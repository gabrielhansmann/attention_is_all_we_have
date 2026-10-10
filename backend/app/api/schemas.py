"""Response models for the HTTP API. They mirror the retrieval tools' dataclasses so the frontend
always receives a citation (file, locator, verbatim quote) next to every piece of evidence."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

Line = Literal["F70", "G60", "G68", "G70"]
Market = Literal["EU", "CN", "US", "RoW"]
Polarity = Literal["positive", "negative", "request"]
Powertrain = Literal["ICE", "PHEV", "BEV"]
EvidenceKind = Literal["feedback", "pdf_text", "option", "study", "sales"]
GroupBy = Literal["vehicle_line", "market_code", "country", "powertrain", "polarity", "feedback_type", "domain"]


class CitationOut(BaseModel):
    kind: str
    id: str
    file: str
    locator: str
    quote: str


class HitOut(BaseModel):
    citation: CitationOut
    text: str
    meta: dict[str, Any] = {}
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    source: Literal["feedback", "docs"]
    hits: list[HitOut]


class StatRow(BaseModel):
    key: str | None
    n: int


class StatsResponse(BaseModel):
    group_by: str
    total: int
    rows: list[StatRow]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "unavailable", "not_configured"]
    openai_key: bool
    version: str
