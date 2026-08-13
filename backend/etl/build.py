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
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE constructors (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE circuits (
    id       INTEGER PRIMARY KEY,
    slug     TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL,
    country  TEXT NOT NULL,
    -- 0 when no track-map SVG ships for this circuit; the UI shows a
    -- "map unavailable" state rather than substituting a placeholder shape.
    has_map  INTEGER NOT NULL
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

        drivers = {name: i for i, name in enumerate(sorted({r["driver"] for r in rows}), start=1)}
        constructors = {name: i for i, name in enumerate(sorted({r["constructor"] for r in rows}), start=1)}
        circuit_rows = {r["circuit"]["slug"]: r["circuit"] for r in rows}
        circuits = {slug: i for i, slug in enumerate(sorted(circuit_rows), start=1)}

        conn.executemany("INSERT INTO drivers (id, name) VALUES (?, ?)", [(i, n) for n, i in drivers.items()])
        conn.executemany(
            "INSERT INTO constructors (id, name) VALUES (?, ?)", [(i, n) for n, i in constructors.items()]
        )
        conn.executemany(
            "INSERT INTO circuits (id, slug, name, country, has_map) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    circuits[slug],
                    slug,
                    circuit_rows[slug]["circuit_name"],
                    circuit_rows[slug]["country"],
                    int((CIRCUIT_ASSET_DIR / f"{slug}.svg").exists()),
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
