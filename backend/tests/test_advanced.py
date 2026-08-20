"""Advanced analytics tests against a hand-built fixture.

Answers below are computed by hand in the comments so a reviewer can verify
the expectation without running the code -- the point of a fixture test is
that the expected value does not come from the implementation.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.app import advanced
from backend.etl.build import SCHEMA, slugify as slug

# Two constructors, four drivers, two seasons of two races each.
#
# RED: ALICE + BOB are teammates in all 4 races.
#   race  ALICE  BOB      ahead
#   2020a   1      2      ALICE (+1)
#   2020b   1      3      ALICE (+2)
#   2021a   2      1      BOB   (-1)
#   2021b   4      1      BOB   (-3)
#   ALICE vs BOB: shared 4, ahead 2, delta = (1+2-1-3)/4 = -0.25
#
# BLUE: CARA all 4 races; DAN only 2021 (mid-season style partial spell).
#   race  CARA  DAN
#   2020a   3    -
#   2020b   2    -
#   2021a   3    5
#   2021b   2    6
#   CARA vs DAN: shared 2, ahead 2, delta = (5-3 + 6-2)/2 = 3.0
FIXTURE = [
    (2020, 1, 1, "ALICE", "Red"), (2020, 1, 2, "BOB", "Red"), (2020, 1, 3, "CARA", "Blue"),
    (2020, 2, 1, "ALICE", "Red"), (2020, 2, 3, "BOB", "Red"), (2020, 2, 2, "CARA", "Blue"),
    (2021, 1, 2, "ALICE", "Red"), (2021, 1, 1, "BOB", "Red"), (2021, 1, 3, "CARA", "Blue"),
    (2021, 1, 5, "DAN", "Blue"),
    (2021, 2, 4, "ALICE", "Red"), (2021, 2, 1, "BOB", "Red"), (2021, 2, 2, "CARA", "Blue"),
    (2021, 2, 6, "DAN", "Blue"),
]

ALICE, BOB, CARA, DAN = 1, 2, 3, 4
BLUE, RED = 1, 2


@pytest.fixture
def conn() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    # Two circuits so circuit-level metrics have something to separate.
    db.execute("INSERT INTO circuits (id, slug, name, country, has_map) VALUES (1, 'alpha', 'Alpha Circuit', 'Testland', 1)")
    db.execute("INSERT INTO circuits (id, slug, name, country, has_map) VALUES (2, 'beta', 'Beta Circuit', 'Testland', 0)")

    drivers = {n: i for i, n in enumerate(["ALICE", "BOB", "CARA", "DAN"], start=1)}
    constructors = {n: i for i, n in enumerate(["Blue", "Red"], start=1)}
    db.executemany("INSERT INTO drivers (id, slug, name) VALUES (?, ?, ?)",
                   [(i, slug(n), n) for n, i in drivers.items()])
    db.executemany("INSERT INTO constructors (id, slug, name) VALUES (?, ?, ?)",
                   [(i, slug(n), n) for n, i in constructors.items()])

    races = {}
    for season, rnd, _, _, _ in FIXTURE:
        if (season, rnd) not in races:
            races[(season, rnd)] = len(races) + 1
            db.execute(
                "INSERT INTO races (id, season, round, name, date, circuit_id) VALUES (?, ?, ?, ?, ?, ?)",
                (races[(season, rnd)], season, rnd, f"R{rnd}", f"{season}-01-0{rnd}", rnd),
            )
    db.executemany(
        "INSERT INTO results (race_id, driver_id, constructor_id, position) VALUES (?, ?, ?, ?)",
        [(races[(s, r)], drivers[d], constructors[c], p) for s, r, p, d, c in FIXTURE],
    )
    db.commit()
    return db


# --------------------------------------------------------------------------
# Teammate analysis
# --------------------------------------------------------------------------

def test_teammate_head_to_head_matches_hand_count(conn):
    spell = advanced.teammate_records(conn, ALICE)[0]
    assert spell["teammate_name"] == "BOB"
    assert spell["shared_races"] == 4
    assert spell["ahead"] == 2      # 2020a, 2020b
    assert spell["behind"] == 2     # 2021a, 2021b
    assert spell["h2h_rate"] == 0.5


def test_teammate_position_delta_is_signed_correctly(conn):
    """Positive delta means finishing ahead. ALICE nets -0.25 against BOB."""
    alice = advanced.teammate_records(conn, ALICE)[0]
    assert alice["avg_position_delta"] == -0.25
    # And BOB's mirror must be the exact negation.
    bob = advanced.teammate_records(conn, BOB)[0]
    assert bob["avg_position_delta"] == 0.25


def test_teammate_records_are_symmetric(conn):
    alice = advanced.teammate_records(conn, ALICE)[0]
    bob = advanced.teammate_records(conn, BOB)[0]
    assert alice["ahead"] == bob["behind"]
    assert alice["behind"] == bob["ahead"]
    assert alice["shared_races"] == bob["shared_races"]


def test_only_shared_races_are_counted(conn):
    """CARA ran 4 races, DAN only 2. The pairing must count 2, not 4 --
    this is what stops unequal season lengths distorting the ratio."""
    spell = advanced.teammate_records(conn, CARA)[0]
    assert spell["teammate_name"] == "DAN"
    assert spell["shared_races"] == 2
    assert spell["ahead"] == 2
    assert spell["avg_position_delta"] == 3.0


def test_teammates_split_by_constructor_not_merged(conn):
    """A pairing is (teammate, constructor). Spells at different teams are
    different samples and must not be pooled."""
    for driver in (ALICE, BOB, CARA, DAN):
        spells = advanced.teammate_records(conn, driver)
        keys = [(s["teammate_id"], s["constructor_id"]) for s in spells]
        assert len(keys) == len(set(keys))


def test_driver_with_no_teammate_returns_empty(conn):
    conn.execute("INSERT INTO drivers (id, slug, name) VALUES (99, 'solo', 'SOLO')")
    assert advanced.teammate_records(conn, 99) == []


def test_teammate_summary_excludes_short_spells(conn):
    """DAN's 2-race spell is under MIN_SHARED_RACES, so it is excluded from
    CARA's totals and reported separately rather than silently dropped."""
    summary = advanced.teammate_summary(conn, CARA)
    assert summary["shared_races"] == 0
    assert summary["h2h_rate"] is None
    assert summary["excluded_short_spells"] == 1


