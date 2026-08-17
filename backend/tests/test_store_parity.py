"""The two stores must agree, and this is the only thing that checks it.

WHY COUNTS ARE NOT ENOUGH
-------------------------
SQLite and Postgres are two materialisations of the same source. Matching row
counts prove that the same *number* of rows landed, which is exactly the check
that would pass if every driver's results were attributed to the wrong driver.
These tests compare values, keyed on the identifier that means the same thing
in both stores.

THAT IDENTIFIER IS `slug`
-------------------------
Not the integer id. Integer ids come from a serial sequence in Postgres and
from enumerating sorted slugs in SQLite; they have never matched and are not
meant to. A parity test that joined on id would report differences that are
not differences, and -- worse -- could report agreement by comparing a row
against an unrelated row that happens to share a number.

Skips entirely without SUPABASE_DB_URL, so a fresh clone still runs green.
That skip is a real gap in coverage, not a pass: nothing here has been checked
unless the credentials are present.
"""
from __future__ import annotations

import os

import pytest

# Imported for its side effect: populates os.environ from .env. Without it the
# skip below fires even when credentials are configured, and the suite reports
# "unverified" while the check it describes was available all along.
from backend.app import env as _env  # noqa: F401
from backend.app.db import DB_PATH, connect

psycopg = pytest.importorskip("psycopg", reason="psycopg not installed")

pytestmark = [
    pytest.mark.skipif(
        not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
    ),
    pytest.mark.skipif(
        not os.getenv("SUPABASE_DB_URL"),
        reason="SUPABASE_DB_URL unset -- cross-store parity unverified",
    ),
]


@pytest.fixture(scope="module")
def lite():
    conn = connect()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def pg():
    with psycopg.connect(os.getenv("SUPABASE_DB_URL"), connect_timeout=30) as conn:
        yield conn


def _lite_rows(conn, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql)]


