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


class SeasonStats(Stats):
    season: int


class ConstructorSpell(SeasonStats):
    constructor_id: int
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
    winner_driver: str | None = Field(
        default=None, description="Null when the source carries no position-1 row for this race."
    )
    winner_constructor_id: int | None = None
    winner_constructor: str | None = None


class RaceResult(BaseModel):
    position: int
    driver_id: int
    driver_name: str
    constructor_id: int
    constructor_name: str


class ErrorResponse(BaseModel):
    """Structured error body. Stack traces are never included."""

    detail: str
