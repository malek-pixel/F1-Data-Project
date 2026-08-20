"""Analytics tests against a hand-built fixture with known answers.

Deliberately not run against the real database: these assert that the
formulas are correct, which requires numbers verifiable by hand.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.app import analytics
from backend.etl.build import SCHEMA, slugify as slug

# Two seasons, two races each, three drivers, two constructors.
#
#   ALICE (Red)  : P1, P1, P2, P4  -> 4 entries, 2 wins, 3 podiums, avg 2.0
#   BOB   (Red)  : P2, P3, P1, P1  -> 4 entries, 2 wins, 4 podiums, avg 1.75
#   CARA  (Blue) : P3, P2, P3, P2  -> 4 entries, 0 wins, 4 podiums, avg 2.5
FIXTURE = [
    # (season, round, position, driver, constructor)
    (2020, 1, 1, "ALICE", "Red"), (2020, 1, 2, "BOB", "Red"), (2020, 1, 3, "CARA", "Blue"),
    (2020, 2, 1, "ALICE", "Red"), (2020, 2, 3, "BOB", "Red"), (2020, 2, 2, "CARA", "Blue"),
    (2021, 1, 2, "ALICE", "Red"), (2021, 1, 1, "BOB", "Red"), (2021, 1, 3, "CARA", "Blue"),
    (2021, 2, 4, "ALICE", "Red"), (2021, 2, 1, "BOB", "Red"), (2021, 2, 2, "CARA", "Blue"),
]


@pytest.fixture
def conn() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.execute("INSERT INTO circuits (id, slug, name, country, has_map) VALUES (1, 'test', 'Test Circuit', 'Testland', 1)")

    drivers = {name: i for i, name in enumerate(["ALICE", "BOB", "CARA"], start=1)}
    constructors = {name: i for i, name in enumerate(["Blue", "Red"], start=1)}
    races = {}
    db.executemany("INSERT INTO drivers (id, slug, name) VALUES (?, ?, ?)",
                   [(i, slug(n), n) for n, i in drivers.items()])
    db.executemany("INSERT INTO constructors (id, slug, name) VALUES (?, ?, ?)",
                   [(i, slug(n), n) for n, i in constructors.items()])

    for season, rnd, _, _, _ in FIXTURE:
        if (season, rnd) not in races:
            races[(season, rnd)] = len(races) + 1
            db.execute(
                "INSERT INTO races (id, season, round, name, date, circuit_id) VALUES (?, ?, ?, ?, ?, 1)",
                (races[(season, rnd)], season, rnd, f"R{rnd}", f"{season}-01-0{rnd}"),
            )
    db.executemany(
        "INSERT INTO results (race_id, driver_id, constructor_id, position) VALUES (?, ?, ?, ?)",
        [(races[(s, r)], drivers[d], constructors[c], p) for s, r, p, d, c in FIXTURE],
    )
    db.commit()
    return db


ALICE, BOB, CARA = 1, 2, 3
BLUE, RED = 1, 2


def test_career_stats_match_hand_calculation(conn):
    stats = analytics.entity_stats(conn, "driver", ALICE)
    assert stats["entries"] == 4
    assert stats["wins"] == 2
    assert stats["podiums"] == 3
    assert stats["win_rate"] == 0.5
    assert stats["podium_rate"] == 0.75
    assert stats["avg_classified_position"] == 2.0
    assert stats["best_classified_position"] == 1


def test_avg_position_counts_every_entry_not_just_finishes(conn):
    # BOB: (2 + 3 + 1 + 1) / 4 = 1.75
    assert analytics.entity_stats(conn, "driver", BOB)["avg_classified_position"] == 1.75


def test_podium_includes_third_place(conn):
    # CARA never wins but is classified P2/P3 every time.
    stats = analytics.entity_stats(conn, "driver", CARA)
    assert stats["wins"] == 0
    assert stats["podiums"] == 4
    assert stats["podium_rate"] == 1.0


def test_rates_are_none_not_zero_when_no_entries(conn):
    stats = analytics.entity_stats(conn, "driver", ALICE, season_from=1999, season_to=1999)
    assert stats["entries"] == 0
    assert stats["win_rate"] is None
    assert stats["avg_classified_position"] is None


def test_rates_flagged_unreliable_below_threshold(conn):
    # 4 entries is under MIN_ENTRIES_FOR_RATES, so the rate is returned but flagged.
    stats = analytics.entity_stats(conn, "driver", ALICE)
    assert stats["win_rate"] == 0.5
    assert stats["rates_reliable"] is False


def test_season_filter_narrows_the_window(conn):
    stats = analytics.entity_stats(conn, "driver", ALICE, season_from=2020, season_to=2020)
    assert stats["entries"] == 2
    assert stats["wins"] == 2
    assert stats["win_rate"] == 1.0


def test_by_season_splits_correctly(conn):
    seasons = analytics.by_season(conn, "driver", ALICE)
    assert [s["season"] for s in seasons] == [2020, 2021]
    assert [s["wins"] for s in seasons] == [2, 0]


def test_constructor_aggregates_both_its_drivers(conn):
    stats = analytics.entity_stats(conn, "constructor", RED)
    assert stats["entries"] == 8       # ALICE 4 + BOB 4
    assert stats["wins"] == 4          # every race was won by a Red driver
    assert stats["podiums"] == 7


def test_driver_contribution_shares_sum_to_one(conn):
    rows = analytics.constructor_driver_contribution(conn, RED)
    assert {r["driver_name"] for r in rows} == {"ALICE", "BOB"}
    assert sum(r["entry_share"] for r in rows) == pytest.approx(1.0)
    assert sum(r["win_share"] for r in rows) == pytest.approx(1.0)


def test_win_share_is_none_when_constructor_has_no_wins(conn):
    rows = analytics.constructor_driver_contribution(conn, BLUE)
    assert rows[0]["win_share"] is None       # Blue never won -- not 0.0, not a crash
    assert rows[0]["entry_share"] == 1.0


def test_leaderboard_orders_by_wins_then_podiums(conn):
    items = analytics.leaderboard(conn, "driver", sort="wins")["items"]
    # ALICE and BOB both have 2 wins; BOB has more podiums so ranks first.
    assert [i["name"] for i in items] == ["BOB", "ALICE", "CARA"]


def test_leaderboard_avg_position_sorts_ascending(conn):
    items = analytics.leaderboard(conn, "driver", sort="avg_position")["items"]
    assert [i["name"] for i in items] == ["BOB", "ALICE", "CARA"]


@pytest.mark.parametrize("sort", list(analytics._LEADERBOARD_SORTS))
@pytest.mark.parametrize("entity", ["driver", "constructor"])
def test_every_sort_key_executes(conn, entity, sort):
    """Each advertised sort must actually run.

    `sort=name` shipped broken: the query joins `races`, which also has a
    `name` column, so the unqualified ORDER BY was ambiguous and SQLite
    rejected the statement -- a 503 for anyone choosing "Name (A-Z)".
    Parametrised over the real dict so a new sort key cannot be added
    without a test.
    """
    page = analytics.leaderboard(conn, entity, sort=sort, limit=5)
    assert page["total"] > 0
    assert len(page["items"]) > 0


def test_name_sort_is_alphabetical(conn):
    items = analytics.leaderboard(conn, "driver", sort="name")["items"]
    assert [i["name"] for i in items] == ["ALICE", "BOB", "CARA"]


def test_leaderboard_min_entries_excludes_small_samples(conn):
    page = analytics.leaderboard(conn, "driver", min_entries=5)
    assert page["total"] == 0


def test_leaderboard_pagination_reports_unfiltered_total(conn):
    page = analytics.leaderboard(conn, "driver", limit=1, offset=1)
    assert page["total"] == 3
    assert len(page["items"]) == 1
    assert page["items"][0]["name"] == "ALICE"


def test_search_wildcards_are_escaped_not_executed(conn):
    # '%' must be treated as a literal, otherwise it would match everything.
    assert analytics.leaderboard(conn, "driver", search="%")["total"] == 0
    assert analytics.leaderboard(conn, "driver", search="ALI")["total"] == 1


def test_compare_reports_shared_seasons(conn):
    result = analytics.compare(conn, "driver", ALICE, BOB)
    assert result["shared_seasons"] == [2020, 2021]
    assert result["left"]["wins"] == 2
    # Under the entry threshold, so not declared comparable.
    assert result["comparable"] is False


def test_season_summary_is_wins_based_not_points_based(conn):
    summary = analytics.season_summary(conn, 2020)
    assert summary["ranking_basis"] == "wins"
    assert summary["races"] == 2
    assert summary["drivers"][0]["name"] == "ALICE"   # 2 wins in 2020


def test_season_summary_returns_none_for_unknown_season(conn):
    assert analytics.season_summary(conn, 1999) is None
