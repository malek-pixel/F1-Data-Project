"""Response schemas.

The stat block is one model reused everywhere rather than re-declared per
endpoint -- the same guarantee analytics.py gives for the calculations, at
the serialisation layer.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Stats(BaseModel):
    """Canonical stat block. See analytics.py for every definition."""

    entries: int = Field(description="Race classifications. Includes retirements: the source has no status column.")
    wins: int
    podiums: int
    win_rate: float | None = Field(description="wins / entries. None when entries = 0, never 0.0-by-default.")
    podium_rate: float | None = Field(description="podiums / entries.")
    avg_classified_position: float | None = Field(
        description="Mean final classification incl. retirements. NOT average finishing position."
    )
    best_classified_position: int | None
    rates_reliable: bool = Field(description="False below the minimum entry count; rates are shown but flagged.")


class NamedStats(Stats):
    id: int
    name: str


class SeasonStats(Stats):
    season: int


class ConstructorSpell(SeasonStats):
    constructor_id: int
    constructor_name: str


class DriverContribution(Stats):
    driver_id: int
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


class Race(BaseModel):
    id: int
    season: int
    round: int
    name: str
    date: str
    circuit_id: int
    circuit_name: str
    circuit_slug: str


class RaceResult(BaseModel):
    position: int
    driver_id: int
    driver_name: str
    constructor_id: int
    constructor_name: str


class ErrorResponse(BaseModel):
    """Structured error body. Stack traces are never included."""

    detail: str
