"""Import results.csv into Supabase/PostgreSQL.

Pipeline
--------
    results.csv
        -> staging_results          (raw text, nothing rejected at load time)
        -> validate in staging      (types, ranges, circuit resolution)
        -> upsert dimensions        (seasons, circuits, drivers, constructors)
        -> upsert races
        -> upsert results
        -> derive driver_constructor_seasons
        -> record data-quality checks + dataset provenance
        -> reconcile against the source file

Idempotent: every promotion is an upsert on a natural key, so running it twice
updates rows instead of duplicating them. Verified by the reconciliation step,
which fails the run if database counts drift from the file.

Usage
-----
    export SUPABASE_DB_URL="postgresql://postgres:...@db.<ref>.supabase.co:5432/postgres"
    python -m backend.etl.supabase_import              # full import
    python -m backend.etl.supabase_import --dry-run    # validate only, no writes

The connection string contains the database password and is read from the
environment. It is never committed and never reaches the frontend.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

# Populates os.environ from .env before SUPABASE_DB_URL is read below.
from backend.app import env as _env  # noqa: F401

try:
    import psycopg
except ImportError:  # pragma: no cover - dependency guidance, not logic
    sys.exit("psycopg is required: pip install 'psycopg[binary]'")

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = REPO_ROOT / "results.csv"
CIRCUIT_MAP_CSV = Path(__file__).with_name("circuit_map.csv")
# Second source: finishing status, points, grid, laps. Built by
# `python -m backend.etl.build_enrichment`, joined on (season, round, position).
ENRICHMENT_CSV = REPO_ROOT / "data" / "jolpica_results.csv"
# Sprint races, 2021 onward. Separate event, separate table.
SPRINT_CSV = REPO_ROOT / "data" / "jolpica_sprints.csv"
# Descriptive columns the dimension tables were created for and left NULL.
DRIVERS_CSV = REPO_ROOT / "data" / "jolpica_drivers.csv"
CONSTRUCTORS_CSV = REPO_ROOT / "data" / "jolpica_constructors.csv"
CIRCUITS_CSV = REPO_ROOT / "data" / "jolpica_circuits.csv"
# Qualifying. Coverage is partial before 2003 -- see migration 12.
QUALIFYING_CSV = REPO_ROOT / "data" / "jolpica_qualifying.csv"
# Pit stops. Source coverage begins in 2011 -- see migration 14.
PITSTOPS_CSV = REPO_ROOT / "data" / "jolpica_pitstops.csv"
CIRCUIT_ASSET_DIR = REPO_ROOT / "frontend" / "public" / "circuits"

DATASET_KEY = "ergast_results"
DATASET_VERSION = "2025.1"

MIN_SEASON, MAX_SEASON, MAX_POSITION = 1950, 2100, 40


# ---------------------------------------------------------------- helpers

def strip_accents(text: str) -> str:
    """Fold accents so the ASCII circuit map matches 'São Paulo'."""
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def load_circuit_map() -> list[dict]:
    with CIRCUIT_MAP_CSV.open(newline="", encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


def resolve_circuit(rules: list[dict], race_name: str, season: int) -> dict | None:
    key = strip_accents(race_name)
    for rule in rules:
        if strip_accents(rule["race_name"]) == key and int(rule["season_from"]) <= season <= int(rule["season_to"]):
            return rule
    return None


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def slugify(value: str) -> str:
    """Stable key from a display name.

    Accents folded and non-alphanumerics collapsed, so 'Nico Hülkenberg'
    becomes 'nico-hulkenberg' deterministically on every run -- which is what
    makes the upsert idempotent.
    """
    folded = strip_accents(value).lower()
    return "-".join("".join(c if c.isalnum() else " " for c in folded).split())


class Report:
    def __init__(self) -> None:
        self.run_id = uuid.uuid4()
        self.counts: dict[str, int] = {}
        self.checks: list[tuple[str, str, str, int, str]] = []

    def check(self, name: str, status: str, severity: str, rows: int, details: str) -> None:
        self.checks.append((name, status, severity, rows, details))

    @property
    def failed(self) -> bool:
        return any(status == "fail" for _, status, _, _, _ in self.checks)

    def render(self) -> str:
        out = ["", "=" * 68, f"SUPABASE IMPORT  run {self.run_id}", "=" * 68]
        for key, value in self.counts.items():
            out.append(f"  {key:.<44} {value:>10,}")
        out.append("-" * 68)
        for name, status, severity, rows, details in self.checks:
            marker = {"pass": "OK  ", "warn": "WARN", "fail": "FAIL"}[status]
            out.append(f"  [{marker}] {name}" + (f" ({rows:,} rows)" if rows else ""))
            if details and status != "pass":
                out.append(f"         {details}")
        return "\n".join(out)


# ---------------------------------------------------------------- stages

def stage(conn, report: Report, rules: list[dict]) -> None:
    """Load the raw file into staging and validate it there."""
    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    report.counts["source CSV rows"] = len(rows)

    payload = []
    for line_no, row in enumerate(rows, start=2):
        payload.append(
            (
                report.run_id, line_no, row["season"], row["round"], row["race_name"],
                row["date"], row["position"], row["driver"], row["constructor"],
            )
        )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM staging_results WHERE run_id = %s", (report.run_id,))
        cur.executemany(
            """INSERT INTO staging_results
               (run_id, line_no, season, round, race_name, race_date, position, driver, constructor)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            payload,
        )

        # Validate inside the database so the rules apply to whatever was
        # actually loaded, not to the Python objects we think we loaded.
        cur.execute(
            """
            UPDATE staging_results SET rejection = CASE
                WHEN season      !~ '^[0-9]+$'          THEN 'season not an integer'
                WHEN round       !~ '^[0-9]+$'          THEN 'round not an integer'
                WHEN position    !~ '^[0-9]+$'          THEN 'position not an integer'
                WHEN race_date   !~ '^\\d{4}-\\d{2}-\\d{2}$' THEN 'malformed date'
                WHEN coalesce(trim(driver), '')      = '' THEN 'missing driver'
                WHEN coalesce(trim(constructor), '') = '' THEN 'missing constructor'
                WHEN coalesce(trim(race_name), '')   = '' THEN 'missing race name'
                WHEN season::int NOT BETWEEN %s AND %s THEN 'season out of range'
                WHEN round::int  < 1                   THEN 'invalid round'
                WHEN position::int NOT BETWEEN 1 AND %s THEN 'position out of range'
                ELSE NULL END
            WHERE run_id = %s
            """,
            (MIN_SEASON, MAX_SEASON, MAX_POSITION, report.run_id),
        )

        # Resolve circuits for rows that passed type validation.
        cur.execute(
            "SELECT id, race_name, season FROM staging_results WHERE run_id = %s AND rejection IS NULL",
            (report.run_id,),
        )
        updates, unmapped = [], set()
        for row_id, race_name, season in cur.fetchall():
            rule = resolve_circuit(rules, race_name.strip(), int(season))
            if rule:
                updates.append((rule["slug"], row_id))
            else:
                unmapped.add((race_name, season))
        cur.executemany("UPDATE staging_results SET circuit_key = %s WHERE id = %s", updates)

        cur.execute(
            "UPDATE staging_results SET is_valid = true WHERE run_id = %s AND rejection IS NULL AND circuit_key IS NOT NULL",
            (report.run_id,),
        )
        cur.execute(
            "UPDATE staging_results SET rejection = 'no circuit_map rule' "
            "WHERE run_id = %s AND rejection IS NULL AND circuit_key IS NULL",
            (report.run_id,),
        )

        cur.execute("SELECT count(*) FROM staging_results WHERE run_id = %s AND is_valid", (report.run_id,))
        valid = cur.fetchone()[0]
        cur.execute(
            "SELECT rejection, count(*) FROM staging_results WHERE run_id = %s AND NOT is_valid GROUP BY rejection",
            (report.run_id,),
        )
        rejections = cur.fetchall()

    report.counts["staged rows"] = len(payload)
    report.counts["valid rows"] = valid
    report.counts["rejected rows"] = len(payload) - valid

    if rejections:
        for reason, count in rejections:
            report.check(f"rejected: {reason}", "fail", "fatal", count, "row did not pass staging validation")
    else:
        report.check("staging validation", "pass", "info", 0, "")

    if unmapped:
        report.check(
            "unmapped circuits", "fail", "fatal", len(unmapped),
            "; ".join(f"{name} {season}" for name, season in sorted(unmapped)[:5]),
        )


