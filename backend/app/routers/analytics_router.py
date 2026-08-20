"""Advanced analytics endpoints.

Kept under the existing entity paths (`/api/drivers/{id}/teammates`) rather
than a parallel `/api/analytics/*` tree -- the resource is still the driver,
and a second namespace for the same entity would only add a decision about
which one to call.

The exceptions are `/api/analytics/metrics` and the era/dominance views, which
are not scoped to a single entity.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import advanced, analytics
from .. import backends, supabase_repo
from ..db import fetch_one_or_404, get_db

router = APIRouter()


@router.get("/analytics/metrics", tags=["analytics"])
def list_metrics():
    """The metric registry: definition, formula, source columns, edge cases,
    limitations and sample-size rule for every advanced metric.

    This is the same structure the Methodology page renders, so documentation
    and implementation cannot drift apart.
    """
    return {
        "thresholds": {
            "min_entries_for_rates": advanced.MIN_ENTRIES_FOR_RATES,
            "min_entries_for_spread": advanced.MIN_ENTRIES_FOR_SPREAD,
            "min_appearances_for_specialism": advanced.MIN_APPEARANCES_FOR_SPECIALISM,
            "min_shared_races": advanced.MIN_SHARED_RACES,
        },
        "metrics": advanced.METRICS,
    }


# --------------------------------------------------------------------------
# Driver analytics
# --------------------------------------------------------------------------

@router.get("/drivers/{driver_id}/distribution", tags=["drivers"])
def driver_distribution(
    driver_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    season: int | None = Query(None, ge=1950, le=2100),
):
    """Finishing distribution: median, spread, IQR and a position histogram.

    The mean alone cannot distinguish a driver who is reliably 5th from one
    alternating podiums with retirements. These do.
    """
    row = fetch_one_or_404(conn, "drivers", driver_id)
    if season is not None:
        # The view aggregates a whole career; a season filter is not
        # expressible against it without a second view. Served from SQLite and
        # not claimed as Supabase-backed.
        return advanced.distribution(conn, driver_id=row["id"], season=season)
    return backends.serve(
        "distribution",
        lambda: advanced.distribution(conn, driver_id=row["id"]),
        lambda: supabase_repo.distribution(row["slug"]),
    )


@router.get("/drivers/{driver_id}/qualifying", tags=["drivers"])
def driver_qualifying(driver_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """Career qualifying record.

    `qualifying_p1` counts fastest-qualifier classifications. It is NOT a pole
    count and must not be presented as one: the two diverge in the sprint era
    (2021 awarded pole to the sprint winner) and one case remains unexplained.
    The field name says exactly what was counted.
    """
    row = fetch_one_or_404(conn, "drivers", driver_id)
    stats = backends.serve(
        "driver_qualifying",
        lambda: analytics.driver_qualifying_stats(conn, row["id"]),
        lambda: supabase_repo.driver_qualifying_payload(row["slug"]),
    )
    since = stats.get("coverage_from")
    return {
        **stats,
        # Built from the measured coverage boundary, never a literal year.
        "coverage_note": (
            f"Qualifying is essentially complete from {since}. The source "
            f"carries little before that, so early-career totals may "
            f"understate."
            if since else "Qualifying coverage could not be determined."
        ),
        "qualifying_p1_note": (
            "Fastest-qualifier classifications, not official pole positions."
        ),
    }


@router.get("/drivers/{driver_id}/teammates", tags=["drivers"])
def driver_teammates(driver_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """Head-to-head against every teammate, grouped by constructor spell.

    Only races where both drivers started for the same constructor are
    counted, which removes the distortion from unequal season lengths and
    mid-season replacements.
    """
    row = fetch_one_or_404(conn, "drivers", driver_id)
    return backends.serve(
        "teammate_records",
        lambda: {
            "summary": advanced.teammate_summary(conn, row["id"]),
            "spells": advanced.teammate_records(conn, row["id"]),
            "methodology": advanced.METRICS_BY_KEY["teammate_h2h"],
        },
        lambda: supabase_repo.teammates_payload(row["slug"]),
    )


@router.get("/drivers/{driver_id}/circuits", tags=["drivers"])
def driver_circuits(
    driver_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    min_appearances: int = Query(advanced.MIN_APPEARANCES_FOR_SPECIALISM, ge=1, le=30),
):
    """Per-circuit record, each compared against the driver's own career average."""
    row = fetch_one_or_404(conn, "drivers", driver_id)
    return backends.serve(
        "driver_circuits",
        lambda: {
            "circuits": advanced.circuit_profile(conn, row["id"], min_appearances),
            "min_appearances": min_appearances,
            "methodology": advanced.METRICS_BY_KEY["circuit_specialism"],
        },
        lambda: {
            "circuits": supabase_repo.driver_circuit_profile(row["slug"], min_appearances),
            "min_appearances": min_appearances,
            "methodology": advanced.METRICS_BY_KEY["circuit_specialism"],
        },
    )


