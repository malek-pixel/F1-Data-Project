"""Integrity tests against the real built database.

These guard the pipeline: if results.csv or the circuit map changes in a way
that breaks a relationship, these fail rather than the UI silently showing a
wrong number.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from backend.app.db import DB_PATH, connect
from backend.etl.build import RAW_CSV

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
)


@pytest.fixture(scope="module")
def conn():
    db = connect()
    yield db
    db.close()


def test_every_source_row_is_loaded(conn):
    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        source_rows = sum(1 for _ in csv.DictReader(handle))
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == source_rows


def test_coverage_is_2000_to_2025(conn):
    lo, hi = conn.execute("SELECT MIN(season), MAX(season) FROM races").fetchone()
    assert (lo, hi) == (2000, 2025)


def test_entity_counts(conn):
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("drivers", "constructors", "circuits", "races")
    }
    assert counts == {"drivers": 129, "constructors": 38, "circuits": 39, "races": 503}


def test_no_orphaned_results(conn):
    orphans = conn.execute(
        """
        SELECT COUNT(*) FROM results r
        LEFT JOIN races ra        ON ra.id = r.race_id
        LEFT JOIN drivers d       ON d.id  = r.driver_id
        LEFT JOIN constructors c  ON c.id  = r.constructor_id
        WHERE ra.id IS NULL OR d.id IS NULL OR c.id IS NULL
        """
    ).fetchone()[0]
    assert orphans == 0


def test_every_race_maps_to_a_circuit(conn):
    assert conn.execute("SELECT COUNT(*) FROM races WHERE circuit_id IS NULL").fetchone()[0] == 0


def test_positions_are_within_range(conn):
    lo, hi = conn.execute("SELECT MIN(position), MAX(position) FROM results").fetchone()
    assert lo == 1
    assert hi <= 40


def test_exactly_one_winner_per_race(conn):
    bad = conn.execute(
        "SELECT COUNT(*) FROM (SELECT race_id FROM results WHERE position = 1 GROUP BY race_id HAVING COUNT(*) != 1)"
    ).fetchone()[0]
    assert bad == 0


def test_no_driver_appears_twice_in_one_race(conn):
    bad = conn.execute(
        "SELECT COUNT(*) FROM (SELECT race_id, driver_id FROM results GROUP BY race_id, driver_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    assert bad == 0


def test_each_season_has_a_contiguous_round_sequence(conn):
    for (season,) in conn.execute("SELECT DISTINCT season FROM races"):
        rounds = [r[0] for r in conn.execute("SELECT round FROM races WHERE season = ? ORDER BY round", [season])]
        assert rounds == list(range(1, len(rounds) + 1)), f"season {season} has gaps: {rounds}"


def test_race_dates_fall_in_their_season(conn):
    bad = conn.execute(
        "SELECT COUNT(*) FROM races WHERE CAST(SUBSTR(date, 1, 4) AS INTEGER) != season"
    ).fetchone()[0]
    assert bad == 0


def test_circuits_without_a_map_are_flagged_not_hidden(conn):
    """Circuits with no SVG must still exist as entities -- the UI shows a
    map-unavailable state rather than dropping the circuit."""
    total, mapped = conn.execute("SELECT COUNT(*), SUM(has_map) FROM circuits").fetchone()
    assert total == 39
    assert 0 < mapped < total


def test_double_header_winners_are_ordered_deterministically(conn):
    """A circuit can host two races in one season, so season alone is not a
    total order. Silverstone 2020 ran the British GP (R4) and the 70th
    Anniversary GP (R5); the Red Bull Ring did the same in 2020 and 2021."""
    from backend.app import analytics

    silverstone = conn.execute("SELECT id FROM circuits WHERE slug = 'silverstone'").fetchone()[0]
    winners = analytics.circuit_winners(conn, silverstone)

    seasons = [row["season"] for row in winners]
    assert seasons == sorted(seasons, reverse=True), "winners must be newest-first"

    in_2020 = [row["race_name"] for row in winners if row["season"] == 2020]
    # Descending by round: the later race (70th Anniversary, R5) comes first.
    assert in_2020 == ["70th Anniversary Grand Prix", "British Grand Prix"]


def test_database_is_read_only(conn):
    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM results")


def test_no_hardcoded_season_span_in_user_facing_strings():
    """No string the API can emit may state the coverage window as a literal.

    A span baked into a methodology string is correct only until the next
    ingestion, after which it silently describes the wrong window -- worse than
    stating no window at all. `analytics.coverage_span()` and
    `analytics.qualifying_coverage_from()` read it from the data instead.

    Scoped to strings that can REACH A USER, via the AST rather than a line
    scan. Comments and docstrings are excluded deliberately: they document
    findings, and a finding like "totals were short from 2021" is evidence
    whose whole value is the specific year. Only runtime string values are
    capable of shipping a stale claim to a client.
    """
    import ast
    import re

    app_dir = Path(__file__).resolve().parents[1] / "app"
    span = re.compile(r"\b(19|20)\d{2}\s*-\s*(19|20)\d{2}\b")

    offenders = []
    for path in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # Collect docstring nodes so they can be skipped by identity.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    if isinstance(body[0].value.value, str):
                        docstrings.add(id(body[0].value))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if span.search(node.value):
                offenders.append(
                    f"{path.relative_to(app_dir)}:{node.lineno}: {node.value.strip()[:80]}"
                )

    assert not offenders, (
        "hardcoded season span in a user-facing string; derive it instead:\n"
        + "\n".join(offenders)
    )


def test_coverage_span_matches_the_data(conn):
    from backend.app import analytics

    lo, hi = conn.execute("SELECT MIN(season), MAX(season) FROM races").fetchone()
    assert analytics.coverage_span(conn) == f"{lo}-{hi}"
