"""Drivers, constructors and circuits.

Every list endpoint filters, sorts and paginates in SQL. Query parameters
are constrained by FastAPI so out-of-range or unknown values return 422
before any query runs.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query

from .. import analytics, schemas
from ..db import fetch_one_or_404, get_db

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
    constructor_id: int | None = Query(None, ge=1),
    min_entries: int = Query(1, ge=1),
    page: dict = Depends(_pagination),
    seasons: dict = Depends(_season_range),
):
    return analytics.leaderboard(
        conn, "driver", sort=sort, search=search, constructor_id=constructor_id,
        min_entries=min_entries, **page, **seasons,
    )


@router.get("/drivers/{driver_id}", tags=["drivers"])
def get_driver(driver_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """One driver, addressed by slug ("hamilton") or by legacy integer id.

    `slug` is returned alongside `id` so a client can migrate its links
    without a second request, and so the payload carries the identifier that
    is portable between backends.
    """
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


@router.get("/drivers/{driver_id}/seasons", response_model=list[schemas.SeasonStats], tags=["drivers"])
def get_driver_seasons(driver_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """Season-by-season block. Powers wins-by-season and average-position charts."""
    row = fetch_one_or_404(conn, "drivers", driver_id)
    return analytics.by_season(conn, "driver", row["id"])


# --------------------------------------------------------------------------
# Constructors
# --------------------------------------------------------------------------

@router.get("/constructors", response_model=schemas.Page, tags=["constructors"])
def list_constructors(
    conn: sqlite3.Connection = Depends(get_db),
    sort: SortKey = "wins",
    search: str | None = Query(None, max_length=100),
    min_entries: int = Query(1, ge=1),
    page: dict = Depends(_pagination),
    seasons: dict = Depends(_season_range),
):
    # The browsable index is the one place hidden constructors are withheld.
    # Their detail pages still resolve by id, and every aggregate still counts
    # them -- see analytics.HIDDEN_CONSTRUCTORS.
    return analytics.leaderboard(
        conn,
        "constructor",
        sort=sort,
        search=search,
        min_entries=min_entries,
        exclude_hidden=True,
        **page,
        **seasons,
    )


@router.get("/constructors/{constructor_id}", tags=["constructors"])
def get_constructor(constructor_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """One constructor, addressed by slug ("ferrari") or by legacy integer id."""
    row = fetch_one_or_404(conn, "constructors", constructor_id)
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "nationality": row["nationality"],
        "stats": analytics.entity_stats(conn, "constructor", row["id"]),
        "seasons": analytics.by_season(conn, "constructor", row["id"]),
    }


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
    return analytics.constructor_driver_contribution(conn, row["id"], season)


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
    params: list = []
    if search:
        sql += " WHERE c.name LIKE ? ESCAPE '\\' OR c.country LIKE ? ESCAPE '\\'"
        params += [analytics.like_pattern(search)] * 2
    return [dict(row) for row in conn.execute(sql + " ORDER BY c.name", params)]


@router.get("/circuits/{circuit_id}", tags=["circuits"])
def get_circuit(circuit_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """One circuit, addressed by slug ("monza") or by legacy integer id."""
    row = fetch_one_or_404(conn, "circuits", circuit_id)
    resolved = row["id"]
    return {
        **dict(row),
        "has_map": bool(row["has_map"]),
        "stats": analytics.entity_stats(conn, "circuit", resolved),
        "winners": analytics.circuit_winners(conn, resolved),
        "top_drivers": analytics.leaderboard(conn, "driver", circuit_id=resolved, limit=10)["items"],
        "top_constructors": analytics.leaderboard(conn, "constructor", circuit_id=resolved, limit=10)["items"],
    }
