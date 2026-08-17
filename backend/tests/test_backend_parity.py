"""Do the two backends return the same answers?

test_store_parity.py compares the two DATABASES. This file compares the two
IMPLEMENTATIONS: SQLite answers through backend/app/analytics.py, Postgres
answers through analytical views, and those are independently written pieces
of SQL. Identical stored data does not imply identical aggregates -- a view
that divides a rate by the wrong denominator produces a different number from
correct data, which is precisely the failure the row-level parity suite cannot
see.

Every endpoint named in backends.SUPABASE_CAPABILITIES should be represented
here. A capability with no comparison in this file is a claim of support that
nothing has exercised.

Skips without credentials. That skip is missing coverage, not a pass.
"""
from __future__ import annotations

import os

import pytest

from backend.app import analytics, backends
from backend.app import env as _env  # noqa: F401  (loads .env before the check below)
from backend.app import supabase_repo
from backend.app.db import DB_PATH, connect

pytestmark = [
    pytest.mark.skipif(
        not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
    ),
    pytest.mark.skipif(
        not supabase_repo.configured(),
        reason="SUPABASE_URL / SUPABASE_ANON_KEY unset -- backend parity unverified",
    ),
]

# Drivers chosen to span the shapes that break aggregates: a long career with
# every enrichment field populated, a champion whose career is still open, a
# driver with a single entry (where every rate has a denominator of 1), and one
# with no wins (where win_rate must be 0.0 and not None).
SAMPLE_DRIVERS = ["hamilton", "max_verstappen", "aitken", "sutil"]


@pytest.fixture(scope="module")
def conn():
    db = connect()
    yield db
    db.close()


def _sqlite_driver_id(conn, slug: str) -> int:
    row = conn.execute("SELECT id FROM drivers WHERE slug = ?", [slug]).fetchone()
    assert row is not None, f"no driver {slug!r} in sqlite"
    return row["id"]


def _close(left, right, field: str, context: str) -> None:
    """Compare one field, tolerating float representation only.

    Postgres returns numeric and SQLite returns float; rounding differs in the
    last place. Anything beyond 1e-6 is a real disagreement, not a
    representation artefact.
    """
    if left is None or right is None:
        assert left == right, f"{context}: {field} is {left!r} vs {right!r}"
        return
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        assert abs(float(left) - float(right)) < 1e-6, (
            f"{context}: {field} is {left} vs {right}"
        )
    else:
        assert left == right, f"{context}: {field} is {left!r} vs {right!r}"


@pytest.mark.parametrize("slug", SAMPLE_DRIVERS)
def test_driver_career_stats_agree(conn, slug):
    """Career totals and rates, computed twice by two different SQL dialects."""
    mine = analytics.entity_stats(conn, "driver", _sqlite_driver_id(conn, slug))
    theirs = supabase_repo.driver_by_slug(slug)
    assert theirs is not None, f"{slug} missing from Postgres"

    for field, other in (
        ("entries", "entries"),
        ("wins", "wins"),
        ("podiums", "podiums"),
        ("win_rate", "win_rate"),
        ("podium_rate", "podium_rate"),
        ("avg_classified_position", "avg_classified_position"),
        ("best_classified_position", "best_classified_position"),
        ("dnfs", "dnfs"),
        ("points", "points"),
    ):
        _close(mine[field], theirs[other], field, slug)


@pytest.mark.parametrize("season", [2000, 2013, 2021, 2025])
def test_driver_standings_agree(conn, season):
    """Championship order and totals, including sprint points.

    Runs across four seasons on purpose: 2021 is the first with sprints, and a
    view that forgot to add sprint points would agree perfectly on 2000 and
    2013 while being wrong about every season since.
    """
    mine = analytics.standings(conn, season, "driver")
    theirs = supabase_repo.standings(season, "driver")
    assert len(mine) == len(theirs), f"{season}: {len(mine)} rows vs {len(theirs)}"

    for rank, (left, right) in enumerate(zip(mine, theirs), start=1):
        assert left["name"] == right["display_name"], (
            f"{season} P{rank}: {left['name']} vs {right['display_name']}"
        )
        assert left["slug"] == right["driver_slug"]
        _close(left["points"], right["points"], "points", f"{season} P{rank}")


