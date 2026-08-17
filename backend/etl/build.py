"""Build the analytical SQLite database from results.csv.

Pipeline: read raw CSV -> validate -> normalize/assign stable IDs -> load.

Reproducible and idempotent: the DB is dropped and rebuilt from scratch on
every run, so there is no hand-editing path by which records can drift away
from the source CSV.

Run:  python -m backend.etl.build            (from the repo root)
      python -m backend.etl.build --report   (also print the data-quality report)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = REPO_ROOT / "results.csv"
CIRCUIT_MAP_CSV = Path(__file__).with_name("circuit_map.csv")
# The directory the frontend actually serves track maps from. Deliberately not
# the extracted design mockup: the pipeline must not depend on an unpacked zip,
# or a fresh clone builds a database claiming no circuit has a map while the
# SVGs sit in frontend/public.
CIRCUIT_ASSET_DIR = REPO_ROOT / "frontend" / "public" / "circuits"
DB_PATH = REPO_ROOT / "data" / "f1.db"

EXPECTED_COLUMNS = ["season", "round", "race_name", "date", "position", "driver", "constructor"]

# Sanity bounds. Deliberately loose -- these catch corruption, not outliers.
MIN_SEASON, MAX_SEASON = 1950, 2100
MAX_POSITION = 40


def strip_accents(text: str) -> str:
    """Fold accents so 'Sao Paulo' and 'Sao Paulo' compare equal.

    The circuit map is written in plain ASCII; race names in the source CSV
    are not. Folding on both sides keeps the map readable and diff-friendly.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


