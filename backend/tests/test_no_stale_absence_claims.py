"""No file may claim a dataset is missing when the database has it.

WHY THIS EXISTS
---------------
This project has now had the same failure three times. Points, finishing
status, grid, qualifying and pit stops were ingested, and prose written before
that went on saying they were absent -- in analytics.py's module docstring
(the file that calls itself the single source of truth), in the OpenAPI
description every API consumer reads, in API.md, in METHODOLOGY.md, and in
four endpoint docstrings. Every one of them was true when written.

Nothing detected it, because a comment cannot fail. The dataset summary was
fixed by *measuring* availability instead of listing it, and the audit's
absent-list went the same way. Prose cannot be measured, so it is checked
instead: if the database has a column, no file may say it does not.

The claims are matched literally rather than by meaning. That is a real limit
-- rephrasing a claim evades this test -- but a literal match is worth having,
because these particular sentences were copied between files and would have
been caught the first time.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app.db import DB_PATH, connect

REPO_ROOT = Path(__file__).resolve().parents[2]

SEARCHED_SUFFIXES = {".py", ".md", ".ts", ".tsx"}
SKIPPED_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    "data", "archive", ".venv", "venv", "cache",
    # Design briefs are dated inputs describing what was known when the design
    # was commissioned, not claims this codebase makes about its own data.
    # They are kept verbatim on purpose; rewriting them would falsify the
    # record of what the design was actually drawn against.
    "uploads",
}

# Phrase -> the query proving it false. A phrase is only listed here once the
# claim is actually wrong; the point is to keep it wrong-and-caught rather than
# wrong-and-shipped.
FORBIDDEN_CLAIMS = {
    "no points column": "SELECT COUNT(*) FROM results WHERE points IS NOT NULL",
    "dataset has no points": "SELECT COUNT(*) FROM results WHERE points IS NOT NULL",
    "source has no status column": "SELECT COUNT(*) FROM results WHERE status IS NOT NULL",
    "no status column": "SELECT COUNT(*) FROM results WHERE status IS NOT NULL",
    "no grid position": "SELECT COUNT(*) FROM results WHERE grid IS NOT NULL",
    "points dominance cannot be computed": "SELECT COUNT(*) FROM results WHERE points IS NOT NULL",
    "championship standings, lap times": "SELECT COUNT(*) FROM results WHERE points IS NOT NULL",
    # Fourth recurrence, caught in the UI rather than by this file: the
    # dataset summary kept a static "unavailable" tail after the lap,
    # practice and fastest-lap ingestions landed, so the Home page told
    # readers the tool could not show 552,138 rows of lap times. The tail is
    # probed now; these phrases keep it from being written back.
    #
    # Phrased to match the UNQUALIFIED claim only. "The source publishes no
    # fastest lap before 2004" is true and must keep being sayable, so the
    # forbidden strings below are the list-entry forms that appeared in the
    # dataset summary and in METHODOLOGY.md, not every sentence containing
    # the words.
    "lap times / sector times": "SELECT COUNT(*) FROM lap_times",
    "lap times, sector times": "SELECT COUNT(*) FROM lap_times",
    "lap times, lap-by-lap timing": "SELECT COUNT(*) FROM lap_times",
    "pit stops, tyre compounds, telemetry": "SELECT COUNT(compound) FROM practice_laps",
}

# This file quotes every forbidden phrase by definition, and the checklist
# documents the history of having fixed them. Both would otherwise fail the
# test they exist to support.
EXEMPT_FILES = {
    Path(__file__).name,
    "BACKEND_CHECKLIST.md",
}

# Recording that a claim WAS made is not making it. A comment explaining that
# a field used to be reported as absent is exactly the context a future reader
# needs, and deleting it to satisfy a grep would remove the reason the code
# looks the way it does.
#
# So a line is exempt when it is visibly retrospective. The markers are
# deliberately narrow -- they describe the past explicitly, and none of them
# appear in a sentence that asserts a present absence. This mirrors the fix
# already made to the hardcoded-year guard, which was rewritten to walk
# runtime strings rather than lines once it started failing on docstrings that
# recorded findings.
HISTORICAL_MARKERS = (
    "previously", "used to", "stopped being true", "went on saying",
    "no longer", "was true when", "which is why", "rendered \"",
    "had already happened", "before that", "until now",
)


def _searchable_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if path.suffix not in SEARCHED_SUFFIXES or not path.is_file():
            continue
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        if path.name in EXEMPT_FILES:
            continue
        files.append(path)
    return files


@pytest.mark.skipif(
    not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
)
@pytest.mark.parametrize("phrase", sorted(FORBIDDEN_CLAIMS))
def test_no_file_claims_a_dataset_is_absent_when_it_is_present(phrase):
    conn = connect()
    try:
        present = conn.execute(FORBIDDEN_CLAIMS[phrase]).fetchone()[0]
    finally:
        conn.close()

    if not present:
        pytest.skip(f"{phrase!r} is still accurate: the column is empty")

    pattern = re.compile(re.escape(phrase), re.IGNORECASE)
    offenders = []
    for path in _searchable_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            # Prose wraps, so the marker that makes a sentence retrospective
            # ("previously said ...") frequently lands on the line above the
            # phrase itself. Checking one line in isolation reported the
            # project's own fix notes as violations.
            window = " ".join(lines[max(0, index - 2):index + 2]).lower()
            if any(marker in window for marker in HISTORICAL_MARKERS):
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}")

    assert not offenders, (
        f"{present:,} rows contradict the claim {phrase!r}, still written at: "
        + ", ".join(offenders[:8])
    )


# ---------------------------------------------------------------------------
# The same failure mode, for capabilities rather than datasets.
# ---------------------------------------------------------------------------
#
# The claims above go stale when a column gets populated. This one goes stale
# when a module gets written, and it has now happened once: "there is no
# monitoring, error reporting or alerting in this project" was written in
# OPERATIONS.md, copied into README.md, into PULL_REQUEST.md, and into a
# comment in ErrorBoundary.tsx -- four places, one of which was load-bearing
# prose telling a reader not to expect a signal that now exists.
#
# The distinction being defended is narrow and worth keeping narrow. The app
# is *instrumented*; nothing is *watching*. Saying "nothing is watching" must
# stay sayable, because it is true and it is the more important half. What
# must not stay sayable is the unqualified claim that no capture exists, when
# backend/app/observability.py and frontend/src/services/reporting.ts both do.

CAPABILITY_CLAIMS = {
    # phrase -> the file whose existence makes it false
    "no monitoring, error reporting or alerting": "backend/app/observability.py",
    "there is no error reporting in this project": "frontend/src/services/reporting.ts",
    "no error reporting in this project yet": "frontend/src/services/reporting.ts",
}


@pytest.mark.parametrize("phrase", sorted(CAPABILITY_CLAIMS))
def test_no_file_claims_a_capability_is_absent_when_it_is_implemented(phrase):
    proof = REPO_ROOT / CAPABILITY_CLAIMS[phrase]
    if not proof.exists():
        pytest.skip(f"{phrase!r} is still accurate: {proof.name} does not exist")

    pattern = re.compile(re.escape(phrase), re.IGNORECASE)
    offenders = []
    for path in _searchable_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            window = " ".join(lines[max(0, index - 2):index + 2]).lower()
            if any(marker in window for marker in HISTORICAL_MARKERS):
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}")

    assert not offenders, (
        f"{proof.relative_to(REPO_ROOT)} implements it, but {phrase!r} is still written at: "
        + ", ".join(offenders[:8])
    )