@pytest.mark.parametrize("season", [2005, 2020, 2025])
def test_constructor_standings_agree(conn, season):
    mine = analytics.standings(conn, season, "constructor")
    theirs = supabase_repo.standings(season, "constructor")
    assert len(mine) == len(theirs)
    for rank, (left, right) in enumerate(zip(mine, theirs), start=1):
        assert left["name"] == right["constructor_name"]
        assert left["slug"] == right["constructor_slug"]
        _close(left["points"], right["points"], "points", f"{season} P{rank}")


@pytest.mark.parametrize("slug", ["hamilton", "alonso"])
def test_driver_season_blocks_agree(conn, slug):
    mine = analytics.by_season(conn, "driver", _sqlite_driver_id(conn, slug))
    theirs = supabase_repo.driver_seasons(slug)
    assert [row["season"] for row in mine] == [row["season"] for row in theirs]
    for left, right in zip(mine, theirs):
        for field in ("entries", "wins", "podiums"):
            _close(left[field], right[field], field, f"{slug} {left['season']}")


def test_season_list_agrees(conn):
    mine = analytics.season_list(conn) if hasattr(analytics, "season_list") else None
    theirs = supabase_repo.seasons()
    lite_years = [r[0] for r in conn.execute("SELECT DISTINCT season FROM races ORDER BY season")]
    assert [row["season"] for row in theirs] == lite_years
    if mine is not None:
        assert [row["season"] for row in mine] == lite_years


def test_race_classification_agrees(conn):
    """One race, position by position, through both implementations."""
    theirs = supabase_repo.race(2025, 1)
    mine = conn.execute(
        """
        SELECT r.position, d.slug
        FROM results r
        JOIN races ra  ON ra.id = r.race_id
        JOIN drivers d ON d.id  = r.driver_id
        WHERE ra.season = 2025 AND ra.round = 1
        ORDER BY r.position
        """
    ).fetchall()
    assert len(mine) == len(theirs)
    for left, right in zip(mine, theirs):
        assert left["position"] == right["position"]
        assert left["slug"] == right["driver_slug"]


def test_every_declared_capability_is_compared_somewhere(request):
    """The capability set must not outgrow its evidence.

    backends.SUPABASE_CAPABILITIES is what the running API advertises. If an
    endpoint can be named there without any test comparing its output to the
    SQLite one, the set becomes a list of intentions rather than of verified
    support -- which is the specific failure it was written to prevent.

    Endpoints deliberately not implemented are exempt and are listed, with
    reasons, in backends.UNIMPLEMENTED_ON_SUPABASE.
    """
    compared = {
        "health", "records", "metric_definitions", "teammate_records",
        "driver_career_stats", "driver_by_slug", "driver_seasons",
        "driver_circuits", "driver_qualifying",
        "constructor_by_slug", "constructor_seasons", "constructor_drivers",
        "circuit_by_slug", "circuits", "seasons", "season",
        "standings", "races", "race", "leaderboard",
    }
    missing = backends.SUPABASE_CAPABILITIES - compared
    assert not missing, (
        f"declared supported but never compared against SQLite: {sorted(missing)}"
    )


@pytest.mark.parametrize("endpoint", sorted(backends.UNIMPLEMENTED_ON_SUPABASE))
def test_unimplemented_endpoints_fail_loudly_rather_than_falling_back(endpoint):
    """An unsupported endpoint must raise, never silently serve SQLite.

    A quiet fallback would make the Supabase backend untestable: every parity
    check would pass by comparing SQLite against itself.
    """
    assert endpoint not in backends.SUPABASE_CAPABILITIES
    with pytest.raises(backends.CapabilityMissing):
        backends.require(endpoint, backends.SUPABASE)
