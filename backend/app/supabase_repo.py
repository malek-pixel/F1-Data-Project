"""Supabase-backed data access. NOT WIRED INTO THE RUNNING API.

STATUS -- READ THIS FIRST
-------------------------
Nothing imports this module except its own tests. The shipped data path is:

    React -> FastAPI -> SQLite (data/f1.db, built by backend/etl/build.py)

This module is a second, parallel materialisation of the same CSV in
PostgreSQL, kept because the schema, migrations and analytical views in
`docs/database.md` are real work and are the intended production target. It is
not currently on any request path, and no router calls it. Its tests skip
entirely when SUPABASE_URL / SUPABASE_ANON_KEY are unset, which is the default
for a fresh clone -- so "the tests pass" says nothing about this file.

Treat every claim below as describing the Supabase deployment, not the
application you get by following README.md. Wiring it in means adding a
backend switch in `db.py` and routing the routers through it; until that
exists, `backend/app/analytics.py` remains the only implementation that serves
a request.

READ-ONLY BY DESIGN
-------------------
Only the publishable/anon key is used here, and RLS grants that key SELECT
only. The API physically cannot write, verified by the security tests. The
service-role key is never imported, never logged and never sent to the browser;
ingestion is a separate server-side script.

WHY POSTGREST RATHER THAN A DIRECT CONNECTION
---------------------------------------------
PostgREST needs only the project URL and publishable key, both safe to hold in
application config, whereas a direct psycopg connection needs the database
password. Fewer secrets in more places is the wrong trade for a read-only
analytical API.

ANALYTICS LIVE IN THE DATABASE
------------------------------
Every aggregate is a view (v_driver_career_stats, v_teammate_comparisons, ...),
so this module selects and filters -- it does not calculate. That keeps the
"one definition per metric" rule intact across both backends.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Imported for its side effect: populates os.environ from .env before the
# constants below are read. These are module-level, so load order matters.
from . import env as _env  # noqa: F401

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# Timeout so a hung upstream surfaces as a clean 503 rather than a stuck worker.
TIMEOUT_SECONDS = 10


class SupabaseError(RuntimeError):
    """Upstream failure. Callers translate this into a 503."""


def configured() -> bool:
    """True when Supabase credentials are present.

    Read by this module's tests to decide whether to run or skip. It is *not*
    a runtime backend switch: no router consults it, so setting the variables
    does not move the API off SQLite. Both stores are produced by the same
    pipeline from the same CSV, so they are one source of truth with two
    materialisations -- not two competing datasets.
    """
    return bool(SUPABASE_URL and SUPABASE_KEY)


def query(
    resource: str,
    select: str = "*",
    filters: dict[str, str] | None = None,
    order: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    exact_count: bool = False,
) -> tuple[list[dict[str, Any]], int | None]:
    """Run a PostgREST query. Returns (rows, total) -- total only when asked.

    Filters use PostgREST operator syntax (`eq.5`, `gte.2010`, `ilike.*ham*`)
    and are URL-encoded here; no value is ever concatenated into a raw SQL
    string, and the anon role cannot reach anything RLS does not allow.
    """
    if not configured():
        raise SupabaseError("Supabase is not configured")

    params: dict[str, str] = {"select": select}
    params.update(filters or {})
    if order:
        params["order"] = order
    if limit is not None:
        params["limit"] = str(limit)
    if offset:
        params["offset"] = str(offset)

    url = f"{SUPABASE_URL}/rest/v1/{resource}?{urllib.parse.urlencode(params)}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    # `count=exact` returns the pre-pagination total in Content-Range, which is
    # what paginated list endpoints need and what avoids a second round trip.
    if exact_count:
        headers["Prefer"] = "count=exact"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            rows = json.loads(response.read().decode("utf-8"))
            total = None
            if exact_count:
                content_range = response.headers.get("Content-Range", "")
                if "/" in content_range:
                    tail = content_range.rsplit("/", 1)[1]
                    total = int(tail) if tail.isdigit() else None
            return rows, total
    except urllib.error.HTTPError as error:
        # Upstream detail goes to the server log, never to the client.
        raise SupabaseError(f"Supabase returned {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SupabaseError("Supabase unreachable") from error


def health() -> dict:
    """Coverage and entity counts, read from the analytical views."""
    seasons, _ = query("v_season_stats", select="season,races")
    counts = {}
    for name, resource in (
        ("drivers", "drivers"),
        ("constructors", "constructors"),
        ("circuits", "circuits"),
        ("results", "results"),
    ):
        _, total = query(resource, select="id", limit=1, exact_count=True)
        counts[name] = total or 0

    years = [row["season"] for row in seasons]
    return {
        "status": "ok",
        "backend": "supabase",
        "season_from": min(years) if years else None,
        "season_to": max(years) if years else None,
        "seasons": len(years),
        "races": sum(row["races"] for row in seasons),
        "results": counts["results"],
        "drivers": counts["drivers"],
        "constructors": counts["constructors"],
        "circuits": counts["circuits"],
        "live_data": False,
    }


def driver_career_stats(driver_id: int) -> dict | None:
    rows, _ = query("v_driver_career_stats", filters={"driver_id": f"eq.{driver_id}"})
    return rows[0] if rows else None


def teammate_records(driver_id: int) -> list[dict]:
    rows, _ = query(
        "v_teammate_comparisons",
        filters={"driver_id": f"eq.{driver_id}"},
        order="shared_races.desc",
    )
    return rows


def records() -> list[dict]:
    rows, _ = query("v_records")
    return rows


def metric_definitions() -> list[dict]:
    rows, _ = query("metric_definitions", filters={"active": "eq.true"}, order="metric_key")
    return rows