def _pg_rows(conn, sql: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return [tuple(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_entity_slugs_are_the_same_set_in_both_stores(lite, pg):
    """The precondition for every other test in this file.

    If the key spaces differ, nothing below is comparing like with like -- it
    is comparing the intersection and silently ignoring the rest.
    """
    for table in ("drivers", "constructors", "circuits"):
        column = "slug" if table != "circuits" else "circuit_key"
        left = {r[0] for r in _lite_rows(lite, f"SELECT slug FROM {table}")}
        right = {r[0] for r in _pg_rows(pg, f"SELECT {column} FROM {table}")}
        assert left == right, (
            f"{table}: only in sqlite {sorted(left - right)[:5]}, "
            f"only in postgres {sorted(right - left)[:5]}"
        )


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

def test_driver_career_totals_agree(lite, pg):
    """Entries, wins and points per driver, keyed on slug.

    This is the check that would catch results attached to the wrong driver --
    a failure mode that leaves every row count perfect.
    """
    left = _lite_rows(lite, """
        SELECT d.slug, COUNT(*), SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END),
               ROUND(COALESCE(SUM(r.points), 0), 2)
        FROM results r JOIN drivers d ON d.id = r.driver_id
        GROUP BY d.slug ORDER BY d.slug
    """)
    right = _pg_rows(pg, """
        SELECT d.slug, COUNT(*), SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END),
               ROUND(COALESCE(SUM(r.points), 0), 2)::float8
        FROM results r JOIN drivers d ON d.id = r.driver_id
        GROUP BY d.slug ORDER BY d.slug
    """)
    assert len(left) == len(right)
    differences = [(a, b) for a, b in zip(left, right) if a != b]
    assert not differences, f"career totals differ: {differences[:5]}"


def test_every_race_has_the_same_classification_in_both_stores(lite, pg):
    """Position-by-position, for all 503 races.

    Compared as (season, round, position, driver slug). A store that dropped
    or reordered a single result row fails here and nowhere else.
    """
    left = _lite_rows(lite, """
        SELECT ra.season, ra.round, r.position, d.slug
        FROM results r
        JOIN races ra   ON ra.id = r.race_id
        JOIN drivers d  ON d.id  = r.driver_id
        ORDER BY ra.season, ra.round, r.position
    """)
    right = _pg_rows(pg, """
        SELECT s.year, ra.round, r.position, d.slug
        FROM results r
        JOIN races ra   ON ra.id = r.race_id
        JOIN seasons s  ON s.id  = ra.season_id
        JOIN drivers d  ON d.id  = r.driver_id
        ORDER BY s.year, ra.round, r.position
    """)
    assert len(left) == len(right), f"row counts differ: {len(left)} vs {len(right)}"
    differences = [(a, b) for a, b in zip(left, right) if a != b]
    assert not differences, f"classifications differ: {differences[:5]}"


def test_season_points_totals_agree(lite, pg):
    """Championship points per driver per season, race plus sprint.

    The aggregate a reader is most likely to check against an official
    standings table, so a disagreement between stores here is the most visible
    kind there is.
    """
    left = _lite_rows(lite, """
        SELECT ra.season, d.slug, ROUND(SUM(pts), 2) FROM (
            SELECT race_id, driver_id, points AS pts FROM results WHERE points IS NOT NULL
            UNION ALL
            SELECT race_id, driver_id, points FROM sprint_results WHERE points IS NOT NULL
        ) x
        JOIN races ra  ON ra.id = x.race_id
        JOIN drivers d ON d.id  = x.driver_id
        GROUP BY ra.season, d.slug ORDER BY ra.season, d.slug
    """)
    right = _pg_rows(pg, """
        SELECT s.year, d.slug, ROUND(SUM(pts), 2)::float8 FROM (
            SELECT race_id, driver_id, points AS pts FROM results WHERE points IS NOT NULL
            UNION ALL
            SELECT race_id, driver_id, points FROM sprint_results WHERE points IS NOT NULL
        ) x
        JOIN races ra  ON ra.id = x.race_id
        JOIN seasons s ON s.id  = ra.season_id
        JOIN drivers d ON d.id  = x.driver_id
        GROUP BY s.year, d.slug ORDER BY s.year, d.slug
    """)
    assert len(left) == len(right)
    differences = [(a, b) for a, b in zip(left, right) if a != b]
    assert not differences, f"season points differ: {differences[:5]}"


@pytest.mark.parametrize(
    ("table", "lite_sql", "pg_sql"),
    ids=lambda v: v if isinstance(v, str) and " " not in v else "",
    argvalues=[
        (
            "qualifying_results",
            "SELECT ra.season, ra.round, q.position, d.slug FROM qualifying_results q"
            " JOIN races ra ON ra.id = q.race_id JOIN drivers d ON d.id = q.driver_id"
            " ORDER BY 1,2,3,4",
            "SELECT s.year, ra.round, q.position, d.slug FROM qualifying_results q"
            " JOIN races ra ON ra.id = q.race_id JOIN seasons s ON s.id = ra.season_id"
            " JOIN drivers d ON d.id = q.driver_id ORDER BY 1,2,3,4",
        ),
        (
            "sprint_results",
            "SELECT ra.season, ra.round, sr.position, d.slug FROM sprint_results sr"
            " JOIN races ra ON ra.id = sr.race_id JOIN drivers d ON d.id = sr.driver_id"
            " ORDER BY 1,2,3,4",
            "SELECT s.year, ra.round, sr.position, d.slug FROM sprint_results sr"
            " JOIN races ra ON ra.id = sr.race_id JOIN seasons s ON s.id = ra.season_id"
            " JOIN drivers d ON d.id = sr.driver_id ORDER BY 1,2,3,4",
        ),
        (
            "pit_stops",
            "SELECT ra.season, ra.round, d.slug, p.stop, p.lap FROM pit_stops p"
            " JOIN races ra ON ra.id = p.race_id JOIN drivers d ON d.id = p.driver_id"
            " ORDER BY 1,2,3,4",
            "SELECT s.year, ra.round, d.slug, p.stop, p.lap FROM pit_stops p"
            " JOIN races ra ON ra.id = p.race_id JOIN seasons s ON s.id = ra.season_id"
            " JOIN drivers d ON d.id = p.driver_id ORDER BY 1,2,3,4",
        ),
        (
            "sessions",
            "SELECT ra.season, ra.round, se.session, se.date FROM sessions se"
            " JOIN races ra ON ra.id = se.race_id ORDER BY 1,2,3",
            "SELECT s.year, ra.round, se.session, se.date::text FROM sessions se"
            " JOIN races ra ON ra.id = se.race_id JOIN seasons s ON s.id = ra.season_id"
            " ORDER BY 1,2,3",
        ),
        (
            "practice_laps",
            "SELECT ra.season, ra.round, p.session, d.slug, p.lap, p.lap_time,"
            " p.compound, p.is_accurate, p.deleted"
            " FROM practice_laps p JOIN races ra ON ra.id = p.race_id"
            " JOIN drivers d ON d.id = p.driver_id ORDER BY 1,2,3,4,5",
            "SELECT s.year, ra.round, p.session, d.slug, p.lap, p.lap_time::float8,"
            " p.compound, p.is_accurate::int, p.deleted::int"
            " FROM practice_laps p JOIN races ra ON ra.id = p.race_id"
            " JOIN seasons s ON s.id = ra.season_id"
            " JOIN drivers d ON d.id = p.driver_id ORDER BY 1,2,3,4,5",
        ),
        (
            "lap_times",
            "SELECT ra.season, ra.round, d.slug, l.lap, l.time_ms FROM lap_times l"
            " JOIN races ra ON ra.id = l.race_id JOIN drivers d ON d.id = l.driver_id"
            " ORDER BY 1,2,3,4",
            "SELECT s.year, ra.round, d.slug, l.lap, l.time_ms FROM lap_times l"
            " JOIN races ra ON ra.id = l.race_id JOIN seasons s ON s.id = ra.season_id"
            " JOIN drivers d ON d.id = l.driver_id ORDER BY 1,2,3,4",
        ),
    ],
)
def test_secondary_datasets_agree(lite, pg, table, lite_sql, pg_sql):
    """Every dataset beyond race results, compared row for row.

    Parametrised so a failure names the table rather than the first mismatch
    across all of them.

    Every ORDER BY includes the driver slug, not just (season, round,
    position). That is not belt-and-braces: qualifying genuinely carries
    duplicate positions -- the source reports two drivers at P15 at
    Silverstone 2023 and in five other sessions -- so position alone is not a
    unique sort key, and the two databases are free to break the tie
    differently. Without the tiebreaker this test reported a difference where
    the stores hold identical data. See test_data.py for the check that keeps
    the underlying source defect visible.
    """
    left = _lite_rows(lite, lite_sql)
    right = _pg_rows(pg, pg_sql)
    assert len(left) == len(right), f"{table}: {len(left)} rows in sqlite, {len(right)} in postgres"
    differences = [(a, b) for a, b in zip(left, right) if a != b]
    assert not differences, f"{table} differs: {differences[:5]}"