# --------------------------------------------------------------------------
# Constructor analytics
# --------------------------------------------------------------------------

@router.get("/constructors/{constructor_id}/distribution", tags=["constructors"])
def constructor_distribution(
    constructor_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    season: int | None = Query(None, ge=1950, le=2100),
):
    row = fetch_one_or_404(conn, "constructors", constructor_id)
    if season is not None:
        # The view aggregates every season; a season filter is not expressible
        # against it without a second view. Served from SQLite and not claimed
        # as Supabase-backed.
        return advanced.distribution(conn, constructor_id=row["id"], season=season)
    return backends.serve(
        "constructor_distribution",
        lambda: advanced.distribution(conn, constructor_id=row["id"]),
        lambda: supabase_repo.constructor_distribution(row["slug"]),
    )


# --------------------------------------------------------------------------
# Circuit analytics
# --------------------------------------------------------------------------

@router.get("/circuits/{circuit_id}/specialists", tags=["circuits"])
def circuit_specialists(
    circuit_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    min_appearances: int = Query(advanced.MIN_APPEARANCES_FOR_SPECIALISM, ge=1, le=30),
):
    """Drivers who outperformed their own career norm here.

    Ranked by the delta rather than raw results, so a midfield driver who
    reliably over-delivered is not buried beneath front-runners who were
    quick everywhere.
    """
    row = fetch_one_or_404(conn, "circuits", circuit_id)
    return {
        "specialists": backends.serve(
            "circuit_specialists",
            lambda: advanced.circuit_specialists(conn, row["id"], min_appearances),
            lambda: supabase_repo.circuit_specialists_list(row["slug"], min_appearances),
        ),
        "min_appearances": min_appearances,
        "methodology": advanced.METRICS_BY_KEY["circuit_specialism"],
    }


# --------------------------------------------------------------------------
# Season and era analytics
# --------------------------------------------------------------------------

@router.get("/seasons/{season}/dominance", tags=["seasons"])
def season_dominance(season: int, conn: sqlite3.Connection = Depends(get_db)):
    """How concentrated a season's wins were, normalised by races held."""
    result = backends.serve(
        "season_dominance",
        lambda: advanced.season_dominance(conn, season),
        lambda: supabase_repo.season_dominance(season),
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"No races recorded for season {season}")
    return result


@router.get("/analytics/dominance", tags=["analytics"])
def dominance_timeline(conn: sqlite3.Connection = Depends(get_db)):
    """Per-season concentration across the dataset: how many drivers and teams
    won races each year, and the leader's share."""
    return {
        "seasons": backends.serve(
            "dominance_timeline",
            lambda: advanced.dominance_timeline(conn),
            lambda: supabase_repo.dominance_timeline(),
        ),
        "methodology": advanced.METRICS_BY_KEY["season_dominance"],
    }


@router.get("/analytics/eras", tags=["analytics"])
def eras(conn: sqlite3.Connection = Depends(get_db)):
    """Decade-level aggregates.

    Periods are described, not ranked: regulations, calendar length and field
    size all changed across these boundaries.
    """
    return {
        "eras": backends.serve(
            "era_summary",
            lambda: advanced.era_summary(conn),
            supabase_repo.era_summary,
        ),
        "caveat": (
            "Decades are presented as periods, not as a ranking. Regulations, calendar length, "
            "field size and scoring systems all changed across these boundaries, so totals are not "
            "directly equivalent between them."
        ),
    }