def promote(conn, report: Report, rules: list[dict], dataset_id: int) -> None:
    """Normalise staging into the production tables. All upserts."""
    with conn.cursor() as cur:
        # ---- seasons
        cur.execute(
            """
            INSERT INTO seasons (year, display_name, dataset_id)
            SELECT DISTINCT season::int, season, %s FROM staging_results WHERE run_id = %s AND is_valid
            ON CONFLICT (year) DO UPDATE SET display_name = excluded.display_name, updated_at = now()
            """,
            (dataset_id, report.run_id),
        )

        # ---- circuits (from the curated map, restricted to those actually used)
        used = {row["slug"] for row in rules}
        cur.execute("SELECT DISTINCT circuit_key FROM staging_results WHERE run_id = %s AND is_valid", (report.run_id,))
        active = {row[0] for row in cur.fetchall()}
        circuit_rows = []
        for slug in sorted(used & active):
            rule = next(r for r in rules if r["slug"] == slug)
            asset = f"/circuits/{slug}.svg" if (CIRCUIT_ASSET_DIR / f"{slug}.svg").exists() else None
            circuit_rows.append((slug, rule["circuit_name"], rule["country"], asset))
        cur.executemany(
            """
            INSERT INTO circuits (circuit_key, circuit_name, country, svg_asset)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (circuit_key) DO UPDATE
              SET circuit_name = excluded.circuit_name,
                  country      = excluded.country,
                  svg_asset    = excluded.svg_asset,
                  updated_at   = now()
            """,
            circuit_rows,
        )

        # ---- drivers / constructors
        for table, key_col, name_col, source_col in (
            ("drivers", "driver_key", "display_name", "driver"),
            ("constructors", "constructor_key", "constructor_name", "constructor"),
        ):
            cur.execute(
                f"SELECT DISTINCT trim({source_col}) FROM staging_results WHERE run_id = %s AND is_valid",
                (report.run_id,),
            )
            entities = [(slugify(name), name) for (name,) in cur.fetchall()]
            cur.executemany(
                f"""INSERT INTO {table} ({key_col}, {name_col}) VALUES (%s,%s)
                    ON CONFLICT ({key_col}) DO UPDATE
                      SET {name_col} = excluded.{name_col}, updated_at = now()""",
                entities,
            )

        # ---- races
        cur.execute(
            """
            INSERT INTO races (season_id, round, race_name, circuit_id, race_date)
            SELECT DISTINCT s.id, st.round::int, trim(st.race_name), c.id, st.race_date::date
            FROM staging_results st
            JOIN seasons  s ON s.year = st.season::int
            JOIN circuits c ON c.circuit_key = st.circuit_key
            WHERE st.run_id = %s AND st.is_valid
            ON CONFLICT (season_id, round) DO UPDATE
              SET race_name  = excluded.race_name,
                  circuit_id = excluded.circuit_id,
                  race_date  = excluded.race_date,
                  updated_at = now()
            """,
            (report.run_id,),
        )

        # ---- results
        cur.execute(
            """
            INSERT INTO results (race_id, driver_id, constructor_id, position, dataset_id)
            SELECT r.id, d.id, co.id, st.position::int, %s
            FROM staging_results st
            JOIN seasons s       ON s.year = st.season::int
            JOIN races r         ON r.season_id = s.id AND r.round = st.round::int
            JOIN drivers d       ON d.display_name = trim(st.driver)
            JOIN constructors co ON co.constructor_name = trim(st.constructor)
            WHERE st.run_id = %s AND st.is_valid
            ON CONFLICT (race_id, driver_id) DO UPDATE
              SET constructor_id = excluded.constructor_id,
                  position       = excluded.position,
                  dataset_id     = excluded.dataset_id,
                  updated_at     = now()
            """,
            (dataset_id, report.run_id),
        )

        # ---- driver_constructor_seasons (derived, never hand-entered)
        cur.execute(
            """
            INSERT INTO driver_constructor_seasons
                (driver_id, constructor_id, season_id, race_count, first_round, last_round)
            SELECT res.driver_id, res.constructor_id, ra.season_id,
                   count(*), min(ra.round), max(ra.round)
            FROM results res JOIN races ra ON ra.id = res.race_id
            GROUP BY res.driver_id, res.constructor_id, ra.season_id
            ON CONFLICT (driver_id, constructor_id, season_id) DO UPDATE
              SET race_count  = excluded.race_count,
                  first_round = excluded.first_round,
                  last_round  = excluded.last_round
            """
        )

        for table in ("seasons", "circuits", "drivers", "constructors", "races", "results",
                      "driver_constructor_seasons"):
            cur.execute(f"SELECT count(*) FROM {table}")
            report.counts[f"{table} in database"] = cur.fetchone()[0]


