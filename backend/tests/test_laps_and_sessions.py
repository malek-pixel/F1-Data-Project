"""Integrity tests for lap timings and the weekend timetable.

These datasets arrive differently from the rest. Lap times come from a
per-race fetch of several thousand requests that is expected to be run in
pieces, so "partial" is a legitimate state and the tests must hold on a
half-loaded database as well as a complete one. What they must never allow is
a partial load that looks complete, or a lap time that is present but wrong.
"""
from __future__ import annotations

import pytest

from backend.app.db import DB_PATH, connect
from backend.etl.build_laps import parse_lap_time

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
)


@pytest.fixture(scope="module")
def conn():
    db = connect()
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1:39.019", 99_019),
        ("0:55.400", 55_400),
        ("39.019", 39_019),
        # Two-digit milliseconds are padded, not truncated: "55.4" is 400ms,
        # not 4ms. Getting this backwards would make every such lap the
        # fastest ever recorded.
        ("0:55.4", 55_400),
    ],
)
def test_lap_times_parse_to_milliseconds(text, expected):
    assert parse_lap_time(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "no time", "1:2:3.456", None])
def test_unparseable_lap_times_are_none_not_zero(text):
    """None, never 0.

    A lap time coerced to zero does not fail -- it wins. It would be returned
    as the fastest lap of its race, and of every aggregate above it, while
    looking like an ordinary value.
    """
    assert parse_lap_time(text) is None


# ---------------------------------------------------------------------------
# Lap timings
# ---------------------------------------------------------------------------

def test_every_lap_time_is_attributed_to_a_real_race_and_driver(conn):
    orphans = conn.execute(
        """
        SELECT COUNT(*) FROM lap_times l
        LEFT JOIN races ra  ON ra.id = l.race_id
        LEFT JOIN drivers d ON d.id  = l.driver_id
        WHERE ra.id IS NULL OR d.id IS NULL
        """
    ).fetchone()[0]
    assert orphans == 0


def test_no_lap_time_is_stored_as_zero(conn):
    """The CHECK constraint should make this impossible; assert it anyway.

    The constraint is the guard, this is the proof the guard is still on the
    column -- a schema edit that dropped it would otherwise go unnoticed until
    a zero appeared in a records table.
    """
    assert conn.execute("SELECT COUNT(*) FROM lap_times WHERE time_ms <= 0").fetchone()[0] == 0


def test_lap_numbering_starts_at_one_and_has_no_gaps_within_a_race(conn):
    """A driver's laps must run 1..n with nothing missing.

    A gap means a page of the paginated fetch was lost. The row count alone
    would not reveal it: the race would simply have fewer laps than it ran,
    which reads as a retirement rather than as missing data.
    """
    bad = conn.execute(
        """
        SELECT race_id, driver_id, COUNT(*) AS laps, MIN(lap) AS lo, MAX(lap) AS hi
        FROM lap_times
        GROUP BY race_id, driver_id
        HAVING lo <> 1 OR hi <> laps
        LIMIT 5
        """
    ).fetchall()
    assert not bad, f"non-contiguous lap numbering: {[tuple(r) for r in bad]}"


def test_loaded_races_are_fully_loaded(conn):
    """Partial coverage across races is fine; a partial race is not.

    The fetch is resumable per race, so some races having no laps at all is
    expected mid-ingestion. But a race present with only a handful of timings
    means its fetch was interrupted mid-page, and that is indistinguishable
    from a real short race unless it is checked here.
    """
    suspicious = conn.execute(
        """
        SELECT ra.season, ra.round, COUNT(*) AS timings
        FROM lap_times l JOIN races ra ON ra.id = l.race_id
        GROUP BY l.race_id
        HAVING timings < 100
        LIMIT 5
        """
    ).fetchall()
    assert not suspicious, f"races with implausibly few lap timings: {[tuple(r) for r in suspicious]}"


