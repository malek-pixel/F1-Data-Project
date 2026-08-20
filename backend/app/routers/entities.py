"""Drivers, constructors and circuits.

Every list endpoint filters, sorts and paginates in SQL. Query parameters
are constrained by FastAPI so out-of-range or unknown values return 422
before any query runs.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import analytics, backends, schemas, supabase_repo
from ..db import MAX_ID, fetch_one_or_404, get_db

router = APIRouter()

SortKey = Literal["wins", "podiums", "entries", "win_rate", "podium_rate", "avg_position", "name"]


def _pagination(
    limit: int = Query(50, ge=1, le=200, description="Page size."),
    offset: int = Query(0, ge=0),
) -> dict:
    return {"limit": limit, "offset": offset}


def _season_range(
    season_from: int | None = Query(None, ge=1950, le=2100),
    season_to: int | None = Query(None, ge=1950, le=2100),
) -> dict:
    return {"season_from": season_from, "season_to": season_to}


# --------------------------------------------------------------------------
# Drivers
# --------------------------------------------------------------------------

@router.get("/drivers", response_model=schemas.Page, tags=["drivers"])
def list_drivers(
    conn: sqlite3.Connection = Depends(get_db),
    sort: SortKey = "wins",
    search: str | None = Query(None, max_length=100),
    constructor_id: int | None = Query(None, ge=1, le=MAX_ID),
    min_entries: int = Query(1, ge=1, le=1000),
    page: dict = Depends(_pagination),
    seasons: dict = Depends(_season_range),
):
    # Search and the season/constructor filters have no Supabase
    # implementation, so a request using them is served by SQLite even when
    # Supabase is selected. That is not a silent fallback: `serve` is only
    # reached for the unfiltered case, and the filtered case never claims to
    # be answered by Supabase.
    filtered = search or constructor_id or seasons["season_from"] or seasons["season_to"]
    if filtered:
        return analytics.leaderboard(
            conn, "driver", sort=sort, search=search, constructor_id=constructor_id,
            min_entries=min_entries, **page, **seasons,
        )
    return backends.serve(
        "leaderboard",
        lambda: analytics.leaderboard(
            conn, "driver", sort=sort, min_entries=min_entries, **page, **seasons,
        ),
        lambda: supabase_repo.leaderboard_page(
            "driver", sort=sort, min_entries=min_entries, **page,
        ),
    )


@router.get("/drivers/{driver_id}", tags=["drivers"])
def get_driver(driver_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """One driver, addressed by slug ("hamilton") or by legacy integer id.

    `slug` is returned alongside `id` so a client can migrate its links
    without a second request, and so the payload carries the identifier that
    is portable between backends.
    """
    def from_sqlite():
        row = fetch_one_or_404(conn, "drivers", driver_id)
        return {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "nationality": row["nationality"],
            "date_of_birth": row["date_of_birth"],
            "abbreviation": row["abbreviation"],
            "permanent_number": row["permanent_number"],
            "stats": analytics.entity_stats(conn, "driver", row["id"]),
            "constructors": analytics.driver_constructor_history(conn, row["id"]),
        }

    def from_supabase():
        # Resolve the slug through SQLite first so a legacy integer id still
        # addresses the right driver: ids are store-local, so passing one
        # straight to Postgres would return a different person.
        row = fetch_one_or_404(conn, "drivers", driver_id)
        detail = supabase_repo.driver_detail(row["slug"])
        if detail is None:
            raise HTTPException(status_code=404, detail=f"No driver {driver_id!r}")
        return detail

    return backends.serve("driver_by_slug", from_sqlite, from_supabase)


@router.get("/drivers/{driver_id}/seasons", response_model=list[schemas.SeasonStats], tags=["drivers"])
def get_driver_seasons(driver_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """Season-by-season block. Powers wins-by-season and average-position charts."""
    row = fetch_one_or_404(conn, "drivers", driver_id)
    return backends.serve(
        "driver_seasons",
        lambda: analytics.by_season(conn, "driver", row["id"]),
        lambda: supabase_repo.driver_seasons_detail(row["slug"]),
    )


# --------------------------------------------------------------------------
# Constructors
# --------------------------------------------------------------------------

@router.get("/constructors", response_model=schemas.Page, tags=["constructors"])
def list_constructors(
    conn: sqlite3.Connection = Depends(get_db),
    sort: SortKey = "wins",
    search: str | None = Query(None, max_length=100),
    min_entries: int = Query(1, ge=1, le=1000),
    page: dict = Depends(_pagination),
    seasons: dict = Depends(_season_range),
):
    # The browsable index is the one place hidden constructors are withheld.
    # Their detail pages still resolve by id, and every aggregate still counts
    # them -- see analytics.HIDDEN_CONSTRUCTORS.
    filtered = search or seasons["season_from"] or seasons["season_to"]
    if filtered:
        # Search and the season range have no Supabase implementation, so a
        # request using them is served by SQLite even when Supabase is
        # selected. `serve` is simply not reached, so nothing claims to be
        # Supabase-backed when it is not.
        return analytics.leaderboard(
            conn, "constructor", sort=sort, search=search, min_entries=min_entries,
            exclude_hidden=True, **page, **seasons,
        )
    return backends.serve(
        "leaderboard",
        lambda: analytics.leaderboard(
            conn, "constructor", sort=sort, min_entries=min_entries,
            exclude_hidden=True, **page, **seasons,
        ),
        lambda: supabase_repo.leaderboard_page(
            "constructor", sort=sort, min_entries=min_entries, exclude_hidden=True, **page,
        ),
    )


@router.get("/constructors/{constructor_id}", tags=["constructors"])
def get_constructor(constructor_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """One constructor, addressed by slug ("ferrari") or by legacy integer id."""
    row = fetch_one_or_404(conn, "constructors", constructor_id)
    return backends.serve(
        "constructor_by_slug",
        lambda: {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "nationality": row["nationality"],
            "stats": analytics.entity_stats(conn, "constructor", row["id"]),
            "seasons": analytics.by_season(conn, "constructor", row["id"]),
        },
        lambda: supabase_repo.constructor_detail(row["slug"]),
    )


@router.get(
    "/constructors/{constructor_id}/drivers",
    response_model=list[schemas.DriverContribution],
    tags=["constructors"],
)
def get_constructor_drivers(
    constructor_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    season: int | None = Query(None, ge=1950, le=2100),
):
    """Driver contribution: share of the team's entries, wins and podiums."""
    row = fetch_one_or_404(conn, "constructors", constructor_id)
    if season is not None:
        # The contribution view covers a whole career; a season filter needs a
        # second view. Served from SQLite and not claimed as Supabase-backed.
        return analytics.constructor_driver_contribution(conn, row["id"], season)
    return backends.serve(
        "constructor_drivers",
        lambda: analytics.constructor_driver_contribution(conn, row["id"], None),
        lambda: supabase_repo.constructor_driver_contribution(row["slug"]),
    )


