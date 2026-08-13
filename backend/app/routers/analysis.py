"""Compare, records, insights, search and dataset introspection."""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import analytics
from ..db import fetch_one_or_404, get_db

router = APIRouter()


@router.get("/compare/{entity}", tags=["compare"])
def compare_entities(
    entity: Literal["drivers", "constructors"],
    left: int = Query(..., ge=1, description="Left entity id."),
    right: int = Query(..., ge=1, description="Right entity id."),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Head-to-head between two drivers or two constructors.

    Returns career blocks plus a shared-seasons window, and a `comparable`
    flag that is false when the careers barely overlap or either side has too
    few entries for its rates to mean anything. No winner is declared -- the
    client presents both sides and the caveats.
    """
    if left == right:
        raise HTTPException(status_code=400, detail="left and right must be different entities")
    table = entity
    for entity_id in (left, right):
        fetch_one_or_404(conn, table, entity_id)

    singular = "driver" if entity == "drivers" else "constructor"
    result = analytics.compare(conn, singular, left, right)
    result["left_name"] = conn.execute(f"SELECT name FROM {table} WHERE id = ?", [left]).fetchone()["name"]
    result["right_name"] = conn.execute(f"SELECT name FROM {table} WHERE id = ?", [right]).fetchone()["name"]
    result["methodology"] = (
        f"Career totals cover {analytics.coverage_span(conn)} only. Entry counts, era and machinery "
        "differ between entities; the shared-seasons block is the like-for-like view. "
        "Rates use entries as the denominator."
    )
    return result


@router.get("/records", tags=["insights"])
def get_records(conn: sqlite3.Connection = Depends(get_db)):
    """Dataset records. Each carries its own methodology string."""
    return {
        "scope": f"{analytics.coverage_span(conn)} race classifications",
        "records": analytics.records(conn),
    }


@router.get("/insights", tags=["insights"])
def get_insights(conn: sqlite3.Connection = Depends(get_db), limit: int = Query(6, ge=1, le=20)):
    """Calculated observations. Descriptive only -- the dataset holds no
    causal variables, so no insight asserts a cause."""
    return {"insights": analytics.insights(conn, limit)}


@router.get("/dataset/summary", tags=["dataset"])
def get_dataset_summary(conn: sqlite3.Connection = Depends(get_db)):
    """Schema shape, coverage and known issues. No server internals."""
    return analytics.dataset_summary(conn)


@router.get("/cars", tags=["cars"])
def get_car_library(conn: sqlite3.Connection = Depends(get_db)):
    """Constructor-seasons, grouped by constructor. See analytics.car_library."""
    return {
        "teams": analytics.car_library(conn),
        "unit": "constructor-season",
        "chassis_available": False,
    }


@router.get("/search", tags=["search"])
def global_search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=25),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Search drivers, constructors, circuits and seasons."""
    return {"query": q, "results": analytics.search(conn, q, limit)}
