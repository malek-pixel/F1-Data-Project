"""Response schemas.

The stat block is one model reused everywhere rather than re-declared per
endpoint -- the same guarantee analytics.py gives for the calculations, at
the serialisation layer.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Stats(BaseModel):
    """Canonical stat block. See analytics.py for every definition."""

    entries: int = Field(
        description=(
            "Race classifications, retirements included. Retirements are "
            "identifiable -- see `results.status` -- but they are entries, so "
            "they are counted here rather than filtered out."
        )
    )
    wins: int
    podiums: int
    win_rate: float | None = Field(description="wins / entries. None when entries = 0, never 0.0-by-default.")
    podium_rate: float | None = Field(description="podiums / entries.")
    avg_classified_position: float | None = Field(
        description="Mean final classification incl. retirements. NOT average finishing position."
    )
    best_classified_position: int | None
    rates_reliable: bool = Field(description="False below the minimum entry count; rates are shown but flagged.")

    # ------------------------------------------------------------------
    # Declared so they are actually served.
    #
    # analytics._stats() has computed every field below for some time, but
    # none of them were declared here -- and an undeclared key is dropped
    # during response serialisation without warning. The effect was that the
    # ingested points, finishing-status and grid data never reached any client
    # through a list endpoint, while the SQL that produced it ran on every
    # request. Nothing failed; the numbers simply were not there.
    #
    # Every one of these is None rather than 0 when the enrichment is absent:
    # "not known" and "zero" are different claims, and only one of them is
    # safe to render.
    # ------------------------------------------------------------------
    top5: int
    top10: int
    top5_rate: float | None
    top10_rate: float | None
    finishes: int | None = Field(
        default=None, description="Classified finishes. None when no status data covers these entries."
    )
    dnfs: int | None = Field(
        default=None, description="Entries that did not reach a classified finish."
    )
    dnf_rate: float | None = Field(
        default=None, description="dnfs / entries carrying a status, never / all entries."
    )
    points: float | None = Field(
        default=None, description="Championship points as scored under the rules of each season."
    )
    avg_grid: float | None = Field(
        default=None, description="Mean starting slot. Pit-lane starts (grid 0) are excluded, not counted as zero."
    )
    avg_positions_gained: float | None = Field(
        default=None, description="Mean grid minus finish, classified finishes only."
    )


class NamedStats(Stats):
    id: int
    # The portable identifier. `id` is assigned independently by each backing
    # store and is therefore meaningless across them; `slug` is not. Clients
    # should link on this.
    slug: str
    name: str
    # Carried on the listing so the library card can render it without a
    # request per row. Null only where the source has none for that entity --
    # every driver and constructor in this dataset has one.
    nationality: str | None = None


class SeasonStats(Stats):
    season: int


class ConstructorSpell(SeasonStats):
    constructor_id: int
    constructor_slug: str
    constructor_name: str


class DriverContribution(Stats):
    driver_id: int
    driver_slug: str
    driver_name: str
    entry_share: float | None
    win_share: float | None = Field(description="Share of the constructor's wins. None when the team has none.")
    podium_share: float | None


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[NamedStats]


class Circuit(BaseModel):
    id: int
    slug: str
    name: str
    country: str
    has_map: bool = Field(description="False when no track-map SVG ships; the UI shows a map-unavailable state.")
    races: int = Field(description="Races held here across the covered seasons.")
    top_winner: str | None = Field(
        default=None, description="Driver with most wins here. Null when no race here has a recorded winner."
    )
    top_winner_wins: int | None = Field(default=None, description="That driver's win count here.")


class Race(BaseModel):
    id: int
    season: int
    round: int
    name: str
    date: str
    circuit_id: int
    circuit_name: str
    circuit_slug: str
    winner_driver_id: int | None = None
    # Null alongside the id, never independently: both come from the same
    # LEFT JOIN, so a race with no recorded winner has neither.
    winner_driver_slug: str | None = None
    winner_driver: str | None = Field(
        default=None, description="Null when the source carries no position-1 row for this race."
    )
    winner_constructor_id: int | None = None
    winner_constructor_slug: str | None = None
    winner_constructor: str | None = None
    # The winner's grid slot (0 is real -- a pit-lane start) and finishing
    # status, plus whoever qualified first. Named "qualifying_first" rather
    # than "pole" because the two differ in the sprint era.
    winner_grid: int | None = None
    winner_status: str | None = None
    qualifying_first: str | None = None
    qualifying_first_slug: str | None = None


class RaceResult(BaseModel):
    position: int
    driver_id: int
    driver_slug: str
    driver_name: str
    constructor_id: int
    constructor_slug: str
    constructor_name: str
    # Nullable because a build without the enrichment CSV has none of these.
    # Null means "not known for this row", never zero.
    grid: int | None = Field(default=None, description="Starting slot. 0 is a real value: a pit-lane start.")
    laps: int | None = None
    points: float | None = Field(default=None, description="Points awarded under that season's rules.")
    status: str | None = Field(
        default=None, description="Raw source status ('Finished', '+1 Lap', 'Gearbox', ...). Not bucketed."
    )
    classification: str | None = Field(
        default=None, description="classified | retired | disqualified | withdrawn."
    )
    position_text: str | None = None
    # The official award, as published. rank 1 is the credited driver, which
    # is not necessarily whoever set the quickest time -- eligibility rules
    # apply. NULL before 2004 and for drivers who set no timed lap.
    fastest_lap_rank: int | None = None
    fastest_lap_number: int | None = None
    fastest_lap_time: str | None = None


class ErrorResponse(BaseModel):
    """Structured error body. Stack traces are never included."""

    detail: str