# --------------------------------------------------------------------------
# Circuits
# --------------------------------------------------------------------------

@router.get("/circuits", response_model=list[schemas.Circuit], tags=["circuits"])
def list_circuits(
    conn: sqlite3.Connection = Depends(get_db),
    search: str | None = Query(None, max_length=100),
):
    # Race count and leading winner come with the list so the circuit table can
    # be rendered from one request. Both are indexed lookups over 39 rows; the
    # alternative was a request per circuit to fill one column.
    sql = """
        SELECT c.id, c.slug, c.name, c.country, c.has_map,
               (SELECT COUNT(*) FROM races ra WHERE ra.circuit_id = c.id) AS races,
               (
                 SELECT d.name
                 FROM results r
                 JOIN races ra2 ON ra2.id = r.race_id
                 JOIN drivers d ON d.id = r.driver_id
                 WHERE ra2.circuit_id = c.id AND r.position = 1
                 GROUP BY d.id
                 ORDER BY COUNT(*) DESC, d.name
                 LIMIT 1
               ) AS top_winner,
               (
                 SELECT COUNT(*)
                 FROM results r
                 JOIN races ra3 ON ra3.id = r.race_id
                 WHERE ra3.circuit_id = c.id AND r.position = 1
                 GROUP BY r.driver_id
                 ORDER BY COUNT(*) DESC
                 LIMIT 1
               ) AS top_winner_wins
        FROM circuits c
    """
    def from_sqlite():
        params: list = []
        clause = ""
        if search:
            clause = " WHERE c.name LIKE ? ESCAPE '\' OR c.country LIKE ? ESCAPE '\'"
            params += [analytics.like_pattern(search)] * 2
        return [dict(row) for row in conn.execute(sql + clause + " ORDER BY c.name", params)]

    if search:
        # Circuit search has no Supabase implementation, so `serve` is simply
        # not reached and nothing claims to be Supabase-backed when it is not.
        return from_sqlite()
    return backends.serve("circuits", from_sqlite, supabase_repo.circuits_list)


@router.get("/circuits/{circuit_id}", tags=["circuits"])
def get_circuit(circuit_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """One circuit, addressed by slug ("monza") or by legacy integer id."""
    row = fetch_one_or_404(conn, "circuits", circuit_id)
    resolved = row["id"]

    def from_sqlite():
        return {
            **dict(row),
            "has_map": bool(row["has_map"]),
            # The listing carries `races` and the detail page renders it in three
            # places -- the card subtitle, the header line and the RACES cell --
            # but this payload never included it, so all three read as an em dash
            # on every circuit. Counted here rather than derived from `winners`,
            # which holds only the races that have a recorded winner.
            "races": conn.execute(
                "SELECT COUNT(*) FROM races WHERE circuit_id = ?", [resolved]
            ).fetchone()[0],
            "stats": analytics.entity_stats(conn, "circuit", resolved),
            "winners": analytics.circuit_winners(conn, resolved),
            "top_drivers": analytics.leaderboard(conn, "driver", circuit_id=resolved, limit=10)["items"],
            "top_constructors": analytics.leaderboard(conn, "constructor", circuit_id=resolved, limit=10)["items"],
        }

    return backends.serve(
        "circuit_by_slug",
        from_sqlite,
        lambda: supabase_repo.circuit_detail(row["slug"]),
    )
