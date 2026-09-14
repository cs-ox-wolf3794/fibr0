"""Shared data shapes. The LLM output schema lives here too so prompt and code cannot drift."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Direction = Literal["up", "down"]
Horizon = Literal["1d", "5d"]
Magnitude = Literal["small", "medium", "large"]
ImpactOrder = Literal["first", "second"]

EventCategory = Literal[
    "supply_disruption",
    "infrastructure_outage",
    "weather",
    "geopolitical",
    "policy_regulation",
    "commodity_price",
    "demand_signal",
    "earnings_guidance",
    "m_and_a",
    "corporate_action",
    "other",
]


class Slot(StrEnum):
    PRE_OPEN = "pre_open"
    MIDDAY = "midday"
    POST_CLOSE = "post_close"


class RawItem(BaseModel):
    id: int | None = None
    source_id: str
    url: str
    url_hash: str
    title: str
    body: str = ""
    published_at: datetime | None = None
    tier: int = 2


class Event(BaseModel):
    """A cluster of raw items describing one real-world event."""

    id: int | None = None
    slot: Slot
    title: str
    text_for_analysis: str
    item_ids: list[int] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_tiers: list[int] = Field(default_factory=list)

    @property
    def tier3_only(self) -> bool:
        return bool(self.source_tiers) and all(t >= 3 for t in self.source_tiers)


# --- LLM structured output -------------------------------------------------
# extra="forbid" makes pydantic emit additionalProperties: false, which the
# structured-outputs API requires. Keep these models free of numeric bounds and
# other constraints the JSON-schema subset may reject; validate ranges in code.


class TickerImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(description="US-listed ticker symbol, upper case, no exchange suffix")
    direction: Direction
    horizon: Horizon
    magnitude: Magnitude
    order: ImpactOrder = Field(
        description=(
            "first = directly named or obviously central; "
            "second = supplier, customer, competitor, or sector ETF"
        )
    )
    confidence: float = Field(
        description=(
            "Probability from 0.5 to 1.0 that the stock closes in the stated direction "
            "at the horizon, net of the XLE move"
        )
    )
    rationale: str = Field(description="One or two sentences on the causal link for this ticker")


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_summary: str = Field(description="Neutral two-sentence description of what happened")
    category: EventCategory
    rationale_raw: str = Field(
        description="Full reasoning, as long as needed. Stored backend-only, never shown to users."
    )
    rationale_summary: str = Field(
        description="Exactly two sentences for public display. No banned words. No first person."
    )
    impacts: list[TickerImpact]


# --- Published shapes -------------------------------------------------------


class Prediction(BaseModel):
    event_id: int
    ticker: str
    direction: Direction
    horizon: Horizon
    magnitude: Magnitude
    order: ImpactOrder
    raw_confidence: float
    calibrated_confidence: float
    is_calibrated: bool
    rationale_summary: str
    source_urls: list[str]
    slot: Slot