def promote_enrichment(conn, report: Report) -> None:
    """Attach finishing status, points, grid and laps to existing result rows.

    A second source (`data/jolpica_results.csv`) joined on
    (season, round, position). That key was verified to align across all 10,550
    rows -- same driver, same constructor -- before the columns were added.

    This UPDATEs existing rows and inserts nothing: the enrichment must never
    be able to invent a result that `results.csv` does not contain. If the join
    misses, the row keeps NULLs and the coverage check below reports it.
    """
    if not ENRICHMENT_CSV.exists():
        report.check("enrichment source", "warn", "warning", 0,
                     f"{ENRICHMENT_CSV.name} not found -- run "
                     "python -m backend.etl.build_enrichment")
        return

    with ENRICHMENT_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    report.counts["enrichment source rows"] = len(rows)

    payload = [
        (
            row["position_text"], row["classification"], row["status"],
            row["points"], row["grid"], row["laps"],
            int(row["season"]), int(row["round"]), int(row["position"]),
        )
        for row in rows
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            UPDATE results r
               SET position_text  = %s,
                   classification = %s,
                   status         = %s,
                   points         = %s::numeric,
                   grid           = %s::smallint,
                   laps           = %s::smallint,
                   updated_at     = now()
              FROM races ra JOIN seasons s ON s.id = ra.season_id
             WHERE ra.id = r.race_id
               AND s.year = %s AND ra.round = %s AND r.position = %s
            """,
            payload,
        )

        cur.execute("SELECT count(*) FROM results WHERE classification IS NULL")
        unenriched = cur.fetchone()[0]
        report.counts["results enriched"] = (
            report.counts.get("results in database", 0) - unenriched
        )
        report.check(
            "enrichment coverage",
            "pass" if unenriched == 0 else "fail",
            "info" if unenriched == 0 else "fatal",
            unenriched,
            "result rows with no finishing status -- the join key missed",
        )

        # The enrichment must not have altered classification order. If these
        # disagree, the join matched the wrong rows.
        cur.execute(
            """SELECT count(*) FROM results
               WHERE classification = 'classified' AND position_text <> position::text"""
        )
        drifted = cur.fetchone()[0]
        report.check(
            "enrichment agrees with position", "pass" if drifted == 0 else "fail",
            "info" if drifted == 0 else "fatal", drifted,
            "classified rows whose position_text disagrees with position",
        )

        # Winners must be classified, score points, and complete laps. A join
        # that silently shifted by one row would break this immediately.
        cur.execute(
            """SELECT count(*) FROM results
               WHERE position = 1
                 AND (classification <> 'classified' OR points <= 0 OR laps <= 0)"""
        )
        bad_winners = cur.fetchone()[0]
        report.check(
            "winners are classified and scored", "pass" if bad_winners == 0 else "fail",
            "info" if bad_winners == 0 else "fatal", bad_winners,
            "race winners with a non-classified status, no points or no laps",
        )


def promote_pit_stops(conn, report: Report, dataset_id: int) -> None:
    """Load pit stops, 2011 onward.

    Keyed on the source's own `driverId`, resolved through the committed map in
    jolpica_drivers.csv rather than by name -- pit-stop rows carry no display
    name, so a name join is not even available here.

    Coverage before 2011 is zero and that is correct, so no count check against
    `results` is made. What is checked is that every row in the file landed.
    """
    if not PITSTOPS_CSV.exists() or not DRIVERS_CSV.exists():
        report.check("pit stop source", "warn", "warning", 0,
                     "jolpica_pitstops.csv or jolpica_drivers.csv missing")
        return

    with DRIVERS_CSV.open(newline="", encoding="utf-8") as handle:
        by_source_id = {
            r["jolpica_driver_id"]: r["driver"]
            for r in csv.DictReader(handle)
            if r.get("jolpica_driver_id")
        }

    with PITSTOPS_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    report.counts["pit stop source rows"] = len(rows)

    unresolved = sorted({r["driver_id"] for r in rows if r["driver_id"] not in by_source_id})
    if unresolved:
        # Refuse rather than drop: a driver id with no mapping means the
        # dimension and the fact table disagree about who exists.
        report.check("pit stop drivers resolve", "fail", "fatal", len(unresolved),
                     f"unmapped source driver ids: {', '.join(unresolved[:5])}")
        return

    payload = [
        (
            int(r["lap"]), int(r["stop"]),
            (r["time_of_day"] or "").strip() or None,
            # NULL, never 0: a zero-second stop is not a thing.
            (r["duration"] or "").strip() or None,
            dataset_id,
            int(r["season"]), int(r["round"]), by_source_id[r["driver_id"]],
        )
        for r in rows
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO pit_stops
                (race_id, driver_id, lap, stop, time_of_day, duration, dataset_id)
            SELECT ra.id, d.id, %s, %s, %s, %s, %s
            FROM races ra
            JOIN seasons s ON s.id = ra.season_id AND s.year = %s
            JOIN drivers d ON d.display_name = %s
            WHERE ra.round = %s
            ON CONFLICT (race_id, driver_id, stop) DO UPDATE
              SET lap = excluded.lap, time_of_day = excluded.time_of_day,
                  duration = excluded.duration, updated_at = now()
            """,
            # Placeholder order in the SQL, not column order.
            [(lap, stop, tod, dur, ds, season, driver, rnd)
             for lap, stop, tod, dur, ds, season, rnd, driver in payload],
        )

        cur.execute("SELECT count(*) FROM pit_stops")
        loaded = cur.fetchone()[0]
        report.counts["pit_stops in database"] = loaded
        report.check(
            "every pit stop row loaded",
            "pass" if loaded == len(rows) else "fail",
            "info" if loaded == len(rows) else "fatal",
            len(rows) - loaded,
            "pit stop rows whose race or driver did not resolve",
        )

        cur.execute(
            "SELECT count(*) FROM pit_stops p"
            " JOIN races ra ON ra.id = p.race_id"
            " JOIN seasons s ON s.id = ra.season_id"
            " WHERE s.year < 2011"
        )
        early = cur.fetchone()[0]
        report.check(
            "no pit stops before 2011", "pass" if early == 0 else "fail",
            "info" if early == 0 else "fatal", early,
            "pit stops recorded for seasons the source does not cover",
        )


