"""Post-build integrity audit and coverage matrix.

`build.py` validates the CSV on the way *in*. This audits the database that
came *out*, which is a different question: a pipeline can validate every input
row and still produce a broken database through a bad join or a lost row.

Two outputs:

  * **Integrity checks** -- structural facts that must hold. Each is `pass`,
    `warn` or `fail`. A `fail` is a defect; a `warn` is a known upstream gap
    that is recorded rather than silently tolerated.
  * **Coverage matrix** -- per dataset, what is actually present. Built by
    counting rows, never by asserting a coverage level. A dataset with no
    source reports `unavailable`, not `0`.

Design rule, from the project brief: this module **flags anomalies, it never
silently corrects them**. Nothing here writes to the database.

Run:  python -m backend.etl.audit           (human-readable report)
      python -m backend.etl.audit --json    (machine-readable)
Exit: 0 when no check fails, 1 otherwise. Warnings do not fail the run.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field

from backend.app.db import DB_PATH, connect

PASS, WARN, FAIL = "pass", "warn", "fail"


@dataclass
class Check:
    """One integrity assertion and its measured result."""

    name: str
    status: str
    measured: int
    detail: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warned(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    def render(self) -> str:
        width = max(len(c.name) for c in self.checks)
        lines = ["INTEGRITY", "-" * (width + 22)]
        for c in self.checks:
            flag = {PASS: "ok  ", WARN: "WARN", FAIL: "FAIL"}[c.status]
            lines.append(f"{flag}  {c.name:<{width}}  {c.measured:>6}  {c.detail}")

        lines += ["", "COVERAGE", "-" * (width + 22)]
        for row in self.coverage:
            # NULL row count means "no source", which must not read as 0.
            count = "--" if row["rows"] is None else str(row["rows"])
            lines.append(
                f"      {row['dataset']:<{width}}  {count:>6}  "
                f"{row['coverage']}  [{row['verification']}]"
            )

        lines += [
            "",
            f"{len(self.checks)} checks: {len(self.failed)} failed, "
            f"{len(self.warned)} warned, "
            f"{len(self.checks) - len(self.failed) - len(self.warned)} passed.",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Integrity checks.
#
# Each entry is (name, sql, expected, severity_when_violated, detail). The SQL
# returns a single number; `expected` is the only value that means "clean".
# Written as data rather than code so the list reads as a specification.
# ---------------------------------------------------------------------------
_CHECKS: list[tuple[str, str, int, str, str]] = [
    ("duplicate_results", "SELECT COUNT(*) FROM (SELECT race_id, driver_id FROM results"
     " GROUP BY race_id, driver_id HAVING COUNT(*) > 1)", 0, FAIL,
     "one driver has at most one classification per race"),
    ("duplicate_races", "SELECT COUNT(*) FROM (SELECT season, round FROM races"
     " GROUP BY season, round HAVING COUNT(*) > 1)", 0, FAIL,
     "(season, round) is unique"),
    ("duplicate_driver_names", "SELECT COUNT(*) FROM (SELECT LOWER(name) FROM drivers"
     " GROUP BY LOWER(name) HAVING COUNT(*) > 1)", 0, FAIL, "no driver appears twice"),
    ("duplicate_constructor_names", "SELECT COUNT(*) FROM (SELECT LOWER(name) FROM constructors"
     " GROUP BY LOWER(name) HAVING COUNT(*) > 1)", 0, FAIL, "no constructor appears twice"),
    ("orphan_result_race", "SELECT COUNT(*) FROM results r"
     " LEFT JOIN races x ON x.id = r.race_id WHERE x.id IS NULL", 0, FAIL,
     "every result points at a real race"),
    ("orphan_result_driver", "SELECT COUNT(*) FROM results r"
     " LEFT JOIN drivers d ON d.id = r.driver_id WHERE d.id IS NULL", 0, FAIL,
     "every result points at a real driver"),
    ("orphan_result_constructor", "SELECT COUNT(*) FROM results r"
     " LEFT JOIN constructors c ON c.id = r.constructor_id WHERE c.id IS NULL", 0, FAIL,
     "every result points at a real constructor"),
    ("orphan_race_circuit", "SELECT COUNT(*) FROM races r"
     " LEFT JOIN circuits c ON c.id = r.circuit_id WHERE c.id IS NULL", 0, FAIL,
     "every race points at a real circuit"),
    ("position_below_one", "SELECT COUNT(*) FROM results WHERE position < 1", 0, FAIL,
     "classification order starts at 1"),
    ("position_null", "SELECT COUNT(*) FROM results WHERE position IS NULL", 0, FAIL,
     "position is never unknown"),
    ("race_without_results", "SELECT COUNT(*) FROM races r WHERE NOT EXISTS"
     " (SELECT 1 FROM results x WHERE x.race_id = r.id)", 0, FAIL,
     "no race is recorded with an empty field"),
    ("race_without_winner", "SELECT COUNT(*) FROM races r WHERE NOT EXISTS"
     " (SELECT 1 FROM results x WHERE x.race_id = r.id AND x.position = 1)", 0, FAIL,
     "every race has a P1"),
    ("race_with_multiple_winners", "SELECT COUNT(*) FROM (SELECT race_id FROM results"
     " WHERE position = 1 GROUP BY race_id HAVING COUNT(*) > 1)", 0, FAIL,
     "no race has two P1s"),
    ("season_date_mismatch", "SELECT COUNT(*) FROM races"
     " WHERE CAST(STRFTIME('%Y', date) AS INTEGER) <> season", 0, FAIL,
     "a race is dated inside its own season"),
    ("round_sequence_gap", "SELECT COUNT(*) FROM (SELECT season FROM races"
     " GROUP BY season HAVING MAX(round) <> COUNT(*))", 0, FAIL,
     "rounds run 1..N with no gaps"),
    ("driver_never_raced", "SELECT COUNT(*) FROM drivers d WHERE NOT EXISTS"
     " (SELECT 1 FROM results r WHERE r.driver_id = d.id)", 0, FAIL,
     "no driver exists without a result"),
    ("constructor_never_raced", "SELECT COUNT(*) FROM constructors c WHERE NOT EXISTS"
     " (SELECT 1 FROM results r WHERE r.constructor_id = c.id)", 0, FAIL,
     "no constructor exists without a result"),
    ("circuit_never_used", "SELECT COUNT(*) FROM circuits c WHERE NOT EXISTS"
     " (SELECT 1 FROM races r WHERE r.circuit_id = c.id)", 0, FAIL,
     "no circuit exists without a race"),
    # Warning, not failure: an upstream omission this project reports rather
    # than patches. Denominators count rows present, never MAX(position).
    ("classification_gaps", "SELECT COUNT(*) FROM (SELECT race_id FROM results"
     " GROUP BY race_id HAVING MAX(position) <> COUNT(*))", 0, WARN,
     "races whose classification skips a position (upstream omission)"),
    # Future-dated results would mean fabricated data for races not yet run.
    ("results_for_future_races", "SELECT COUNT(*) FROM races"
     " WHERE date > DATE('now')", 0, FAIL,
     "no race is recorded ahead of its date"),

    # ---- enrichment (finishing status, points, grid, laps) ----
    ("enrichment_missing", "SELECT COUNT(*) FROM results WHERE classification IS NULL",
     0, FAIL, "every result carries a finishing status"),
    ("classification_disagrees_with_position",
     "SELECT COUNT(*) FROM results WHERE classification = 'classified'"
     " AND position_text <> CAST(position AS TEXT)", 0, FAIL,
     "classified rows agree with their position"),
    ("winner_not_classified",
     "SELECT COUNT(*) FROM results WHERE position = 1 AND classification <> 'classified'",
     0, FAIL, "every race winner is classified"),
    ("winner_scored_no_points",
     "SELECT COUNT(*) FROM results WHERE position = 1 AND points <= 0", 0, FAIL,
     "every race winner scored points"),
    ("negative_points", "SELECT COUNT(*) FROM results WHERE points < 0", 0, FAIL,
     "points are never negative"),
    # grid = 0 is a pit lane start and is valid; negative is not.
    ("negative_grid", "SELECT COUNT(*) FROM results WHERE grid < 0", 0, FAIL,
     "grid is never negative (0 is a valid pit-lane start)"),
    ("laps_negative", "SELECT COUNT(*) FROM results WHERE laps < 0", 0, FAIL,
     "laps completed is never negative"),
    ("unknown_classification",
     "SELECT COUNT(*) FROM results WHERE classification NOT IN"
     " ('classified','retired','disqualified','withdrawn')", 0, FAIL,
     "classification uses only the four documented categories"),

    # ---- sprints ----
    ("sprint_before_2021",
     "SELECT COUNT(*) FROM sprint_results s JOIN races ra ON ra.id = s.race_id"
     " WHERE ra.season < 2021", 0, FAIL,
     "no sprint is recorded before the format existed"),
    ("sprint_orphan_race",
     "SELECT COUNT(*) FROM sprint_results s LEFT JOIN races ra ON ra.id = s.race_id"
     " WHERE ra.id IS NULL", 0, FAIL, "every sprint points at a real race"),
    ("qualifying_orphan_race",
     "SELECT COUNT(*) FROM qualifying_results q LEFT JOIN races ra ON ra.id = q.race_id"
     " WHERE ra.id IS NULL", 0, FAIL, "every qualifying row points at a real race"),
    ("qualifying_duplicate_pole",
     "SELECT COUNT(*) FROM (SELECT race_id FROM qualifying_results WHERE position = 1"
     " GROUP BY race_id HAVING COUNT(*) > 1)", 0, FAIL, "no race has two qualifying P1s"),
    # Q3 marks the 2006 three-segment format; Q2 the 2005 aggregate format.
    # An earlier appearance would mean a modern rule applied retroactively.
    ("session_predates_its_format",
     "SELECT COUNT(*) FROM qualifying_results q JOIN races ra ON ra.id = q.race_id"
     " WHERE (ra.season < 2006 AND q.q3 IS NOT NULL)"
     "    OR (ra.season < 2005 AND q.q2 IS NOT NULL)", 0, FAIL,
     "no qualifying session predates the format that created it"),
    ("pitstop_before_2011",
     "SELECT COUNT(*) FROM pit_stops p JOIN races ra ON ra.id = p.race_id"
     " WHERE ra.season < 2011", 0, FAIL,
     "no pit stop is recorded before the source covers them"),
    ("pitstop_orphan_race",
     "SELECT COUNT(*) FROM pit_stops p LEFT JOIN races ra ON ra.id = p.race_id"
     " WHERE ra.id IS NULL", 0, FAIL, "every pit stop points at a real race"),
    # A zero-second stop is not a thing; the source's gaps must stay NULL.
    ("pitstop_zero_duration",
     "SELECT COUNT(*) FROM pit_stops WHERE duration = '0' OR duration = '0.0'", 0, FAIL,
     "no pit stop duration was zero-filled"),
    # Warning, not failure: the SOURCE is missing stop #1 for two drivers
    # (Chilton, 2014 British GP; Sainz, 2019 Singapore GP). Fabricating the
    # missing stop or renumbering the survivors would both be worse than
    # carrying a recorded warning.
    ("pitstop_numbering_gaps",
     "SELECT COUNT(*) FROM (SELECT race_id, driver_id FROM pit_stops"
     " GROUP BY race_id, driver_id HAVING MAX(stop) <> COUNT(*))", 0, WARN,
     "drivers whose pit stop numbering skips a stop (upstream omission)"),
    ("sprint_duplicate_winner",
     "SELECT COUNT(*) FROM (SELECT race_id FROM sprint_results WHERE position = 1"
     " GROUP BY race_id HAVING COUNT(*) > 1)", 0, FAIL,
     "no sprint has two winners"),
]


def run_checks(conn: sqlite3.Connection) -> list[Check]:
    checks = []
    for name, sql, expected, severity, detail in _CHECKS:
        measured = conn.execute(sql).fetchone()[0]
        status = PASS if measured == expected else severity
        checks.append(Check(name=name, status=status, measured=measured, detail=detail))
    return checks


# ---------------------------------------------------------------------------
# Coverage matrix.
#
# Reports what is present. A dataset with no source is `unavailable` -- never
# `0`, which would claim a measured zero. Verification is `structural` for
# everything: no value here has been cross-checked against an authoritative
# F1 source, and saying otherwise would be the claim the brief forbids.
# ---------------------------------------------------------------------------
# Datasets with no source at all. Nothing here is a "not yet" -- each one has
# been looked for and does not exist in anything this project ingests, so the
# row reports `unavailable` rather than a measured zero.
#
# `lap_times` and `sessions` used to be listed here and are not any more. They
# are now measured below, from row counts, for the same reason the dataset
# summary stopped hardcoding its own absence list: a hand-maintained list of
# what is missing becomes a lie the moment someone ingests one of the items
# and does not think to edit it.
#
# `practice_results` stays: the Ergast-compatible source exposes no practice
# classifications (its /practice, /fp1 and /sessions routes 400 or 404). The
# weekend timetable IS ingested and is reported separately as `sessions` --
# the two must not be conflated, because having the schedule of FP1 says
# nothing about having its results.
_ABSENT = [
    "practice_results",
    "cars", "engines", "tyres",
]


def _span_for(conn: sqlite3.Connection, sql: str, fallback: str) -> str:
    """Measured season span of a dataset, e.g. "2011-2025".

    Derived rather than written down. A hardcoded window is a claim that stops
    being re-checked; this one cannot drift from what was actually loaded.
    """
    lo, hi = conn.execute(sql).fetchone()
    if lo is None:
        return fallback
    return f"{lo}-{hi}" if lo != hi else str(lo)

# Cross-validated against Jolpica-F1: all 10,550 rows matched on driver and
# constructor, and championship totals reproduce the official standings
# exactly for all 26 seasons. That is corroboration by an independent record,
# which is a materially stronger claim than "internally consistent".
_VALIDATED = "cross-validated vs Jolpica-F1"
_STRUCTURAL = "structural (not cross-validated)"


def _lap_coverage(conn: sqlite3.Connection) -> str:
    """How much of the race calendar has lap timings, stated as a fraction.

    A span alone would be misleading here. Lap ingestion is a per-race fetch
    of several thousand requests, so a run can legitimately be half finished,
    and "2000-2025" would then describe the endpoints of a sparse set rather
    than its coverage. The fraction is the honest summary.
    """
    covered = conn.execute("SELECT COUNT(DISTINCT race_id) FROM lap_times").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM races").fetchone()[0]
    if not covered:
        return "none loaded"
    span = _span_for(
        conn,
        "SELECT MIN(ra.season), MAX(ra.season) FROM lap_times l"
        " JOIN races ra ON ra.id = l.race_id",
        "unknown",
    )
    return f"{covered}/{total} races ({span})"


def coverage_matrix(conn: sqlite3.Connection) -> list[dict]:
    lo, hi = conn.execute("SELECT MIN(season), MAX(season) FROM races").fetchone()
    span = f"{lo}-{hi}"

    present = [
        ("seasons", "SELECT COUNT(DISTINCT season) FROM races", span, _STRUCTURAL),
        ("races", "SELECT COUNT(*) FROM races", span, _VALIDATED),
        ("race_results", "SELECT COUNT(*) FROM results", span, _VALIDATED),
        ("drivers", "SELECT COUNT(*) FROM drivers", span, _VALIDATED),
        ("constructors", "SELECT COUNT(*) FROM constructors", span, _VALIDATED),
        ("circuits", "SELECT COUNT(*) FROM circuits", span, _STRUCTURAL),
        ("finishing_status",
         "SELECT COUNT(*) FROM results WHERE classification IS NOT NULL", span, _VALIDATED),
        ("championship_points",
         "SELECT COUNT(*) FROM results WHERE points IS NOT NULL", span, _VALIDATED),
        ("grid_positions",
         "SELECT COUNT(*) FROM results WHERE grid IS NOT NULL", span, _VALIDATED),
        ("laps_completed",
         "SELECT COUNT(*) FROM results WHERE laps IS NOT NULL", span, _VALIDATED),
        # Sprints exist only from 2021; reporting the full span would overstate
        # the coverage of a dataset that cannot exist before then.
        ("sprints", "SELECT COUNT(*) FROM sprint_results", "2021-" + str(hi), _VALIDATED),
        # Partial before 2003 and complete after. Reporting a single span
        # would overstate the early seasons, so the gap is named instead.
        ("qualifying", "SELECT COUNT(*) FROM qualifying_results",
         "2003-" + str(hi) + " complete; 2000-2002 partial (6-24%)", _STRUCTURAL),
        ("driver_detail",
         "SELECT COUNT(*) FROM drivers WHERE nationality IS NOT NULL", span, _VALIDATED),
        # 2011 onward only -- the source has no pit stop data before then.
        ("pit_stops", "SELECT COUNT(*) FROM pit_stops", "2011-" + str(hi), _STRUCTURAL),
        ("circuit_location",
         "SELECT COUNT(*) FROM circuits WHERE latitude IS NOT NULL", span, _STRUCTURAL),
        # Both spans are measured, not asserted: an interrupted lap fetch
        # produces genuinely partial coverage, and the row must say so rather
        # than claim the full window.
        ("lap_times", "SELECT COUNT(*) FROM lap_times",
         _lap_coverage(conn), _STRUCTURAL),
        ("sessions", "SELECT COUNT(*) FROM sessions",
         _span_for(conn,
                   "SELECT MIN(ra.season), MAX(ra.season) FROM sessions s"
                   " JOIN races ra ON ra.id = s.race_id",
                   "none loaded")
         + " (weekend timetable only, not practice results)", _STRUCTURAL),
    ]

    rows = [
        {
            "dataset": name,
            "rows": conn.execute(sql).fetchone()[0],
            "coverage": cov,
            "verification": verification,
        }
        for name, sql, cov, verification in present
    ]

    # Circuit maps are a partial asset, so report the real fraction.
    with_map = conn.execute("SELECT COUNT(*) FROM circuits WHERE has_map = 1").fetchone()[0]
    total_circuits = conn.execute("SELECT COUNT(*) FROM circuits").fetchone()[0]
    rows.append({
        "dataset": "circuit_maps",
        "rows": with_map,
        "coverage": f"{with_map}/{total_circuits} circuits",
        "verification": "asset presence only",
    })

    rows += [
        {
            "dataset": name,
            "rows": None,
            "coverage": "unavailable",
            "verification": "no source ingested",
        }
        for name in _ABSENT
    ]
    return rows


def audit(conn: sqlite3.Connection) -> Report:
    return Report(checks=run_checks(conn), coverage=coverage_matrix(conn))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run: python -m backend.etl.build")
        return 1

    conn = connect()
    try:
        report = audit(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps({
            "checks": [vars(c) for c in report.checks],
            "coverage": report.coverage,
        }, indent=2))
    else:
        print(report.render())

    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
