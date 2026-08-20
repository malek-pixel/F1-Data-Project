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

from . import backends, observability, supabase_repo
from .db import connect
from .routers import analysis, analytics_router, calendar, entities

# Before anything else logs, so the startup lines below carry the same format
# and request-id field as everything after them.
observability.configure_logging()

log = logging.getLogger(__name__)

# Fail at import, not on the first request. A backend misconfiguration is a
# deployment error; discovering it as an intermittent 503 later is strictly
# worse than refusing to start.
ACTIVE_BACKEND = backends.check_ready()
log.info("Serving from backend: %s", ACTIVE_BACKEND)

# Said out loud at startup rather than left to be assumed. "Is error reporting
# on?" is the question nobody asks until they need the answer to have been yes.
log.info("Error reporting: %s", observability.configure_error_reporting())

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

# Added before CORS so it is *outermost* at runtime -- Starlette applies
# middleware in reverse order of registration. That matters: a request
# rejected by CORS should still appear in the access log, and a request that
# fails inside CORS handling should still get a request id. An access log that
# cannot see the requests another middleware turned away is not an access log.
app.add_middleware(observability.AccessLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

for module in (entities, calendar, analysis, analytics_router):
    app.include_router(module.router, prefix="/api")


def _error(status: int, detail: str) -> JSONResponse:
    """Every error body, built in one place.

    Carries the request id alongside the safe message. That is the half of
    observability the log cannot provide on its own: a reader who can quote
    `request_id` turns "a page broke sometime this afternoon" into one grep.
    It is safe to expose -- it is a random token this process minted (or a
    validated one a proxy sent), and it identifies a log line, not a user.

    `detail` keeps its exact wording and position. The frontend reads that key
    and renders it verbatim, so it is a contract, not a message.
    """
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "request_id": observability.current_request_id.get()},
        headers={"X-Request-ID": observability.current_request_id.get()},
    )


STORE_UNAVAILABLE = "Data store unavailable. Retry shortly."


@app.exception_handler(sqlite3.Error)
async def database_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
    """Log the real error, return a safe one.

    Database internals never reach the client; the server log keeps the detail.
    """
    log.exception("Database error on %s", request.url.path)
    return _error(503, STORE_UNAVAILABLE)


@app.exception_handler(supabase_repo.SupabaseError)
async def supabase_error(request: Request, exc: Exception) -> JSONResponse:
    """The Supabase leg's equivalent of the handler above.

    Only sqlite3.Error was handled, so a Supabase outage escaped as a bare
    500 "Internal Server Error" with no JSON body -- against the documented
    contract (503, retryable, `{"detail"}`) and against the client, which
    reads `detail` to tell a reader what to do. Verified by pointing
    SUPABASE_URL at a dead host.

    The message is deliberately generic and the real error goes to the log:
    the URL and key live in the exception text.
    """
    log.exception("Supabase error on %s", request.url.path)
    return _error(503, STORE_UNAVAILABLE)


@app.exception_handler(backends.CapabilityMissing)
async def capability_missing(request: Request, exc: Exception) -> JSONResponse:
    """An endpoint the selected backend cannot serve.

    501 rather than 503: retrying will not help, because nothing is broken --
    this backend simply has no implementation. The distinction matters to a
    client deciding whether to back off and try again.
    """
    log.warning("Capability missing on %s: %s", request.url.path, exc)
    return _error(501, "This endpoint is not available on the active data store.")


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """The gap the other three handlers left open.

    Everything above catches a *named* failure. Anything else -- a TypeError
    in an analytics function, a KeyError on a row shape that changed -- escaped
    as a bare 500 with Starlette's `Internal Server Error` as plain text and no
    JSON body at all. That breaks the documented contract in the same way the
    Supabase gap did before it was handled: the client reads `detail` to decide
    what to tell a reader, and a body without one falls through to the generic
    fallback in `services/api.ts`.

    So: the same safe body as every other failure, and the real exception --
    with its traceback and request id -- to the log and to Sentry when it is
    configured. The wording says "unexpected" rather than "retry shortly"
    because, unlike a store outage, retrying an unhandled bug is not advice
    anyone should be given.
    """
    log.exception("Unhandled error on %s", request.url.path)
    return _error(500, "Something went wrong handling this request. It has been logged.")


def _health_sqlite() -> dict:
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


@app.get("/api/health", tags=["meta"])
def health():
    """Liveness plus dataset coverage and entity counts.

    The client renders every "129 drivers"-style figure from this payload
    rather than hardcoding it in copy, so the text cannot go stale when the
    dataset changes.

    Dispatched through `backends.serve` like every other route, and NOT
    hardwired to SQLite. That distinction is the whole point of a health
    check: this endpoint reads SQLite unconditionally, so with
    F1_BACKEND=supabase and Supabase unreachable, every real route returned
    503 while this one returned 200 "ok". An uptime check pointed here --
    which is exactly what docs/OPERATIONS.md recommends as the first thing to
    add -- would have reported the application healthy while it served
    nothing. Now a store outage surfaces here as the same 503 a client gets.
    """
    payload = backends.serve("health", _health_sqlite, supabase_repo.health)
    return {
        **payload,
        # Which store actually answered, and what it can answer. Stated so a
        # reader never has to infer the backend from the numbers.
        **backends.describe(),
    }