def promote_qualifying(conn, report: Report, dataset_id: int) -> None:
    """Load qualifying into its own table.

    Coverage is partial before 2003 and that is expected, so this deliberately
    does NOT check row count against `results`. What it does check is that
    every row present in the file landed: a shortfall means a driver or race
    failed to resolve, which is a real failure and must not be mistaken for
    the known source gap.
    """
    if not QUALIFYING_CSV.exists():
        report.check("qualifying source", "warn", "warning", 0,
                     f"{QUALIFYING_CSV.name} not found -- qualifying not loaded")
        return

    with QUALIFYING_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    report.counts["qualifying source rows"] = len(rows)

    def blank_to_none(value: str) -> str | None:
        # "" means the segment did not exist or no time was set. NULL, not "".
        return (value or "").strip() or None

    payload = [
        (
            int(r["position"]), blank_to_none(r["q1"]), blank_to_none(r["q2"]),
            blank_to_none(r["q3"]), dataset_id,
            int(r["season"]), r["driver"].strip(), r["constructor"].strip(),
            int(r["round"]),
        )
        for r in rows
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO qualifying_results
                (race_id, driver_id, constructor_id, position, q1, q2, q3, dataset_id)
            SELECT ra.id, d.id, co.id, %s, %s, %s, %s, %s
            FROM races ra
            JOIN seasons s       ON s.id = ra.season_id AND s.year = %s
            JOIN drivers d       ON d.display_name = %s
            JOIN constructors co ON co.constructor_name = %s
            WHERE ra.round = %s
            ON CONFLICT (race_id, driver_id) DO UPDATE
              SET constructor_id = excluded.constructor_id,
                  position       = excluded.position,
                  q1 = excluded.q1, q2 = excluded.q2, q3 = excluded.q3,
                  updated_at     = now()
            """,
            payload,
        )

        cur.execute("SELECT count(*) FROM qualifying_results")
        loaded = cur.fetchone()[0]
        report.counts["qualifying_results in database"] = loaded
        report.check(
            "every qualifying row loaded",
            "pass" if loaded == len(rows) else "fail",
            "info" if loaded == len(rows) else "fatal",
            len(rows) - loaded,
            "qualifying rows whose driver, constructor or race did not resolve",
        )

        # One pole per race, wherever the session is recorded at all.
        cur.execute(
            "SELECT count(*) FROM (SELECT race_id FROM qualifying_results"
            " WHERE position = 1 GROUP BY race_id HAVING count(*) > 1) x"
        )
        dupes = cur.fetchone()[0]
        report.check(
            "one pole per race", "pass" if dupes == 0 else "fail",
            "info" if dupes == 0 else "fatal", dupes,
            "races with more than one qualifying P1",
        )

        # A session must not appear before the format that created it.
        #
        # This check first encoded the assumption "Q1/Q2/Q3 began in 2006" and
        # failed on 107 rows -- correctly, because the assumption was wrong.
        # 2005 opened with AGGREGATE qualifying: two flying laps, one on
        # Saturday and one on Sunday, recorded as Q1 and Q2 and summed. So Q2
        # in 2005 is real data, not corruption.
        #
        # Q3 is the genuine 2006 marker: the three-segment knockout format.
        # This is exactly why modern rules must never be assumed to hold
        # historically -- the source was right and the check was wrong.
        cur.execute(
            """SELECT count(*) FROM qualifying_results q
               JOIN races ra ON ra.id = q.race_id
               JOIN seasons s ON s.id = ra.season_id
               WHERE (s.year < 2006 AND q.q3 IS NOT NULL)
                  OR (s.year < 2005 AND q.q2 IS NOT NULL)"""
        )
        anachronistic = cur.fetchone()[0]
        report.check(
            "no session predates its format",
            "pass" if anachronistic == 0 else "fail",
            "info" if anachronistic == 0 else "fatal", anachronistic,
            "Q3 before 2006, or Q2 before the 2005 aggregate format",
        )


def promote_dimensions(conn, report: Report) -> None:
    """Fill the descriptive columns the dimension tables were created for.

    `drivers.nationality`, `drivers.date_of_birth`, `circuits.latitude` and
    friends have been NULL since the schema was written, honestly meaning "not
    yet known". This is the source that knows.

    Empty strings become NULL, never "". A blank string would pass a NOT NULL
    check and satisfy a CHECK constraint while meaning nothing -- exactly the
    placeholder-as-data problem the project forbids. It also matters
    concretely: `abbreviation` is constrained to ^[A-Z]{3}$ and 24 drivers
    predate three-letter codes; 67 predate permanent numbers.

    Still NULL after this, because no source supplies them: circuit length,
    number of corners, lap records.
    """
    def rows_of(path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def blank_to_none(value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    drivers = rows_of(DRIVERS_CSV)
    constructors = rows_of(CONSTRUCTORS_CSV)
    circuits = rows_of(CIRCUITS_CSV)

    if not (drivers or constructors or circuits):
        report.check("dimension enrichment", "warn", "warning", 0,
                     "no dimension CSVs -- run python -m backend.etl.build_dimensions")
        return

    with conn.cursor() as cur:
        cur.executemany(
            """UPDATE drivers SET nationality = %s, date_of_birth = %s::date,
                      abbreviation = %s, permanent_number = %s::int, updated_at = now()
               WHERE display_name = %s""",
            [
                (
                    blank_to_none(r["nationality"]),
                    blank_to_none(r["date_of_birth"]),
                    blank_to_none(r["abbreviation"]),
                    blank_to_none(r["permanent_number"]),
                    r["driver"].strip(),
                )
                for r in drivers
            ],
        )
        cur.executemany(
            "UPDATE constructors SET nationality = %s, updated_at = now()"
            " WHERE constructor_name = %s",
            [(blank_to_none(r["nationality"]), r["constructor"].strip()) for r in constructors],
        )
        cur.executemany(
            """UPDATE circuits SET official_name = %s, locality = %s,
                      latitude = %s::numeric, longitude = %s::numeric,
                      source_url = %s, updated_at = now()
               WHERE circuit_key = %s""",
            [
                (
                    blank_to_none(r["official_name"]), blank_to_none(r["locality"]),
                    blank_to_none(r["latitude"]), blank_to_none(r["longitude"]),
                    blank_to_none(r["source_url"]), r["circuit_key"].strip(),
                )
                for r in circuits
            ],
        )

        for table, column, expected in (
            ("drivers", "nationality", len(drivers)),
            ("drivers", "date_of_birth", len(drivers)),
            ("constructors", "nationality", len(constructors)),
            ("circuits", "latitude", len(circuits)),
        ):
            cur.execute(f"SELECT count({column}) FROM {table}")
            got = cur.fetchone()[0]
            report.check(
                f"{table}.{column} populated",
                "pass" if got == expected else "fail",
                "info" if got == expected else "fatal",
                expected - got,
                f"{table} rows still missing {column} after enrichment",
            )
        report.counts["drivers enriched"] = len(drivers)
        report.counts["constructors enriched"] = len(constructors)
        report.counts["circuits enriched"] = len(circuits)


def promote_sprints(conn, report: Report, dataset_id: int) -> None:
    """Load sprint results into their own table.

    Resolved by driver and constructor NAME against the dimensions already
    loaded from results.csv. A sprint entrant who never started a Grand Prix
    would not exist as a driver row -- so the count check below fails the run
    rather than silently dropping them. (None exist in 2021-2025; the check is
    there so a future season cannot regress silently.)
    """
    if not SPRINT_CSV.exists():
        report.check("sprint source", "warn", "warning", 0,
                     f"{SPRINT_CSV.name} not found -- sprints not loaded")
        return

    with SPRINT_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    report.counts["sprint source rows"] = len(rows)

    # psycopg3 accepts only positional %s, so the tuple order below must match
    # the order the placeholders appear in the SQL, not the column order.
    payload = [
        (
            int(row["position"]), row["position_text"], row["classification"],
            row["status"], row["points"], row["grid"], row["laps"], dataset_id,
            int(row["season"]), row["driver"].strip(), row["constructor"].strip(),
            int(row["round"]),
        )
        for row in rows
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sprint_results
                (race_id, driver_id, constructor_id, position, position_text,
                 classification, status, points, grid, laps, dataset_id)
            SELECT ra.id, d.id, co.id, %s, %s, %s, %s,
                   %s::numeric, %s::smallint, %s::smallint, %s
            FROM races ra
            JOIN seasons s       ON s.id = ra.season_id AND s.year = %s
            JOIN drivers d       ON d.display_name = %s
            JOIN constructors co ON co.constructor_name = %s
            WHERE ra.round = %s
            ON CONFLICT (race_id, driver_id) DO UPDATE
              SET constructor_id = excluded.constructor_id,
                  position       = excluded.position,
                  position_text  = excluded.position_text,
                  classification = excluded.classification,
                  status         = excluded.status,
                  points         = excluded.points,
                  grid           = excluded.grid,
                  laps           = excluded.laps,
                  updated_at     = now()
            """,
            payload,
        )

        cur.execute("SELECT count(*) FROM sprint_results")
        loaded = cur.fetchone()[0]
        report.counts["sprint_results in database"] = loaded
        report.check(
            "every sprint row loaded",
            "pass" if loaded == len(rows) else "fail",
            "info" if loaded == len(rows) else "fatal",
            len(rows) - loaded,
            "sprint rows whose driver, constructor or race did not resolve",
        )


