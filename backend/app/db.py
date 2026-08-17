"""Database access. Read-only by construction.

The API never writes: the DB is a build artefact of `backend/etl/build.py`,
so connections open in SQLite read-only mode. A bug in a router cannot
corrupt the dataset -- it raises instead.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "f1.db"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    if not path.exists():
        raise RuntimeError(f"Database not found at {path}. Run: python -m backend.etl.build")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, always closed."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# Tables reachable by id lookup. The name is interpolated into SQL (SQLite
# cannot parameterise an identifier), so it is constrained here rather than
# trusted to stay a literal at every call site.
LOOKUP_TABLES = frozenset({"drivers", "constructors", "circuits", "races"})

# Tables carrying a stable, source-derived `slug`. These are the entities the
# API accepts by name as well as by number. `races` is absent deliberately: it
# has no slug column, its natural key being (season, round).
SLUGGED_TABLES = frozenset({"drivers", "constructors", "circuits"})


def fetch_one_or_404(
    conn: sqlite3.Connection, table: str, entity_id: int | str
) -> sqlite3.Row:
    """Look up an entity by slug or integer id, 404ing rather than returning None.

    WHY BOTH
    --------
    The slug is the real identity: it is the only key that means the same
    thing here and in the Postgres materialisation, where integer ids come
    from an unrelated sequence. New links should use it.

    Integer ids keep resolving because they are already in circulation --
    every existing `/drivers/48` bookmark would otherwise 404. They are
    accepted, not preferred, and a numeric-looking value is only ever tried as
    an id, never as a slug, so the two key spaces cannot collide.
    """
    from fastapi import HTTPException

    if table not in LOOKUP_TABLES:
        raise ValueError(f"{table!r} is not a lookup table")

    key = str(entity_id)
    if key.isdigit():
        column, value = "id", int(key)
    elif table in SLUGGED_TABLES:
        column, value = "slug", key
    else:
        raise HTTPException(status_code=404, detail=f"No {table[:-1]} {entity_id!r}")

    row = conn.execute(f"SELECT * FROM {table} WHERE {column} = ?", [value]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No {table[:-1]} {entity_id!r}")
    return row