def test_no_lap_is_implausibly_fast(conn):
    """Lower bound only, and that asymmetry is the point.

    A too-fast lap can only be a parsing or unit error: no Formula 1 lap on a
    championship circuit has been under 50 seconds.

    There is deliberately no upper bound. A first draft of this test asserted
    one and failed on a 33-minute lap, which turned out to be correct data --
    the 2023 Australian Grand Prix was red-flagged and the source counts the
    suspension inside the lap. 49 laps of that race exceed five minutes, and
    several other races carry one. Capping the maximum would not have caught a
    bug; it would have rejected every red-flagged race in the dataset.
    """
    fastest = conn.execute("SELECT MIN(time_ms) FROM lap_times").fetchone()[0]
    if fastest is None:
        pytest.skip("no lap times loaded")
    assert fastest > 50_000, f"implausibly fast lap: {fastest}ms"


def test_each_race_has_a_plausible_green_flag_pace(conn):
    """The *fastest* lap of every race must look like a racing lap.

    This is the check the maximum could not give. Suspensions inflate
    individual laps without limit, but they cannot make a race's quickest lap
    implausible -- so a per-race minimum still catches a circuit whose times
    were parsed in the wrong unit, while tolerating any number of red flags.
    """
    outliers = conn.execute(
        """
        SELECT ra.season, ra.round, MIN(l.time_ms) AS best
        FROM lap_times l JOIN races ra ON ra.id = l.race_id
        GROUP BY l.race_id
        HAVING best < 50000 OR best > 300000
        LIMIT 5
        """
    ).fetchall()
    assert not outliers, f"implausible fastest lap for race: {[tuple(r) for r in outliers]}"


# ---------------------------------------------------------------------------
# Weekend timetable
# ---------------------------------------------------------------------------

KNOWN_SESSIONS = {"fp1", "fp2", "fp3", "qualifying", "sprint", "sprint_qualifying"}


def test_session_codes_are_from_the_known_set(conn):
    codes = {r[0] for r in conn.execute("SELECT DISTINCT session FROM sessions")}
    assert codes <= KNOWN_SESSIONS, f"unexpected session codes: {codes - KNOWN_SESSIONS}"


def test_a_race_never_has_the_same_session_twice(conn):
    """Guards the assumption that unified the sprint-qualifying rename.

    2023's "SprintShootout" and 2024's "SprintQualifying" are stored under one
    code because they are the same session renamed. If a weekend ever carried
    both, that assumption is wrong and the two are distinct sessions -- so
    this must fail rather than let one silently overwrite the other.
    """
    dupes = conn.execute(
        "SELECT race_id, session, COUNT(*) c FROM sessions"
        " GROUP BY race_id, session HAVING c > 1 LIMIT 5"
    ).fetchall()
    assert not dupes, f"duplicate sessions: {[tuple(r) for r in dupes]}"


def test_sprint_sessions_only_exist_from_2021(conn):
    """Sprints began in 2021. An earlier one means a join went wrong."""
    early = conn.execute(
        """
        SELECT ra.season, ra.round, s.session
        FROM sessions s JOIN races ra ON ra.id = s.race_id
        WHERE s.session LIKE 'sprint%' AND ra.season < 2021
        LIMIT 5
        """
    ).fetchall()
    assert not early, f"sprint session before 2021: {[tuple(r) for r in early]}"


def test_every_sprint_session_has_a_matching_sprint_result(conn):
    """The timetable and the results must agree on which weekends had a sprint.

    Two independently ingested files describing the same event. If one says a
    sprint was scheduled and the other has no classification for it, one of
    them is wrong, and neither is self-evidently the wrong one -- which is
    exactly why it is worth failing on.
    """
    mismatched = conn.execute(
        """
        SELECT ra.season, ra.round
        FROM sessions s
        JOIN races ra ON ra.id = s.race_id
        WHERE s.session = 'sprint'
          AND NOT EXISTS (SELECT 1 FROM sprint_results sr WHERE sr.race_id = s.race_id)
        LIMIT 5
        """
    ).fetchall()
    assert not mismatched, f"sprint scheduled but no results: {[tuple(r) for r in mismatched]}"


def test_session_dates_fall_on_or_before_their_race(conn):
    """Every session in this table runs during the race weekend.

    Practice and qualifying precede the grand prix. A session dated after its
    race means the row was attached to the wrong round.
    """
    wrong = conn.execute(
        """
        SELECT ra.season, ra.round, s.session, s.date, ra.date
        FROM sessions s JOIN races ra ON ra.id = s.race_id
        WHERE s.date > ra.date
        LIMIT 5
        """
    ).fetchall()
    assert not wrong, f"session after its race: {[tuple(r) for r in wrong]}"
