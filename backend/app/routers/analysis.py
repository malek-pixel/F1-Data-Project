"""Compare, records, insights, search and dataset introspection."""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import analytics
from .. import backends, supabase_repo
from ..db import fetch_one_or_404, get_db

router = APIRouter()


@router.get("/compare/{entity}", tags=["compare"])
def compare_entities(
    entity: Literal["drivers", "constructors"],
    left: str = Query(..., min_length=1, max_length=100, description="Left entity slug (or legacy id)."),
    right: str = Query(..., min_length=1, max_length=100, description="Right entity slug (or legacy id)."),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Head-to-head between two drivers or two constructors.

    Returns career blocks plus a shared-seasons window, and a `comparable`
    flag that is false when the careers barely overlap or either side has too
    few entries for its rates to mean anything. No winner is declared -- the
    client presents both sides and the caveats.
    """
    table = entity
    # Resolve BEFORE the identity check, so `?left=hamilton&right=48` is
    # caught as the same driver twice rather than compared with itself.
    # fetch_one_or_404 takes a slug or a legacy integer id; slugs are the
    # portable key and the only one that means the same thing on both stores,
    # which is why the UI now links with them.
    left_row = fetch_one_or_404(conn, table, left)
    right_row = fetch_one_or_404(conn, table, right)
    if left_row["id"] == right_row["id"]:
        raise HTTPException(status_code=400, detail="left and right must be different entities")

    singular = "driver" if entity == "drivers" else "constructor"
    result = backends.serve(
        "compare",
        lambda: analytics.compare(conn, singular, left_row["id"], right_row["id"]),
        # Addressed by slug, never by the id in the URL: ids are store-local,
        # so passing one through would compare two different entities.
        lambda: supabase_repo.compare(singular, left_row["slug"], right_row["slug"]),
    )
    result["left_name"] = left_row["name"]
    result["right_name"] = right_row["name"]
    result["methodology"] = (
        f"Career totals cover {analytics.coverage_span(conn)} only. Entry counts, era and machinery "
        "differ between entities; the shared-seasons block is the like-for-like view. "
        "Rates use entries as the denominator."
    )
    return result


@router.get("/records", tags=["insights"])
def get_records(conn: sqlite3.Connection = Depends(get_db)):
    """Dataset records. Each carries its own methodology string."""
    return backends.serve(
        "records",
        lambda: {
            "scope": f"{analytics.coverage_span(conn)} race classifications",
            "records": analytics.records(conn),
        },
        lambda: {
            "scope": f"{supabase_repo.coverage_span()} race classifications",
            "records": supabase_repo.records_list(),
        },
    )


@router.get("/insights", tags=["insights"])
def get_insights(conn: sqlite3.Connection = Depends(get_db), limit: int = Query(6, ge=1, le=20)):
    """Calculated observations. Descriptive only -- the dataset holds no
    causal variables, so no insight asserts a cause.

    The one endpoint with no Postgres implementation, and the one that must
    therefore FAIL under Supabase rather than quietly answer from SQLite.
    `require` is called explicitly because there is no Supabase branch for
    `serve` to take -- without it this route ran the SQLite query whatever
    F1_BACKEND said, which is the exact silent fallback backends.py exists to
    forbid, on the single endpoint documented as unsupported.
    """
    backends.require("insights")
    return {"insights": analytics.insights(conn, limit)}


@router.get("/dataset/summary", tags=["dataset"])
def get_dataset_summary(conn: sqlite3.Connection = Depends(get_db)):
    """Schema shape, coverage and known issues. No server internals.

    Availability is counted from the serving store, so the answer describes
    the database actually answering the request rather than a list written
    down somewhere.
    """
    summary = analytics.dataset_summary(conn)
    summary["availability"] = backends.serve(
        "dataset_availability",
        lambda: analytics.dataset_availability(conn),
        supabase_repo.dataset_availability,
    )
    return summary


@router.get("/cars", tags=["cars"])
def get_car_library(conn: sqlite3.Connection = Depends(get_db)):
    """Constructor-seasons, grouped by constructor. See analytics.car_library."""
    return {
        "teams": analytics.car_library(conn),
        "unit": "constructor-season",
        # The `cars` table is empty in both stores and this says so rather
        # than omitting the field. Verified against the database rather than
        # hardcoded, so it becomes true on its own if a source ever appears.
        "chassis_available": bool(
            backends.serve("cars", lambda: analytics.cars(conn), supabase_repo.cars)
        ),
    }


@router.get("/search", tags=["search"])
def global_search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=25),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Search drivers, constructors, circuits and seasons."""
    results = backends.serve(
        "search",
        lambda: analytics.search(conn, q, limit),
        lambda: supabase_repo.search(q, limit),
    )
    return {"query": q, "results": results}
