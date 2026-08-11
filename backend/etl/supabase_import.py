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

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - dependency guidance, not logic
    sys.exit("psycopg is required: pip install 'psycopg[binary]'")

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = REPO_ROOT / "results.csv"
CIRCUIT_MAP_CSV = Path(__file__).with_name("circuit_map.csv")
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

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
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
                source_id = cur.fetchone()["id"]

                cur.execute(
                    """INSERT INTO datasets
                         (source_id, dataset_key, version, coverage_start, coverage_end, row_count, checksum, description)
                       VALUES (%s,%s,%s,NULL,NULL,NULL,%s,'Race classifications, one row per driver per race')
                       ON CONFLICT (dataset_key, version) DO UPDATE
                         SET checksum = excluded.checksum, imported_at = now()
                       RETURNING id""",
                    (source_id, DATASET_KEY, DATASET_VERSION, checksum(RAW_CSV)),
                )
                dataset_id = cur.fetchone()["id"]

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
