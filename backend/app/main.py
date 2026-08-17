"""FastAPI application.

Read-only analytical API over the SQLite build artefact. Run from the repo root:

    uvicorn backend.app.main:app --reload

Interactive docs at /docs.
"""
from __future__ import annotations

import logging
import os
import sqlite3

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import backends
from .db import connect
from .routers import analysis, analytics_router, calendar, entities

log = logging.getLogger(__name__)

# Fail at import, not on the first request. A backend misconfiguration is a
# deployment error; discovering it as an intermittent 503 later is strictly
# worse than refusing to start.
ACTIVE_BACKEND = backends.check_ready()
log.info("Serving from backend: %s", ACTIVE_BACKEND)

# Origins are configured, never wildcarded -- the default covers the local
# Vite dev server only.
ALLOWED_ORIGINS = os.getenv("F1_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

app = FastAPI(
    title="F1 Data Project API",
    version="1.0.0",
    description=(
        # No season range here on purpose: this string is built once at import,
        # before any connection exists, so a literal would be a claim nothing
        # re-checks. The live window is served by `/api/dataset/summary`.
        "Analytical API over Formula 1 race classifications.\n\n"
        "The seasons covered are whatever the build contains -- see "
        "`/api/dataset/summary` for the authoritative window.\n\n"
        "Every derived number is defined once in `backend/app/analytics.py`.\n\n"
        # No list of absent datasets here either. The previous version of this
        # string named qualifying, points and finishing status as absent, and
        # went on saying so for as long as it took someone to read it against
        # the database. Availability is counted from rows and served by
        # `/api/dataset/summary`; this description points at that rather than
        # duplicating a claim nothing re-checks.
        "Which datasets are present, partial or absent is measured from the "
        "database itself and reported by `/api/dataset/summary`. Nothing is "
        "estimated or inferred: a value that is not in a source is absent, "
        "never approximated."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

for module in (entities, calendar, analysis, analytics_router):
    app.include_router(module.router, prefix="/api")


@app.exception_handler(sqlite3.Error)
async def database_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
    """Log the real error, return a safe one.

    Database internals never reach the client; the server log keeps the detail.
    """
    log.exception("Database error on %s", request.url.path)
    return JSONResponse(status_code=503, content={"detail": "Data store unavailable. Retry shortly."})


@app.get("/api/health", tags=["meta"])
def health():
    """Liveness plus dataset coverage and entity counts.

    The client renders every "129 drivers"-style figure from this payload
    rather than hardcoding it in copy, so the text cannot go stale when the
    dataset changes.
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT MIN(season) AS lo, MAX(season) AS hi, COUNT(*) AS races,"
            " COUNT(DISTINCT season) AS seasons FROM races"
        ).fetchone()
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("results", "drivers", "constructors", "circuits")
        }
        mapped = conn.execute("SELECT COUNT(*) FROM circuits WHERE has_map = 1").fetchone()[0]
    finally:
        conn.close()
    return {
        "status": "ok",
        "season_from": row["lo"],
        "season_to": row["hi"],
        "seasons": row["seasons"],
        "races": row["races"],
        "results": counts["results"],
        "drivers": counts["drivers"],
        "constructors": counts["constructors"],
        "circuits": counts["circuits"],
        "circuits_with_map": mapped,
        "live_data": False,
        # Which store actually answered, and what it can answer. Stated so a
        # reader never has to infer the backend from the numbers.
        **backends.describe(),
    }