@dataclass
class Issue:
    """One data-quality finding. `fatal` issues abort the build."""

    severity: str  # "fatal" | "warning"
    code: str
    detail: str


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, severity: str, code: str, detail: str) -> None:
        self.issues.append(Issue(severity, code, detail))

    @property
    def fatal(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "fatal"]

    def render(self) -> str:
        lines = ["DATA QUALITY REPORT", "=" * 60]
        for key, value in self.counts.items():
            lines.append(f"  {key:.<34} {value:>8,}")
        lines.append("-" * 60)
        if not self.issues:
            lines.append("  no issues found")
        for issue in self.issues:
            lines.append(f"  [{issue.severity.upper():<7}] {issue.code}: {issue.detail}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Extract
# --------------------------------------------------------------------------

def load_raw(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise SystemExit(f"Unexpected columns in {path}: {reader.fieldnames}")
        return list(reader)


ENRICHMENT_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_results.csv"
SPRINT_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_sprints.csv"
QUALIFYING_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_qualifying.csv"
PITSTOPS_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_pitstops.csv"
LAPTIMES_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_laptimes.csv"
SESSIONS_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_sessions.csv"
# FastF1 / F1 live timing, NOT Jolpica. Different source, 2018 onward only.
PRACTICE_CSV = Path(__file__).resolve().parents[2] / "data" / "fastf1_practice_laps.csv"

# Columns pulled from the enrichment, in the order the INSERT expects them.
_ENRICHMENT_FIELDS = ("classification", "position_text", "status", "points", "grid", "laps")


def load_enrichment() -> dict[tuple[int, int, int], dict[str, str]]:
    """Finishing status, points, grid and laps, keyed by (season, round, position).

    Optional by design. `results.csv` remains the only file this build
    requires; without the enrichment every added column is simply NULL, which
    is the honest representation of "not known here".
    """
    if not ENRICHMENT_CSV.exists():
        return {}
    with ENRICHMENT_CSV.open(newline="", encoding="utf-8") as handle:
        return {
            (int(r["season"]), int(r["round"]), int(r["position"])): r
            for r in csv.DictReader(handle)
        }


def load_dimension_rows(path: Path) -> list[dict[str, str]]:
    """All rows of an optional enrichment CSV, or [] when it is absent."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_sprints() -> list[dict[str, str]]:
    if not SPRINT_CSV.exists():
        return []
    with SPRINT_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _enrichment_values(enrichment: dict, row: dict) -> tuple:
    """Enrichment columns for one result row, or NULLs when unavailable.

    Numbers are converted here rather than at load: the CSV holds text, and a
    string in a REAL column would compare and aggregate wrongly in SQLite,
    which is untyped enough to accept it silently.
    """
    match = enrichment.get((row["season"], row["round"], row["position"]))
    if match is None:
        return (None,) * len(_ENRICHMENT_FIELDS)
    return (
        match["classification"],
        match["position_text"],
        match["status"],
        float(match["points"]),
        int(match["grid"]),
        int(match["laps"]),
    )


DRIVERS_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_drivers.csv"
CONSTRUCTORS_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_constructors.csv"
CIRCUITS_CSV = Path(__file__).resolve().parents[2] / "data" / "jolpica_circuits.csv"


def load_dimension(path: Path, key: str) -> dict[str, dict[str, str]]:
    """Descriptive rows keyed by `key`. Empty when the file is absent."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


def slugify(value: str) -> str:
    """Fallback identifier for an entity the enrichment does not name.

    Only reached when the optional dimension CSV is absent -- a fresh clone
    must still build. It is deliberately not the primary source of slugs: a
    name-derived key changes when the name's punctuation does, whereas the
    source's own id does not.
    """
    folded = strip_accents(value).lower()
    return "".join(c if c.isalnum() else "_" for c in folded).strip("_")


def assign_slugs(
    names: set[str], detail: dict[str, dict[str, str]], key: str, report: Report
) -> dict[str, str]:
    """name -> stable slug, preferring the source's own id over the name.

    WHY THIS EXISTS
    ---------------
    Integer primary keys in this project are assigned by enumerating sorted
    names, and in the Postgres materialisation by a serial sequence in
    insertion order. Those two orderings are unrelated, so `/drivers/7` has
    never referred to the same person in both stores. Nothing detected it
    because nothing ever compared them.

    A slug taken from the upstream source is identical in both, by
    construction. It is therefore the identity the API exposes, and the
    integer id is demoted to a join key that never leaves the database.

    Two names sharing a slug would silently merge two entities, so that is
    fatal rather than a warning.
    """
    slugs = {
        name: _blank_to_none(detail.get(name, {}).get(key)) or slugify(name)
        for name in names
    }
    collisions = defaultdict(list)
    for name, slug in slugs.items():
        collisions[slug].append(name)
    for slug, owners in sorted(collisions.items()):
        if len(owners) > 1:
            report.add("fatal", "duplicate_slug", f"{slug!r} claimed by {sorted(owners)}")
    return slugs


def _blank_to_none(value: str | None) -> str | None:
    """"" means the source has no value -- store NULL, never an empty string.

    A blank string is a value that compares equal to itself and renders as
    nothing, which is precisely how "unknown" gets silently laundered into
    "known to be empty".
    """
    value = (value or "").strip()
    return value or None


def _int_or_none(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def _float_or_none(value: str | None) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def load_circuit_map(path: Path) -> list[dict[str, str]]:
    """Read the curated map, skipping the leading `#` comment block."""
    with path.open(newline="", encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def resolve_circuit(rules: list[dict[str, str]], race_name: str, season: int) -> dict[str, str] | None:
    key = strip_accents(race_name)
    for rule in rules:
        if strip_accents(rule["race_name"]) == key:
            if int(rule["season_from"]) <= season <= int(rule["season_to"]):
                return rule
    return None


# --------------------------------------------------------------------------
# Validate
# --------------------------------------------------------------------------

def validate(rows: list[dict[str, str]], rules: list[dict[str, str]], report: Report) -> list[dict]:
    """Return typed, validated rows. Records issues into `report`.

    Rows that fail a fatal check are still reported (all of them, so one run
    surfaces the full picture) but the build aborts before writing the DB.
    """
    typed: list[dict] = []
    seen_entries: set[tuple[int, int, str]] = set()
    race_meta: dict[tuple[int, int], tuple[str, str]] = {}
    positions_by_race: dict[tuple[int, int], list[int]] = defaultdict(list)
    unmapped: set[tuple[str, int]] = set()

    for line_no, row in enumerate(rows, start=2):
        try:
            season = int(row["season"])
            rnd = int(row["round"])
            position = int(row["position"])
        except ValueError:
            report.add("fatal", "non_integer_field", f"line {line_no}: {row}")
            continue

        driver = row["driver"].strip()
        constructor = row["constructor"].strip()
        race_name = row["race_name"].strip()

        if not driver:
            report.add("fatal", "missing_driver", f"line {line_no}")
        if not constructor:
            report.add("fatal", "missing_constructor", f"line {line_no}")
        if not race_name:
            report.add("fatal", "missing_race_name", f"line {line_no}")
        if not MIN_SEASON <= season <= MAX_SEASON:
            report.add("fatal", "season_out_of_range", f"line {line_no}: {season}")
        if rnd < 1:
            report.add("fatal", "invalid_round", f"line {line_no}: {rnd}")
        if not 1 <= position <= MAX_POSITION:
            report.add("fatal", "invalid_position", f"line {line_no}: {position}")

        try:
            race_date = date.fromisoformat(row["date"])
        except ValueError:
            report.add("fatal", "malformed_date", f"line {line_no}: {row['date']!r}")
            continue
        if race_date.year != season:
            report.add("warning", "date_season_mismatch", f"line {line_no}: {race_date} in season {season}")

        # One result row per driver per race.
        entry_key = (season, rnd, driver)
        if entry_key in seen_entries:
            report.add("fatal", "duplicate_entry", f"{driver} appears twice in {season} R{rnd}")
        seen_entries.add(entry_key)

        # A race must be internally consistent about its own name and date.
        race_key = (season, rnd)
        if race_key in race_meta:
            prior_name, prior_date = race_meta[race_key]
            if prior_name != race_name:
                report.add("fatal", "race_name_conflict", f"{season} R{rnd}: {prior_name!r} vs {race_name!r}")
            if prior_date != row["date"]:
                report.add("fatal", "race_date_conflict", f"{season} R{rnd}: {prior_date} vs {row['date']}")
        else:
            race_meta[race_key] = (race_name, row["date"])

        positions_by_race[race_key].append(position)

        circuit = resolve_circuit(rules, race_name, season)
        if circuit is None:
            unmapped.add((race_name, season))
            continue

        typed.append(
            {
                "season": season,
                "round": rnd,
                "race_name": race_name,
                "date": row["date"],
                "position": position,
                "driver": driver,
                "constructor": constructor,
                "circuit": circuit,
            }
        )

    for race_name, season in sorted(unmapped):
        report.add("fatal", "unmapped_circuit", f"no circuit_map.csv rule for {race_name!r} in {season}")

    # Classification order must be unique within a race (two drivers cannot
    # share a position). Gaps are tolerated: the source omits a handful of
    # classifications -- e.g. the 2002 French GP carries 20 rows but runs to
    # position 22 -- which is an upstream omission, not corruption. Every
    # denominator in analytics.py counts rows present, never max(position),
    # so a gap understates a field size rather than inventing entries.
    for (season, rnd), positions in sorted(positions_by_race.items()):
        if len(set(positions)) != len(positions):
            report.add("fatal", "duplicate_position", f"{season} R{rnd}: got {sorted(positions)}")
        elif max(positions) != len(positions):
            report.add(
                "warning",
                "incomplete_classification",
                f"{season} R{rnd}: {len(positions)} rows but classification runs to P{max(positions)}",
            )

    return typed


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE drivers (
    -- Integer id is an internal join key only. It is assigned by ordering
    -- slugs, so it is stable within a build, but it is NOT the identity the
    -- API exposes -- see `slug`.
    id      INTEGER PRIMARY KEY,
    -- The upstream source's own driver id ("hamilton", "max_verstappen").
    -- This is the public identifier: it is the one value that means the same
    -- thing in this database and in the Postgres materialisation, because
    -- neither store invents it.
    slug    TEXT NOT NULL UNIQUE,
    name    TEXT NOT NULL UNIQUE,
    -- Descriptive data from data/jolpica_drivers.csv. NULL where the source
    -- genuinely has none: 24 drivers predate three-letter codes and 67
    -- predate permanent numbers, so those are unknown, not blank.
    nationality      TEXT,
    date_of_birth    TEXT,
    abbreviation     TEXT,
    permanent_number INTEGER
);

CREATE TABLE constructors (
    id      INTEGER PRIMARY KEY,
    -- The source's own constructor id ("ferrari", "red_bull"). Public
    -- identifier, for the same reason as drivers.slug.
    slug    TEXT NOT NULL UNIQUE,
    name    TEXT NOT NULL UNIQUE,
    nationality TEXT
);

CREATE TABLE circuits (
    id       INTEGER PRIMARY KEY,
    slug     TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL,
    country  TEXT NOT NULL,
    -- 0 when no track-map SVG ships for this circuit; the UI shows a
    -- "map unavailable" state rather than substituting a placeholder shape.
    has_map  INTEGER NOT NULL,
    -- From data/jolpica_circuits.csv, matched to `slug` by shared races
    -- rather than by name. Length, corner count and lap records stay absent:
    -- no source supplies them, so they are not columns here at all.
    official_name TEXT,
    locality      TEXT,
    latitude      REAL,
    longitude     REAL,
    source_url    TEXT
);

CREATE TABLE races (
    id          INTEGER PRIMARY KEY,
    season      INTEGER NOT NULL,
    round       INTEGER NOT NULL,
    name        TEXT NOT NULL,
    date        TEXT NOT NULL,
    circuit_id  INTEGER NOT NULL REFERENCES circuits(id),
    UNIQUE (season, round)
);

CREATE TABLE results (
    id              INTEGER PRIMARY KEY,
    race_id         INTEGER NOT NULL REFERENCES races(id),
    driver_id       INTEGER NOT NULL REFERENCES drivers(id),
    constructor_id  INTEGER NOT NULL REFERENCES constructors(id),
    -- Final classification order, 1..N. NOT a "finishing position": it ranks
    -- retirements alongside finishers. Use `classification` to tell them
    -- apart. See METHODOLOGY.md before deriving anything from this field.
    position        INTEGER NOT NULL,

    -- Enrichment from data/jolpica_results.csv, joined on
    -- (season, round, position). NULL where the enrichment file is absent, so
    -- the build still works offline from results.csv alone.
    --
    -- 'classified' | 'retired' | 'disqualified' | 'withdrawn'. Note that
    -- classified is NOT the same as finished: a driver several laps down is
    -- classified. Whether they saw the flag is in `status`.
    classification  TEXT CHECK (classification IN
                        ('classified','retired','disqualified','withdrawn')),
    position_text   TEXT,
    -- Raw source text, 104 distinct values. Never collapsed into an enum.
    status          TEXT,
    points          REAL CHECK (points >= 0),
    -- 0 is a REAL value: a pit lane start. It is not "unknown".
    grid            INTEGER CHECK (grid >= 0),
    laps            INTEGER CHECK (laps >= 0),
    UNIQUE (race_id, driver_id)
);

CREATE TABLE pit_stops (
    id          INTEGER PRIMARY KEY,
    race_id     INTEGER NOT NULL REFERENCES races(id),
    driver_id   INTEGER NOT NULL REFERENCES drivers(id),
    lap         INTEGER NOT NULL,
    stop        INTEGER NOT NULL,
    -- Local clock time as recorded. Not a timestamp: the source gives no date
    -- or timezone, and inventing one would be a fabrication.
    time_of_day TEXT,
    -- Stationary time as written ("22.213", sometimes "1:04.291"). NULL for 14
    -- stops the source records without a duration -- never 0, which would
    -- corrupt every average. Coverage begins in 2011.
    duration    TEXT,
    UNIQUE (race_id, driver_id, stop)
);

CREATE TABLE qualifying_results (
    id              INTEGER PRIMARY KEY,
    race_id         INTEGER NOT NULL REFERENCES races(id),
    driver_id       INTEGER NOT NULL REFERENCES drivers(id),
    constructor_id  INTEGER NOT NULL REFERENCES constructors(id),
    -- Qualifying classification, NOT the starting grid: penalties and
    -- pit-lane starts change the grid afterwards. Use results.grid for that.
    position        INTEGER NOT NULL,
    -- Raw source times ("1:23.456"). NULL means the segment did not exist in
    -- that era, or no time was set -- never zero. Q2 first appears in 2005
    -- (aggregate format), Q3 in 2006 (three-segment knockout).
    q1              TEXT,
    q2              TEXT,
    q3              TEXT,
    UNIQUE (race_id, driver_id)
);

CREATE TABLE sprint_results (
    id              INTEGER PRIMARY KEY,
    race_id         INTEGER NOT NULL REFERENCES races(id),
    driver_id       INTEGER NOT NULL REFERENCES drivers(id),
    constructor_id  INTEGER NOT NULL REFERENCES constructors(id),
    position        INTEGER NOT NULL,
    position_text   TEXT,
    classification  TEXT,
    status          TEXT,
    points          REAL,
    grid            INTEGER,
    laps            INTEGER,
    -- A separate event, not extra rows in `results`: merging the two would
    -- double every driver's race count and corrupt every entry-based rate.
    UNIQUE (race_id, driver_id)
);

CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY,
    race_id     INTEGER NOT NULL REFERENCES races(id),
    -- fp1 | fp2 | fp3 | sprint_qualifying | sprint | qualifying
    session     TEXT NOT NULL,
    date        TEXT NOT NULL,
    -- NULL for most pre-2018 weekends: the source records the day but not the
    -- clock time. Absent, not midnight.
    time        TEXT,
    UNIQUE (race_id, session)
);

-- The weekend TIMETABLE only. There is deliberately no practice
-- classification table: the source has no practice results, and an empty
-- table named `practice_results` would read as "nobody set a time" rather
-- than "this was never available". See backend/etl/build_sessions.py.
CREATE INDEX idx_sessions_race ON sessions(race_id);

CREATE TABLE practice_laps (
    id          INTEGER PRIMARY KEY,
    race_id     INTEGER NOT NULL REFERENCES races(id),
    driver_id   INTEGER NOT NULL REFERENCES drivers(id),
    -- fp1 | fp2 | fp3
    session     TEXT NOT NULL,
    lap         INTEGER CHECK (lap > 0),
    stint       INTEGER CHECK (stint > 0),
    -- Seconds. NULL where the source timed no lap -- an out-lap, or a lap the
    -- car did not complete. Never 0, which would be the fastest lap ever set.
    lap_time    REAL CHECK (lap_time > 0),
    sector1     REAL CHECK (sector1 > 0),
    sector2     REAL CHECK (sector2 > 0),
    sector3     REAL CHECK (sector3 > 0),
    -- SOFT | MEDIUM | HARD | INTERMEDIATE | WET, as the source names them.
    compound    TEXT,
    tyre_life   INTEGER CHECK (tyre_life >= 0),
    fresh_tyre  INTEGER,
    speed_trap  REAL CHECK (speed_trap > 0),
    is_personal_best INTEGER,
    -- Deleted laps are KEPT and flagged, not dropped. The lap happened, and
    -- which laps stood is what decides a session's fastest time.
    deleted     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (race_id, driver_id, session, lap)
);

-- SOURCE NOTE: practice_laps comes from FastF1 / Formula 1 live timing, NOT
-- from Jolpica like every other table here. Different provenance, different
-- coverage (2018 onward only). It is kept in its own table for exactly that
-- reason -- blending two sources into one table is how they start disagreeing
-- without anyone being able to tell which one is wrong.
CREATE INDEX idx_practice_race    ON practice_laps(race_id, session);
CREATE INDEX idx_practice_driver  ON practice_laps(driver_id);
CREATE INDEX idx_practice_fastest ON practice_laps(race_id, session, lap_time);

CREATE TABLE lap_times (
    id          INTEGER PRIMARY KEY,
    race_id     INTEGER NOT NULL REFERENCES races(id),
    driver_id   INTEGER NOT NULL REFERENCES drivers(id),
    lap         INTEGER NOT NULL CHECK (lap > 0),
    -- Running order at the end of this lap, not the finishing position.
    position    INTEGER CHECK (position > 0),
    -- The source's own string, "1:39.019". Kept because it is what was
    -- published; `time_ms` is derived from it and is what queries sort on.
    time_text   TEXT NOT NULL,
    -- NULL only when time_text could not be parsed, which is recorded as a
    -- build warning rather than silently coerced to 0 -- a zero lap time
    -- would win every "fastest lap" query ever run.
    time_ms     INTEGER CHECK (time_ms > 0),
    UNIQUE (race_id, driver_id, lap)
);

CREATE INDEX idx_lap_times_race   ON lap_times(race_id);
CREATE INDEX idx_lap_times_driver ON lap_times(driver_id);
-- Fastest-lap queries scan by time within a race; this is the covering order.
CREATE INDEX idx_lap_times_fastest ON lap_times(race_id, time_ms);

CREATE TABLE build_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Teammate analysis self-joins results on (race_id, constructor_id) to find
-- drivers sharing a car in a race. Without this composite index that join
-- scans, and it is the single most expensive query in the application.
CREATE INDEX idx_results_race_ctor   ON results(race_id, constructor_id);

CREATE INDEX idx_results_driver      ON results(driver_id);
CREATE INDEX idx_results_constructor ON results(constructor_id);
CREATE INDEX idx_results_race        ON results(race_id);
CREATE INDEX idx_results_position    ON results(position);
CREATE INDEX idx_races_season        ON races(season);
CREATE INDEX idx_races_circuit       ON races(circuit_id);
"""


def load(rows: list[dict], db_path: Path, report: Report) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)

        # Descriptive data, keyed by name. Absent file -> all NULL, which is
        # the honest reading of "this build does not know".
        driver_detail = load_dimension(DRIVERS_CSV, "driver")
        constructor_detail = load_dimension(CONSTRUCTORS_CSV, "constructor")
        circuit_detail = load_dimension(CIRCUITS_CSV, "circuit_key")

        # Integer ids are ordered by *slug*, not by name. Ordering by name
        # made the id depend on how a locale sorts accented characters, which
        # is exactly how this store and the Postgres one drifted apart.
        driver_slugs = assign_slugs(
            {r["driver"] for r in rows}, driver_detail, "jolpica_driver_id", report
        )
        constructor_slugs = assign_slugs(
            {r["constructor"] for r in rows}, constructor_detail, "jolpica_constructor_id", report
        )
        if report.fatal:
            raise SystemExit(report.render())

        drivers = {
            name: i
            for i, name in enumerate(sorted(driver_slugs, key=lambda n: driver_slugs[n]), start=1)
        }
        constructors = {
            name: i
            for i, name in enumerate(
                sorted(constructor_slugs, key=lambda n: constructor_slugs[n]), start=1
            )
        }
        circuit_rows = {r["circuit"]["slug"]: r["circuit"] for r in rows}
        circuits = {slug: i for i, slug in enumerate(sorted(circuit_rows), start=1)}

        conn.executemany(
            """INSERT INTO drivers
                 (id, slug, name, nationality, date_of_birth, abbreviation, permanent_number)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    i, driver_slugs[n], n,
                    _blank_to_none(driver_detail.get(n, {}).get("nationality")),
                    _blank_to_none(driver_detail.get(n, {}).get("date_of_birth")),
                    _blank_to_none(driver_detail.get(n, {}).get("abbreviation")),
                    _int_or_none(driver_detail.get(n, {}).get("permanent_number")),
                )
                for n, i in drivers.items()
            ],
        )
        conn.executemany(
            "INSERT INTO constructors (id, slug, name, nationality) VALUES (?, ?, ?, ?)",
            [
                (i, constructor_slugs[n], n,
                 _blank_to_none(constructor_detail.get(n, {}).get("nationality")))
                for n, i in constructors.items()
            ],
        )
        conn.executemany(
            """INSERT INTO circuits
                 (id, slug, name, country, has_map,
                  official_name, locality, latitude, longitude, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    circuits[slug],
                    slug,
                    circuit_rows[slug]["circuit_name"],
                    circuit_rows[slug]["country"],
                    int((CIRCUIT_ASSET_DIR / f"{slug}.svg").exists()),
                    _blank_to_none(circuit_detail.get(slug, {}).get("official_name")),
                    _blank_to_none(circuit_detail.get(slug, {}).get("locality")),
                    _float_or_none(circuit_detail.get(slug, {}).get("latitude")),
                    _float_or_none(circuit_detail.get(slug, {}).get("longitude")),
                    _blank_to_none(circuit_detail.get(slug, {}).get("source_url")),
                )
                for slug in circuits
            ],
        )

        races: dict[tuple[int, int], int] = {}
        race_records = {}
        for row in rows:
            race_records.setdefault(
                (row["season"], row["round"]),
                (row["race_name"], row["date"], circuits[row["circuit"]["slug"]]),
            )
        for i, (key, (name, race_date, circuit_id)) in enumerate(sorted(race_records.items()), start=1):
            races[key] = i
        conn.executemany(
            "INSERT INTO races (id, season, round, name, date, circuit_id) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (races[key], key[0], key[1], *race_records[key])
                for key in sorted(race_records)
            ],
        )

        # Enrichment is optional: keyed by (season, round, position), it is
        # looked up per row and left NULL when the file is absent, so a clone
        # without it still builds a working database from results.csv alone.
        enrichment = load_enrichment()

        conn.executemany(
            """INSERT INTO results
                 (race_id, driver_id, constructor_id, position,
                  classification, position_text, status, points, grid, laps)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    races[(r["season"], r["round"])],
                    drivers[r["driver"]],
                    constructors[r["constructor"]],
                    r["position"],
                    *_enrichment_values(enrichment, r),
                )
                for r in rows
            ],
        )

        # Pit stops key on the source's own driver id, carried in the
        # committed driver map -- pit-stop rows have no display name at all.
        source_id_to_name = {
            r["jolpica_driver_id"]: r["driver"]
            for r in load_dimension_rows(DRIVERS_CSV) if r.get("jolpica_driver_id")
        }
        conn.executemany(
            """INSERT INTO pit_stops
                 (race_id, driver_id, lap, stop, time_of_day, duration)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    races[(int(s["season"]), int(s["round"]))],
                    drivers[source_id_to_name[s["driver_id"]]],
                    int(s["lap"]), int(s["stop"]),
                    _blank_to_none(s["time_of_day"]),
                    _blank_to_none(s["duration"]),
                )
                for s in load_dimension_rows(PITSTOPS_CSV)
                if (int(s["season"]), int(s["round"])) in races
                and source_id_to_name.get(s["driver_id"]) in drivers
            ],
        )

        session_rows = load_dimension_rows(SESSIONS_CSV)
        conn.executemany(
            "INSERT INTO sessions (race_id, session, date, time) VALUES (?, ?, ?, ?)",
            [
                (
                    races[(int(s["season"]), int(s["round"]))],
                    s["session"], s["date"], _blank_to_none(s["time"]),
                )
                for s in session_rows
                if (int(s["season"]), int(s["round"])) in races
            ],
        )
        report.counts["weekend sessions"] = conn.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]

        # Lap times join on the driver slug directly -- no name round-trip is
        # needed now that `drivers.slug` is the source's own id. Optional like
        # every other enrichment: absent file means an empty table, which is
        # what "not ingested" should look like.
        by_slug = {slug: drivers[name] for name, slug in driver_slugs.items()}
        lap_rows = load_dimension_rows(LAPTIMES_CSV)
        unparsed = 0
        lap_payload = []
        for lap in lap_rows:
            key = (int(lap["season"]), int(lap["round"]))
            if key not in races or lap["driver_id"] not in by_slug:
                continue
            millis = _int_or_none(lap["time_ms"])
            if millis is None:
                unparsed += 1
            lap_payload.append((
                races[key], by_slug[lap["driver_id"]], int(lap["lap"]),
                _int_or_none(lap["position"]), lap["time"], millis,
            ))
        conn.executemany(
            """INSERT INTO lap_times
                 (race_id, driver_id, lap, position, time_text, time_ms)
               VALUES (?, ?, ?, ?, ?, ?)""",
            lap_payload,
        )
        if unparsed:
            # A NULL time_ms is invisible to every ordering query, so the row
            # would drop out of "fastest lap" silently. Surfaced instead.
            report.add("warning", "unparsed_lap_time", f"{unparsed} lap times have no millisecond value")
        report.counts["lap timings"] = len(lap_payload)

        # Practice laps. A second source (FastF1) and therefore its own table:
        # blending two providers into one table is how they begin disagreeing
        # with no way to tell which is wrong.
        practice_rows = load_dimension_rows(PRACTICE_CSV)
        practice_payload = []
        for lap in practice_rows:
            key = (int(lap["season"]), int(lap["round"]))
            if key not in races or lap["driver_slug"] not in by_slug:
                continue
            practice_payload.append((
                races[key], by_slug[lap["driver_slug"]], lap["session"],
                _int_or_none(lap["lap"]), _int_or_none(lap["stint"]),
                _float_or_none(lap["lap_time"]),
                _float_or_none(lap["sector1"]),
                _float_or_none(lap["sector2"]),
                _float_or_none(lap["sector3"]),
                _blank_to_none(lap["compound"]),
                _int_or_none(lap["tyre_life"]),
                _int_or_none(lap["fresh_tyre"]),
                _float_or_none(lap["speed_trap"]),
                _int_or_none(lap["is_personal_best"]),
                int(lap["deleted"] or 0),
            ))
        conn.executemany(
            """INSERT OR IGNORE INTO practice_laps
                 (race_id, driver_id, session, lap, stint, lap_time,
                  sector1, sector2, sector3, compound, tyre_life, fresh_tyre,
                  speed_trap, is_personal_best, deleted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            practice_payload,
        )
        report.counts["practice laps"] = conn.execute(
            "SELECT COUNT(*) FROM practice_laps"
        ).fetchone()[0]

        qualifying = load_dimension_rows(QUALIFYING_CSV)
        conn.executemany(
            """INSERT INTO qualifying_results
                 (race_id, driver_id, constructor_id, position, q1, q2, q3)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    races[(int(q["season"]), int(q["round"]))],
                    drivers[q["driver"]],
                    constructors[q["constructor"]],
                    int(q["position"]),
                    _blank_to_none(q["q1"]),
                    _blank_to_none(q["q2"]),
                    _blank_to_none(q["q3"]),
                )
                for q in qualifying
                if (int(q["season"]), int(q["round"])) in races
                and q["driver"] in drivers and q["constructor"] in constructors
            ],
        )

        sprints = load_sprints()
        conn.executemany(
            """INSERT INTO sprint_results
                 (race_id, driver_id, constructor_id, position,
                  position_text, classification, status, points, grid, laps)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    races[(int(s["season"]), int(s["round"]))],
                    drivers[s["driver"]],
                    constructors[s["constructor"]],
                    int(s["position"]),
                    s["position_text"],
                    s["classification"],
                    s["status"],
                    float(s["points"]),
                    int(s["grid"]),
                    int(s["laps"]),
                )
                for s in sprints
                # A sprint entrant must already exist as a driver from
                # results.csv. None are missing for 2021-2025; skipping rather
                # than inventing a driver keeps the dimension source-faithful,
                # and the count check in the report would surface a shortfall.
                if (int(s["season"]), int(s["round"])) in races
                and s["driver"] in drivers
                and s["constructor"] in constructors
            ],
        )

        mapped_circuits = conn.execute("SELECT COUNT(*) FROM circuits WHERE has_map = 1").fetchone()[0]
        conn.executemany(
            "INSERT INTO build_meta (key, value) VALUES (?, ?)",
            [
                ("source_file", RAW_CSV.name),
                # Provenance that can actually be checked: given a DB, a reader
                # can confirm which bytes of results.csv produced it. A build
                # timestamp was considered and rejected -- it would make two
                # builds of the same source differ, and byte-identical rebuilds
                # are the property that proves this pipeline is reproducible.
                ("source_sha256", hashlib.sha256(RAW_CSV.read_bytes()).hexdigest()),
                ("source_rows", str(len(rows))),
                ("season_min", str(min(r["season"] for r in rows))),
                ("season_max", str(max(r["season"] for r in rows))),
            ],
        )
        conn.commit()

        report.counts.update(
            {
                "result rows loaded": len(rows),
                "races": len(races),
                "drivers": len(drivers),
                "constructors": len(constructors),
                "circuits": len(circuits),
                "circuits with track map": mapped_circuits,
            }
        )
        for slug in sorted(circuits):
            if not (CIRCUIT_ASSET_DIR / f"{slug}.svg").exists():
                report.add("warning", "missing_track_map", f"no SVG asset for circuit {slug!r}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="print the full data-quality report")
    args = parser.parse_args()

    report = Report()
    raw = load_raw(RAW_CSV)
    report.counts["source CSV rows"] = len(raw)

    rules = load_circuit_map(CIRCUIT_MAP_CSV)
    rows = validate(raw, rules, report)

    if report.fatal:
        print(report.render())
        print(f"\nBuild aborted: {len(report.fatal)} fatal issue(s). Database not written.")
        return 1

    load(rows, DB_PATH, report)
    if args.report:
        print(report.render())
    print(f"\nBuilt {DB_PATH.relative_to(REPO_ROOT)} from {len(raw):,} source rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