def reconcile(conn, report: Report) -> None:
    """Prove the database agrees with the source file.

    A count that drifts from the file means the import silently lost or
    duplicated rows, which is a failure, not a warning.
    """
    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    expected = {
        "results": len(rows),
        "races": len({(r["season"], r["round"]) for r in rows}),
        "seasons": len({r["season"] for r in rows}),
        "drivers": len({r["driver"].strip() for r in rows}),
        "constructors": len({r["constructor"].strip() for r in rows}),
    }

    with conn.cursor() as cur:
        for table, want in expected.items():
            cur.execute(f"SELECT count(*) FROM {table}")
            got = cur.fetchone()[0]
            report.check(
                f"reconcile {table}",
                "pass" if got == want else "fail",
                "info" if got == want else "fatal",
                abs(got - want),
                "" if got == want else f"source {want:,} vs database {got:,}",
            )

        # Integrity checks that must hold regardless of the source.
        integrity = [
            ("no orphaned results", """
                SELECT count(*) FROM results r
                LEFT JOIN races ra ON ra.id = r.race_id
                LEFT JOIN drivers d ON d.id = r.driver_id
                LEFT JOIN constructors c ON c.id = r.constructor_id
                WHERE ra.id IS NULL OR d.id IS NULL OR c.id IS NULL"""),
            ("no duplicate driver per race", """
                SELECT count(*) FROM (
                    SELECT race_id, driver_id FROM results
                    GROUP BY race_id, driver_id HAVING count(*) > 1) x"""),
            ("exactly one winner per race", """
                SELECT count(*) FROM (
                    SELECT race_id FROM results WHERE position = 1
                    GROUP BY race_id HAVING count(*) <> 1) x"""),
            ("no orphaned races", "SELECT count(*) FROM races ra LEFT JOIN seasons s ON s.id = ra.season_id WHERE s.id IS NULL"),
            ("race date matches season", "SELECT count(*) FROM races ra JOIN seasons s ON s.id = ra.season_id WHERE extract(year FROM ra.race_date) <> s.year"),
            ("positions within range", f"SELECT count(*) FROM results WHERE position < 1 OR position > {MAX_POSITION}"),
            ("no duplicate positions in a race", """
                SELECT count(*) FROM (
                    SELECT race_id, position FROM results
                    GROUP BY race_id, position HAVING count(*) > 1) x"""),
        ]
        for name, sql in integrity:
            cur.execute(sql)
            bad = cur.fetchone()[0]
            report.check(name, "pass" if bad == 0 else "fail", "info" if bad == 0 else "fatal", bad, "")

        # Known upstream gap: reported, not patched.
        cur.execute("""
            SELECT count(*) FROM (
                SELECT race_id FROM results GROUP BY race_id
                HAVING max(position) <> count(*)) x""")
        gaps = cur.fetchone()[0]
        report.check(
            "complete classification sequence", "warn" if gaps else "pass", "warning" if gaps else "info",
            gaps, "races whose classification has gaps -- an upstream omission, not corruption",
        )


