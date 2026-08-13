"""The integrity audit as a build gate.

`backend/etl/audit.py` is only useful if something runs it. These tests make a
failing integrity check fail the suite, so a bad build cannot reach the API.

Warnings deliberately do not fail: the one known warning is an upstream
omission (the 2002 French GP is classified to P22 but only 20 rows exist),
which is reported rather than patched. Turning it into a failure would mean
either fabricating the two missing rows or dropping a real race -- both worse
than carrying a recorded warning.
"""

from __future__ import annotations

import pytest

from backend.app.db import DB_PATH, connect
from backend.etl import audit

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
)


@pytest.fixture(scope="module")
def report():
    conn = connect()
    try:
        yield audit.audit(conn)
    finally:
        conn.close()


def test_no_integrity_check_fails(report):
    failures = [f"{c.name} (measured {c.measured}): {c.detail}" for c in report.failed]
    assert not failures, "integrity checks failed:\n" + "\n".join(failures)


def test_every_check_actually_ran(report):
    """Guards against a check silently disappearing from the list."""
    assert len(report.checks) == len(audit._CHECKS)
    assert {c.name for c in report.checks} == {name for name, *_ in audit._CHECKS}


def test_known_warnings_are_exactly_what_we_expect(report):
    """Pins the accepted warnings.

    A new warning is a real signal, so it must break the build and be looked
    at rather than blend into an ever-growing list of tolerated noise.
    """
    assert {c.name for c in report.warned} == {"classification_gaps"}


def test_coverage_never_reports_absent_data_as_zero(report):
    """NULL vs zero, enforced.

    A dataset with no source must report `None`, not `0`. Reporting 0 lap times
    would claim a measured zero -- that we looked and there were none -- when
    the truth is that nothing was ever ingested.
    """
    for row in report.coverage:
        if row["coverage"] == "unavailable":
            assert row["rows"] is None, f"{row['dataset']} reports {row['rows']!r}, expected None"


def test_coverage_uses_only_the_documented_verification_vocabulary(report):
    """Every verification claim must be one this project can actually back.

    This test previously asserted that NO row claimed cross-validation, which
    was right while none had been done. Cross-validation has since run against
    Jolpica-F1 -- all 10,550 rows matched on driver and constructor, and
    championship totals reproduced the official standings exactly for all 26
    seasons -- so the claim is now supportable for the datasets that went
    through it.

    The guard that matters is therefore no longer "never claim it", but "only
    ever make a claim from this fixed vocabulary". A free-text verification
    string is how an unearned claim would slip in.
    """
    allowed = {
        audit._VALIDATED,
        audit._STRUCTURAL,
        "asset presence only",
        "no source ingested",
    }
    for row in report.coverage:
        assert row["verification"] in allowed, (
            f"{row['dataset']} claims {row['verification']!r}, which is not one of "
            f"the documented verification levels"
        )


def test_unavailable_datasets_never_claim_verification(report):
    """A dataset with no source cannot have been validated."""
    for row in report.coverage:
        if row["coverage"] == "unavailable":
            assert row["verification"] == "no source ingested"


def test_present_datasets_report_a_real_row_count(report):
    for row in report.coverage:
        if row["coverage"] != "unavailable" and row["dataset"] != "circuit_maps":
            assert isinstance(row["rows"], int) and row["rows"] > 0


# ---------------------------------------------------------------- enrichment


def test_every_result_has_a_finishing_status():
    """The whole point of the enrichment: no row may be status-less."""
    conn = connect()
    try:
        missing = conn.execute(
            "SELECT COUNT(*) FROM results WHERE classification IS NULL"
        ).fetchone()[0]
        assert missing == 0, f"{missing} results have no finishing status"
    finally:
        conn.close()


def test_classified_is_not_confused_with_finished():
    """A classified driver need not have finished, and that must stay visible.

    ~2,000 rows are classified but several laps down. If `classification` ever
    started meaning "saw the flag", every reliability metric would silently
    change meaning, so this pins the distinction with real numbers.
    """
    conn = connect()
    try:
        classified = conn.execute(
            "SELECT COUNT(*) FROM results WHERE classification = 'classified'"
        ).fetchone()[0]
        finished = conn.execute(
            "SELECT COUNT(*) FROM results WHERE status = 'Finished'"
        ).fetchone()[0]
        assert finished < classified, (
            "every classified driver appears to have finished -- the "
            "classified/finished distinction has been lost"
        )
    finally:
        conn.close()


def test_grid_zero_is_a_pit_lane_start_not_a_null():
    """0 must remain a real, meaningful value -- never coerced to NULL."""
    conn = connect()
    try:
        pit_starts = conn.execute("SELECT COUNT(*) FROM results WHERE grid = 0").fetchone()[0]
        assert pit_starts > 0, "grid=0 rows vanished; pit-lane starts are real"
    finally:
        conn.close()


def test_championship_totals_reproduce_from_race_plus_sprint_points():
    """Standings must be derivable, never stored.

    Verified against the official standings for all 26 seasons when the data
    was ingested. This asserts the shape that made it work: the champion is
    the points leader, and from 2021 sprint points are part of the total.
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT season, name, SUM(pts) total FROM (
                SELECT ra.season, d.name, r.points pts
                  FROM results r
                  JOIN races ra ON ra.id = r.race_id
                  JOIN drivers d ON d.id = r.driver_id
                UNION ALL
                SELECT ra.season, d.name, s.points
                  FROM sprint_results s
                  JOIN races ra ON ra.id = s.race_id
                  JOIN drivers d ON d.id = s.driver_id
            ) GROUP BY season, name
            """
        ).fetchall()
        by_season = {}
        for season, name, total in rows:
            by_season.setdefault(season, []).append((total, name))

        assert len(by_season) == 26
        for season, entries in by_season.items():
            top = max(entries)
            assert top[0] > 0, f"{season} has no points leader"

        # Spot-check two seasons whose totals were verified against the
        # official standings, one pre-sprint and one sprint-era.
        assert max(by_season[2008])[1] == "Lewis Hamilton"
        assert abs(max(by_season[2008])[0] - 98) < 0.01
        assert abs(max(by_season[2023])[0] - 575) < 0.01, (
            "2023 total is not 575 -- sprint points are missing from the sum"
        )
    finally:
        conn.close()


def test_sprints_are_a_separate_event_not_extra_race_rows():
    """Merging sprints into results would double every driver's race count."""
    conn = connect()
    try:
        results = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        sprints = conn.execute("SELECT COUNT(*) FROM sprint_results").fetchone()[0]
        assert results == 10550, "sprint rows leaked into the results table"
        assert sprints > 0
        earliest = conn.execute(
            "SELECT MIN(ra.season) FROM sprint_results s JOIN races ra ON ra.id = s.race_id"
        ).fetchone()[0]
        assert earliest >= 2021, "a sprint is recorded before the format existed"
    finally:
        conn.close()
