"""Seasons and races."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import analytics, schemas
from ..db import get_db

router = APIRouter()

# The winner rides along with every race row: the race table shows it, and a
# request per race to fill one column is the N+1 this avoids. LEFT JOIN, so a
# race with no recorded position-1 row still appears.
RACE_SELECT = """
    SELECT ra.id, ra.season, ra.round, ra.name, ra.date,
           ra.circuit_id, ci.name AS circuit_name, ci.slug AS circuit_slug,
           d.id AS winner_driver_id, d.name AS winner_driver,
           c.id AS winner_constructor_id, c.name AS winner_constructor
    FROM races ra
    JOIN circuits ci        ON ci.id = ra.circuit_id
    LEFT JOIN results r     ON r.race_id = ra.id AND r.position = 1
    LEFT JOIN drivers d     ON d.id = r.driver_id
    LEFT JOIN constructors c ON c.id = r.constructor_id
"""


@router.get("/seasons", tags=["seasons"])
def list_seasons(conn: sqlite3.Connection = Depends(get_db)):
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT ra.season, COUNT(DISTINCT ra.id) AS races, COUNT(r.id) AS entries,
                   COUNT(DISTINCT r.driver_id) AS drivers, COUNT(DISTINCT r.constructor_id) AS constructors
            FROM races ra LEFT JOIN results r ON r.race_id = ra.id
            GROUP BY ra.season ORDER BY ra.season DESC
            """
        )
    ]


@router.get("/seasons/{season}", tags=["seasons"])
def get_season(season: int, conn: sqlite3.Connection = Depends(get_db)):
    """Season detail: the championship standings, plus wins-ordered tables.

    Two different things are returned and they must not be conflated.

    `standings` is the real championship -- race plus sprint points, verified
    to reproduce the official champion and points total for every covered
    season. This is what a reader means by "the standings".

    `drivers` / `constructors` are ordered by wins, and `ranking_basis` says
    so. They answer "who won the most races", which is a different question;
    a driver can top that table without winning the championship. They are
    retained because existing consumers read them.

    The docstring here previously said these were NOT standings "because the
    source carries no points column". Points have been ingested since; the
    standings are real and the caveat was simply out of date.
    """
    summary = analytics.season_summary(conn, season)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No races recorded for season {season}")
    summary["races_list"] = [
        dict(row) for row in conn.execute(f"{RACE_SELECT} WHERE ra.season = ? ORDER BY ra.round", [season])
    ]
    return summary


@router.get("/seasons/{season}/rounds", tags=["seasons"])
def get_season_rounds(season: int, conn: sqlite3.Connection = Depends(get_db)):
    """Calendar order with each round's winner. Powers the round-by-round strip.

    `winner_driver` is null for a round the source carries no position-1 row
    for -- the round still appears, rather than the calendar looking shorter
    than it was.
    """
    rounds = analytics.season_rounds(conn, season)
    if not rounds:
        raise HTTPException(status_code=404, detail=f"No races recorded for season {season}")
    return {"season": season, "rounds": rounds}


@router.get("/races", response_model=list[schemas.Race], tags=["races"])
def list_races(
    conn: sqlite3.Connection = Depends(get_db),
    season: int | None = Query(None, ge=1950, le=2100),
    circuit_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where, params = "", []
    if season is not None:
        where += " AND ra.season = ?"
        params.append(season)
    if circuit_id is not None:
        where += " AND ra.circuit_id = ?"
        params.append(circuit_id)
    return [
        dict(row)
        for row in conn.execute(
            f"{RACE_SELECT} WHERE 1=1{where} ORDER BY ra.season DESC, ra.round LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    ]


@router.get("/races/{race_id}", tags=["races"])
def get_race(race_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Full race weekend: classification, qualifying, sprint and pit stops.

    Each session reports its own availability rather than returning a bare
    empty list. "No qualifying recorded for this race" and "nobody qualified"
    look identical in JSON otherwise, and only one of them is true.
    """
    row = conn.execute(f"{RACE_SELECT} WHERE ra.id = ?", [race_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No race with id {race_id}")

    qualifying = analytics.qualifying_results(conn, race_id)
    sprint = analytics.sprint_results(conn, race_id)
    stops = analytics.pit_stops(conn, race_id)

    return {
        **dict(row),
        "results": analytics.race_results(conn, race_id),
        "qualifying": {
            "available": bool(qualifying),
            # Why it is missing matters: pre-2003 is a known source gap, not a
            # weekend without a qualifying session.
            "unavailable_reason": None if qualifying else
                "The source carries no qualifying for this race.",
            "items": qualifying,
        },
        "sprint": {
            "available": bool(sprint),
            "unavailable_reason": None if sprint else
                "No sprint was held at this event.",
            "items": sprint,
        },
        "pit_stops": {
            "available": bool(stops),
            "unavailable_reason": None if stops else
                "Pit stop data begins in 2011; none is recorded for this race.",
            "items": stops,
        },
    }


@router.get("/seasons/{season}/standings", tags=["seasons"])
def get_standings(season: int, conn: sqlite3.Connection = Depends(get_db)):
    """Championship standings: race points plus sprint points.

    These ARE the championship, unlike the wins-ordered tables on
    `/seasons/{season}`. Verified to reproduce the official champion and exact
    points total for every season in the dataset.
    """
    drivers = analytics.standings(conn, season, "driver")
    if not drivers:
        raise HTTPException(status_code=404, detail=f"No races recorded for season {season}")
    return {
        "season": season,
        "basis": "points",
        "includes_sprint_points": True,
        "caveat": (
            "Ties are broken by wins, then podiums. The official countback "
            "rule is not implemented, so an exact points tie may order "
            "differently from the official classification."
        ),
        "drivers": drivers,
        "constructors": analytics.standings(conn, season, "constructor"),
    }