def test_comparable_flag_tracks_the_threshold(conn):
    assert advanced.MIN_SHARED_RACES == 5
    assert advanced.teammate_records(conn, ALICE)[0]["comparable"] is False  # 4 shared
    assert advanced.teammate_records(conn, CARA)[0]["comparable"] is False   # 2 shared


# --------------------------------------------------------------------------
# Distribution
# --------------------------------------------------------------------------

def test_distribution_median_and_spread(conn):
    # ALICE positions: 1, 1, 2, 4 -> median (1+2)/2 = 1.5
    dist = advanced.distribution(conn, driver_id=ALICE)
    assert dist["entries"] == 4
    assert dist["median"] == 1.5
    assert dist["worst"] == 4


def test_spread_is_withheld_below_the_threshold(conn):
    """4 entries is under MIN_ENTRIES_FOR_SPREAD, so stdev is None rather
    than a number computed from too little data."""
    assert advanced.MIN_ENTRIES_FOR_SPREAD == 5
    dist = advanced.distribution(conn, driver_id=ALICE)
    assert dist["stdev"] is None
    assert dist["iqr"] is None
    assert dist["spread_reliable"] is False


def test_histogram_partitions_every_entry_exactly_once(conn):
    for driver in (ALICE, BOB, CARA, DAN):
        dist = advanced.distribution(conn, driver_id=driver)
        assert sum(b["count"] for b in dist["histogram"]) == dist["entries"]
        assert sum(b["share"] for b in dist["histogram"]) == pytest.approx(1.0)


