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
def get_driver(driver_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = fetch_one_or_404(conn, "drivers", driver_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "stats": analytics.entity_stats(conn, "driver", driver_id),
        "constructors": analytics.driver_constructor_history(conn, driver_id),
    }


@router.get("/drivers/{driver_id}/seasons", response_model=list[schemas.SeasonStats], tags=["drivers"])
def get_driver_seasons(driver_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Season-by-season block. Powers wins-by-season and average-position charts."""
    fetch_one_or_404(conn, "drivers", driver_id)
    return analytics.by_season(conn, "driver", driver_id)


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
    return analytics.leaderboard(
        conn, "constructor", sort=sort, search=search, min_entries=min_entries, **page, **seasons
    )


@router.get("/constructors/{constructor_id}", tags=["constructors"])
def get_constructor(constructor_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = fetch_one_or_404(conn, "constructors", constructor_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "stats": analytics.entity_stats(conn, "constructor", constructor_id),
        "seasons": analytics.by_season(conn, "constructor", constructor_id),
    }


@router.get(
    "/constructors/{constructor_id}/drivers",
    response_model=list[schemas.DriverContribution],
    tags=["constructors"],
)
def get_constructor_drivers(
    constructor_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    season: int | None = Query(None, ge=1950, le=2100),
):
    """Driver contribution: share of the team's entries, wins and podiums.

    Share of *points* is not offered -- the source has no points column.
    """
    fetch_one_or_404(conn, "constructors", constructor_id)
    return analytics.constructor_driver_contribution(conn, constructor_id, season)


# --------------------------------------------------------------------------
# Circuits
# --------------------------------------------------------------------------

@router.get("/circuits", response_model=list[schemas.Circuit], tags=["circuits"])
def list_circuits(
    conn: sqlite3.Connection = Depends(get_db),
    search: str | None = Query(None, max_length=100),
):
    sql = "SELECT id, slug, name, country, has_map FROM circuits"
    params: list = []
    if search:
        sql += " WHERE name LIKE ? ESCAPE '\\' OR country LIKE ? ESCAPE '\\'"
        params += [analytics.like_pattern(search)] * 2
    return [dict(row) for row in conn.execute(sql + " ORDER BY name", params)]


@router.get("/circuits/{circuit_id}", tags=["circuits"])
def get_circuit(circuit_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = fetch_one_or_404(conn, "circuits", circuit_id)
    return {
        **dict(row),
        "has_map": bool(row["has_map"]),
        "stats": analytics.entity_stats(conn, "circuit", circuit_id),
        "winners": analytics.circuit_winners(conn, circuit_id),
        "top_drivers": analytics.leaderboard(conn, "driver", circuit_id=circuit_id, limit=10)["items"],
        "top_constructors": analytics.leaderboard(conn, "constructor", circuit_id=circuit_id, limit=10)["items"],
    }