def persist_report(conn, report: Report) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO data_quality_checks
               (run_id, check_name, dataset_key, status, severity, affected_rows, details)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            [(report.run_id, name, DATASET_KEY, status, severity, rows, details)
             for name, status, severity, rows, details in report.checks],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate in staging, write nothing")
    args = parser.parse_args()

    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        sys.exit("SUPABASE_DB_URL is not set. See .env.example.")

    rules = load_circuit_map()
    report = Report()

    # Tuple rows, deliberately. Every read in this module is positional
    # (`fetchone()[0]`, `for a, b, c in cur.fetchall()`), and a dict_row cursor
    # silently turns those into reads of the *column names* -- unpacking a dict
    # yields its keys, so `int(season)` received the literal string 'season'.
    # That failed loudly here, but a positional read of a one-column dict would
    # have failed silently. The two places that want a field by name index [0].
    with psycopg.connect(dsn) as conn:
        # One transaction: a failed import leaves the database untouched
        # rather than half-populated.
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO data_sources (source_key, name, source_type, source_url, description)
                       VALUES ('ergast_csv','Ergast-derived race classifications','csv',NULL,
                               'Local results.csv: season, round, race_name, date, position, driver, constructor')
                       ON CONFLICT (source_key) DO UPDATE SET name = excluded.name
                       RETURNING id""")
                source_id = cur.fetchone()[0]

                cur.execute(
                    """INSERT INTO datasets
                         (source_id, dataset_key, version, coverage_start, coverage_end, row_count, checksum, description)
                       VALUES (%s,%s,%s,NULL,NULL,NULL,%s,'Race classifications, one row per driver per race')
                       ON CONFLICT (dataset_key, version) DO UPDATE
                         SET checksum = excluded.checksum, imported_at = now()
                       RETURNING id""",
                    (source_id, DATASET_KEY, DATASET_VERSION, checksum(RAW_CSV)),
                )
                dataset_id = cur.fetchone()[0]

            stage(conn, report, rules)

            if report.failed:
                print(report.render())
                print("\nStaging validation failed. Nothing was promoted.")
                raise SystemExit(1)

            if args.dry_run:
                print(report.render())
                print("\nDry run: staging validated, nothing promoted.")
                raise SystemExit(0)

            promote(conn, report, rules, dataset_id)
            promote_enrichment(conn, report)
            promote_sprints(conn, report, dataset_id)
            promote_dimensions(conn, report)
            promote_qualifying(conn, report, dataset_id)
            promote_pit_stops(conn, report, dataset_id)
            reconcile(conn, report)
            persist_report(conn, report)

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE datasets SET coverage_start = (SELECT min(year) FROM seasons),"
                    " coverage_end = (SELECT max(year) FROM seasons),"
                    " row_count = (SELECT count(*) FROM results) WHERE id = %s",
                    (dataset_id,),
                )
                cur.execute("DELETE FROM staging_results WHERE run_id = %s", (report.run_id,))

            if report.failed:
                print(report.render())
                print("\nReconciliation failed -- transaction rolled back.")
                raise SystemExit(1)

    print(report.render())
    print("\nImport complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
