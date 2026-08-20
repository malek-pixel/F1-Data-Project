"""Can this dataset be rebuilt, exactly, from what is committed?

WHY THIS EXISTS
---------------
`data/f1.db` is gitignored, and the recovery story in docs/OPERATIONS.md rests
entirely on one claim: every table derives from committed CSVs, so a
restore-then-reimport terminates in a known-good state. That claim was
documented and reasoned about, but never demonstrated. A pipeline can be
"reproducible" in the sense that it runs twice without erroring while still
assigning different surrogate ids on each run -- which would make the database
unrestorable in the only sense that matters, because `/drivers/65` would point
at a different driver after a rebuild.

The risk is real rather than theoretical: the build assigns ids by iterating
over sets of names, and Python randomises string hashing per process. If any
of that ordering reached an id, two builds in two processes would disagree.

So this rebuilds from the committed source into a throwaway file and compares
the result, table by table, with the database the API is actually serving.
"""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.app.db import DB_PATH
from backend.etl import build

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
)


def fingerprint(path: Path) -> dict[str, str]:
    """A content hash per table, ordered by every column.

    Ordered by all columns rather than by rowid: rowid ordering would hide the
    very thing being tested, since two builds inserting the same rows in a
    different order would still read back in insertion order and compare equal.
    """
    conn = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        digests = {}
        for table in tables:
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            digest = hashlib.sha256()
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY {', '.join(columns)}"):
                digest.update(repr(row).encode("utf-8"))
            digests[table] = digest.hexdigest()
        return digests
    finally:
        conn.close()


def source_sha(path: Path) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM build_meta WHERE key = 'source_sha256'"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_a_rebuild_reproduces_the_serving_database_exactly():
    """Rebuild from the committed CSVs and compare, table by table.

    A failure here means one of two very different things, so the assertions
    are ordered to tell them apart: a differing `source_sha256` means the local
    `data/f1.db` is simply stale and needs rebuilding, while a matching one
    with differing table content means the BUILD is non-deterministic, which
    is the defect this test is for.
    """
    report = build.Report()
    raw = build.load_raw(build.RAW_CSV)
    rules = build.load_circuit_map(build.CIRCUIT_MAP_CSV)
    rows = build.validate(raw, rules, report)
    assert not report.fatal, "the committed source no longer builds"

    with tempfile.TemporaryDirectory() as tmp:
        rebuilt = Path(tmp) / "rebuild.db"
        build.load(rows, rebuilt, report)

        assert source_sha(rebuilt) == source_sha(DB_PATH), (
            "data/f1.db was built from a different results.csv than the one "
            "committed now -- rebuild it: python -m backend.etl.build"
        )

        served, fresh = fingerprint(DB_PATH), fingerprint(rebuilt)

    assert set(served) == set(fresh), (
        f"a rebuild produced a different set of tables: "
        f"{sorted(set(served) ^ set(fresh))}"
    )
    differing = sorted(t for t in served if served[t] != fresh[t])
    assert not differing, (
        "the build is not deterministic -- two runs of the same source "
        f"produced different content in: {differing}. Surrogate ids would "
        "then change across a rebuild, so every /drivers/{id} URL and every "
        "stored reference breaks on restore."
    )
