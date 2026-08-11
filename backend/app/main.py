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

from .db import connect
from .routers import analysis, analytics_router, calendar, entities

log = logging.getLogger(__name__)

# Origins are configured, never wildcarded -- the default covers the local
# Vite dev server only.
ALLOWED_ORIGINS = os.getenv("F1_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

app = FastAPI(
    title="F1 Data Project API",
    version="1.0.0",
    description=(
        "Analytical API over 2000-2025 Formula 1 race classifications.\n\n"
        "Every derived number is defined once in `backend/app/analytics.py`. "
        "Qualifying, points, finishing status, lap times and car specifications are "
        "absent from the source data and are never estimated -- see `/api/dataset/summary`."
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
    }