def test_distribution_of_nothing_is_null_not_zero(conn):
    dist = advanced.distribution(conn, driver_id=ALICE, season=1999)
    assert dist["entries"] == 0
    assert dist["median"] is None
    assert dist["stdev"] is None


def test_distribution_can_be_scoped_to_a_season(conn):
    # ALICE in 2020 only: positions 1, 1
    dist = advanced.distribution(conn, driver_id=ALICE, season=2020)
    assert dist["entries"] == 2
    assert dist["median"] == 1.0


# --------------------------------------------------------------------------
# Circuit specialisation
# --------------------------------------------------------------------------

def test_circuit_delta_is_relative_to_the_driver_own_career(conn):
    # ALICE career mean = (1+1+2+4)/4 = 2.0.
    # Circuit 1 (round 1 races): positions 1, 2 -> mean 1.5 -> delta +0.5
    profile = {c["circuit_id"]: c for c in advanced.circuit_profile(conn, ALICE)}
    assert profile[1]["avg_classified_position"] == 1.5
    assert profile[1]["delta_vs_career"] == 0.5
    # Circuit 2: positions 1, 4 -> mean 2.5 -> delta -0.5
    assert profile[2]["delta_vs_career"] == -0.5


def test_circuit_threshold_flag_is_reported_not_enforced(conn):
    """Below-threshold circuits are still returned, flagged, so the UI can
    show the record while withholding 'specialist' language."""
    profile = advanced.circuit_profile(conn, ALICE)
    assert all(c["appearances"] == 2 for c in profile)
    assert all(c["meets_threshold"] is False for c in profile)


def test_circuit_specialists_respects_min_appearances(conn):
    assert advanced.circuit_specialists(conn, 1, min_appearances=5) == []
    assert len(advanced.circuit_specialists(conn, 1, min_appearances=1)) > 0


def test_circuit_profile_of_unknown_driver_is_empty(conn):
    assert advanced.circuit_profile(conn, 999) == []


# --------------------------------------------------------------------------
# Season dominance
# --------------------------------------------------------------------------

def test_win_share_is_normalised_by_races_held(conn):
    # 2020: 2 races, ALICE won both -> 1.0
    dom = advanced.season_dominance(conn, 2020)
    assert dom["races"] == 2
    assert dom["top_driver_win_share"] == 1.0
    assert dom["distinct_driver_winners"] == 1


def test_dominance_counts_distinct_winners(conn):
    # 2021: BOB won both races -> one distinct winner
    dom = advanced.season_dominance(conn, 2021)
    assert dom["distinct_driver_winners"] == 1
    assert dom["drivers"][0]["name"] == "BOB"


def test_dominance_states_that_points_are_unavailable(conn):
    assert "points" in advanced.season_dominance(conn, 2020)["basis"].lower()


def test_dominance_for_unknown_season_is_none(conn):
    assert advanced.season_dominance(conn, 1999) is None


def test_dominance_timeline_covers_every_season(conn):
    timeline = advanced.dominance_timeline(conn)
    assert [row["season"] for row in timeline] == [2020, 2021]
    assert all(0 <= row["top_driver_win_share"] <= 1 for row in timeline)


# --------------------------------------------------------------------------
# Metric registry
# --------------------------------------------------------------------------

def test_every_metric_documents_its_limitations(conn):
    """The registry is the published methodology. A metric without stated
    limitations would be presented as more authoritative than it is."""
    for metric in advanced.METRICS:
        assert metric["definition"].strip()
        assert metric["formula"].strip()
        assert metric["limitations"].strip()
        assert metric["columns"]


def test_registry_keys_are_unique(conn):
    keys = [m["key"] for m in advanced.METRICS]
    assert len(keys) == len(set(keys))


def test_rate_metrics_declare_a_minimum_sample(conn):
    for key in ("win_rate", "top10_rate", "teammate_h2h", "circuit_specialism"):
        assert advanced.METRICS_BY_KEY[key]["min_sample"] is not None
