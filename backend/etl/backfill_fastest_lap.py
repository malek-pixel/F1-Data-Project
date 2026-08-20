"""Load the fastest-lap enrichment into Postgres.

WHY THIS EXISTS
---------------
`results` in the SQLite build carries fastest_lap_rank / _number / _time /
_speed. The Postgres table did not have the columns at all, so the two stores
held different data while both claiming to be materialisations of the same
CSV. Migration 24 adds the columns; this loads the values.

KEYED ON THE NATURAL KEY, NEVER ON IDS
--------------------------------------
A result is addressed as (season, round, driver slug). Result ids come from a
different sequence in each store, so matching on `results.id` would write each
value onto an unrelated row -- silently, and in a way no row count would
reveal.

Idempotent: it UPDATEs by natural key, so running it twice writes the same
values. Rows the source has no fastest lap for are left NULL rather than
zeroed; before 2004 the source publishes none at all.

Run:  python -m backend.etl.backfill_fastest_lap
      python -m backend.etl.backfill_fastest_lap --check   (verify only)
"""

from __future__ import annotations

import os
import sys

import psycopg

from backend.app import env  # noqa: F401  (loads .env)
from backend.app.db import connect

BATCH = 1000


def rows_from_sqlite() -> list[tuple]:
    """(season, round, driver_slug, rank, number, time, speed) for enriched rows."""
    conn = connect()
    try:
        return [
            (
                row["season"], row["round"], row["slug"],
                row["fastest_lap_rank"], row["fastest_lap_number"],
                row["fastest_lap_time"], row["fastest_lap_speed"],
            )
            for row in conn.execute(
                """
                SELECT ra.season, ra.round, d.slug,
                       r.fastest_lap_rank, r.fastest_lap_number,
                       r.fastest_lap_time, r.fastest_lap_speed
                FROM results r
                JOIN races ra   ON ra.id = r.race_id
                JOIN drivers d  ON d.id  = r.driver_id
                WHERE r.fastest_lap_rank IS NOT NULL
                """
            )
        ]
    finally:
        conn.close()


UPDATE = """
    UPDATE results r
       SET fastest_lap_rank   = %(rank)s,
           fastest_lap_number = %(number)s,
           fastest_lap_time   = %(time)s,
           fastest_lap_speed  = %(speed)s
      FROM races ra
      JOIN seasons s ON s.id = ra.season_id
      JOIN drivers d ON d.slug = %(slug)s
     WHERE r.race_id = ra.id
       AND r.driver_id = d.id
       AND s.year = %(season)s
       AND ra.round = %(round)s
"""


def load(rows: list[tuple]) -> int:
    """UPDATE one row at a time via executemany.

    psycopg3 has no cursor.mogrify, and building a VALUES list by hand is how
    SQL gets concatenated by accident. 8,725 parameterised statements in one
    transaction is fast enough and keeps every value bound.
    """
    params = [
        {"season": r[0], "round": r[1], "slug": r[2],
         "rank": r[3], "number": r[4], "time": r[5], "speed": r[6]}
        for r in rows
    ]
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=60) as conn:
        with conn.cursor() as cur:
            cur.executemany(UPDATE, params)
        conn.commit()
    return len(params)


def check() -> tuple[int, int]:
    """(rows enriched in Postgres, rows enriched in SQLite)."""
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(fastest_lap_rank) FROM results")
            there = cur.fetchone()[0]
    conn2 = connect()
    try:
        here = conn2.execute("SELECT COUNT(fastest_lap_rank) AS n FROM results").fetchone()["n"]
    finally:
        conn2.close()
    return there, here


def main() -> int:
    if "--check" not in sys.argv:
        rows = rows_from_sqlite()
        print(f"loading {len(rows)} enriched rows")
        print(f"updated {load(rows)} rows")

    there, here = check()
    print(f"postgres: {there}   sqlite: {here}")
    if there != here:
        print("MISMATCH -- the two stores do not agree on how many rows are enriched")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
