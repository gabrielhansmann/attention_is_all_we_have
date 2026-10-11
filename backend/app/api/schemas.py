"""Response models for the HTTP API. They mirror the retrieval tools' dataclasses so the frontend
always receives a citation (file, locator, verbatim quote) next to every piece of evidence."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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


class PassageOut(BaseModel):
    id: str
    label: str | None
    text: str
    cited: bool


class DocumentOut(BaseModel):
    source_id: str
    type: str
    openable: bool
    url: str | None = None      # set for a stored web page: the viewer links to it


class EvidenceContextOut(BaseModel):
    kind: str
    id: str
    file: str
    locator: str
    title: str | None
    page: int | None
    passages: list[PassageOut]
    vehicle_line: str | None
    market_code: str | None
    document: DocumentOut | None


class HitOut(BaseModel):
    citation: CitationOut
    text: str
    meta: dict[str, Any] = {}
    score: float | None = None


class MarketOptionsOut(BaseModel):
    line: Line
    options: list[HitOut]
    truncated: bool


class MarketAssessmentIn(BaseModel):
    line: Line
    option_id: UUID | None = None
    feature: str | None = Field(default=None, min_length=2, max_length=120)

    @model_validator(mode="after")
    def one_feature(self) -> "MarketAssessmentIn":
        if self.feature is not None:
            self.feature = self.feature.strip()
        if (self.option_id is None) == (self.feature is None) or (self.feature is not None and len(self.feature) < 2):
            raise ValueError("Supply either an option_id or a custom feature of at least two characters.")
        return self


class MarketSignalEvidenceOut(BaseModel):
    citation: CitationOut
    stance: Literal["supports", "risk", "mixed", "unclear"]
    reason: str


class MarketSignalOut(BaseModel):
    market: Market
    direction: Literal["positive", "negative", "mixed", "insufficient"]
    explanation: str
    total_feedback: int
    matched_total: int
    counts: dict[str, int]
    reviewed: int
    evidence: list[MarketSignalEvidenceOut]


class MarketAssessmentOut(BaseModel):
    line: Line
    feature: str
    catalog_citation: CitationOut | None
    basis: str
    query_terms: list[str]
    markets: list[MarketSignalOut]


class MarketWebEvidenceOut(BaseModel):
    market: Market | None
    stance: Literal["supports", "risk", "context"]
    url: str
    title: str
    summary: str
    retrieved_at: str
    source_type: str
    scope: str
    reason: str


class MarketWebSignalOut(BaseModel):
    market: Market
    direction: Literal["positive", "negative", "mixed", "insufficient"]
    evidence: list[MarketWebEvidenceOut]


class MarketWebOut(BaseModel):
    public_query: str | None
    context: list[MarketWebEvidenceOut] = Field(default_factory=list)
    markets: list[MarketWebSignalOut]


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


# ---------------------------------------------------------------- chat

from datetime import datetime  # noqa: E402

MessageRole = Literal["pm", "orchestrator", "agent", "system"]
MessageKind = Literal["request", "plan", "plan_change", "step_card", "pushback", "final_result", "system_note"]
StepStatusLit = Literal["planned", "running", "awaiting_review", "accepted", "rejected"]


class AgentOut(BaseModel):
    name: str
    stage: int
    description: str
    available: bool


class ConversationOut(BaseModel):
    id: UUID
    title: str
    vehicle_line: str | None
    market_code: str | None
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime
    comparison_model_id: UUID | None = None
    comparison_variant: str | None = None
    comparison_market: str | None = None


class MessageOut(BaseModel):
    id: UUID
    seq: int
    conversation_id: UUID
    role: MessageRole
    kind: MessageKind
    run_id: UUID | None
    step_id: UUID | None
    content: str
    payload: dict[str, Any]
    created_at: datetime


class StepOut(BaseModel):
    id: UUID
    position: int
    agent_name: str
    stage: int
    status: StepStatusLit
    plan_reason: str | None
    planned_by: Literal["orchestrator", "pm"]
    attempt: int
    available: bool
    human_readable_summary: str | None = None
    pm_note: str | None = None


class RunOut(BaseModel):
    id: UUID
    conversation_id: UUID | None
    vehicle_line: str
    market: str
    query_text: str | None
    status: Literal["in_progress", "completed", "aborted"]
    created_at: datetime
    steps: list[StepOut]


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    runs: list[RunOut]


class PostResult(BaseModel):
    messages: list[MessageOut]
    run: RunOut | None


class CreateConversation(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    request: str | None = Field(default=None, min_length=3, max_length=4000)
    comparison_model_id: UUID | None = None
    comparison_variant: str = Field(default='', max_length=120)
    comparison_market: Market = 'EU'


class PostMessage(BaseModel):
    content: str = Field(min_length=3, max_length=4000)


class UpdateConversation(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["active", "archived"] | None = None


# ---------------------------------------------------------------- evidence library

class SourceCounts(BaseModel):
    feedback: int
    pdf_chunks: int
    options: int
    study_cells: int
    sales_rows: int


class SourceOut(BaseModel):
    id: UUID
    file: str
    type: str
    family: str
    vehicle_line: str | None
    market: str | None
    title: str | None
    retrieved_at: datetime
    trust_tier: str | None = None
    counts: SourceCounts


class UploadOut(BaseModel):
    file: str
    kind: Literal["pdf", "feedback", "sales", "studies", "web"]
    replaced: bool
    counts: SourceCounts
    notes: list[str]


class WebSourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    line: Line | None = None
    market: Market | None = None
    trust_tier: Literal["oem", "trade_press", "forum_social"] | None = None
    replace: bool = False


class SourceLink(BaseModel):
    source_id: str
    line: str | None
    market: str | None
    rows: int


class SourceGraphOut(BaseModel):
    links: list[SourceLink]


class WebFindOut(BaseModel):
    url: str
    domain: str
    title: str | None
    trust_tier: str | None
    findings: int
    skipped_reason: str | None
    agent: str
    retrieved_at: datetime | None
    vehicle_line: str | None
    market: str | None
    request: str | None
    conversation_id: str | None
    conversation: str | None
    source_id: str | None


class CoverageCell(BaseModel):
    line: str
    market: str
    feedback: int
    study_cells: int
    sales_2025: int | None


class CoverageOut(BaseModel):
    cells: list[CoverageCell]
    options_by_line: dict[str, int]
    total_feedback: int

# ---------------------------------------------------------------- authentication

class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: Literal["pm", "admin"]


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut
