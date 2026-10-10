"""Response models for the HTTP API. They mirror the retrieval tools' dataclasses so the frontend
always receives a citation (file, locator, verbatim quote) next to every piece of evidence."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


# ---------------------------------------------------------------- chat

from datetime import datetime  # noqa: E402
from uuid import UUID  # noqa: E402

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
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    request: str | None = Field(default=None, min_length=3, max_length=4000)


class PostMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    content: str = Field(min_length=3, max_length=4000)


class UpdateConversation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["active", "archived"] | None = None


class EditPlan(BaseModel):
    agents: list[str] = Field(min_length=1, max_length=12)


# ---------------------------------------------------------------- evidence library

class SourceCounts(BaseModel):
    feedback: int
    pdf_chunks: int
    options: int
    study_cells: int
    sales_rows: int
    findings: int


class SourceOut(BaseModel):
    id: UUID
    file: str
    type: str
    family: str
    vehicle_line: str | None
    market: str | None
    title: str | None
    retrieved_at: datetime
    counts: SourceCounts


class CoverageCell(BaseModel):
    line: str
    market: str
    feedback: int
    study_cells: int
    sales_volume: int | None


class CoverageOut(BaseModel):
    sales_year: int | None
    cells: list[CoverageCell]
    options_by_line: dict[str, int]
    total_feedback: int

class StepNote(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=2000)


class RetryStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=2000)


class RejectStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=2000)
    proceed: bool           # true: go on without this agent (coverage gap); false: abort the run


class EditStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    summary: str = Field(min_length=3, max_length=20000)
    note: str | None = Field(default=None, max_length=2000)

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


# ---------------------------------------------------------------- database workspace
class ScopeOption(BaseModel):
    key: str
    label: str


class WorkspaceConfigOut(BaseModel):
    lines: list[ScopeOption]
    markets: list[ScopeOption]


class StoredCitation(BaseModel):
    id: UUID
    file: str
    locator: str
    quote: str
    evidence_level: str


class StoredRequirement(BaseModel):
    id: UUID
    code: str | None
    title: str
    description: str
    vehicle_line: str
    markets: list[str]
    status: str
    metric: str | None
    acceptance_criteria: str | None
    evidence_level: str | None
    assumptions: list[str]
    uncertainties: list[str]
    created_at: datetime
    domain: str | None
    score: float | None
    confidence: float | None
    score_rationale: str | None
    weight_vector_version: str | None
    scored_at: datetime | None
    allowed_statuses: list[str]
    citations: list[StoredCitation]


class WorkspaceCounts(BaseModel):
    feedback: int
    study_cells: int
    catalog_options: int
    pending_steps: int


class SalesRow(BaseModel):
    id: UUID
    vehicle_line: str
    market_code: str
    year: int
    volume: int
    is_forecast: bool
    file: str
    locator: str


class CatalogRow(BaseModel):
    id: UUID
    vehicle_line: str
    code: str
    name: str
    description: str | None
    standard_variants: int
    optional_variants: int
    file: str
    locator: str


class StudyRow(BaseModel):
    id: UUID
    vehicle_line: str
    market_code: str
    model: str
    question: str
    metric: str
    answer_option: str | None
    value: float
    file: str
    locator: str


class WorkspaceRun(BaseModel):
    id: UUID
    conversation_id: UUID | None
    query_text: str | None
    vehicle_line: str
    market: str
    status: str
    created_at: datetime
    awaiting_review: int


class AcceptedResult(BaseModel):
    id: UUID
    agent_name: str
    summary: str | None
    output: dict[str, Any]
    resolved_at: datetime | None
    resolved_by: str | None
    run_id: UUID
    conversation_id: UUID | None
    run_status: str
    vehicle_line: str
    market: str


class DecisionEvent(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor: str
    rationale: str | None
    timestamp: datetime
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class WorkspaceSnapshotOut(BaseModel):
    generated_at: datetime
    counts: WorkspaceCounts
    requirements: list[StoredRequirement]
    sales: list[SalesRow]
    options: list[CatalogRow]
    studies: list[StudyRow]
    runs: list[WorkspaceRun]
    results: list[AcceptedResult]
    audits: list[DecisionEvent]


class ReviewRequirement(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    status: str = Field(min_length=1, max_length=30)
    expected_status: str = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=3, max_length=2000)
