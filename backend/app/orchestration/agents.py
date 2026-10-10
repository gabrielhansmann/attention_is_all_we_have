"""How the step runner calls each catalog agent (docs/architecture/01 and 02).

One adapter per agent: it takes a `StepContext` (the run's scope and request, steering, and the accepted output
of earlier steps) and returns the agent's result dataclass. Adapters write nothing; the runner stores the output
after the Critic has reviewed it. Agent modules are imported inside the adapters so the API starts without them.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

MAX_WEB_SOURCES = 6
WEIGHT_RE = re.compile(r"\b(customer_relevance|business_signal|strategic_fit|effort_proxy)\s*=\s*(\d*\.?\d+)")


@dataclass
class StepContext:
    query: str
    vehicle_line: str                     # "ALL" means no filter
    market: str
    run_id: str
    note: str | None = None               # the PM's steering note on a Retry
    instruction: str | None = None        # the Critic's instruction on an automatic retry
    steps: list[dict[str, Any]] = field(default_factory=list)       # earlier steps of the run, with `output`
    decisions: list[dict[str, Any]] = field(default_factory=list)   # the run's audit events so far

    @property
    def steering(self) -> str | None:
        parts = [f"PM steering: {self.note}" if self.note else "", self.instruction or ""]
        return "\n".join(p for p in parts if p) or None

    @property
    def task(self) -> str:
        """The request plus any steering, for agents whose model reads the query."""
        return f"{self.query}\n{self.steering}" if self.steering else self.query

    def accepted(self, key: str) -> list[dict[str, Any]]:
        """Items of one kind (`findings`, `clusters`, `requirements`) from the accepted steps, in plan order."""
        return [item for s in self.steps if s.get("status") == "accepted"
                for item in (s.get("output") or {}).get(key) or [] if isinstance(item, dict)]


AgentRunner = Callable[[StepContext], Any]


def _client() -> Any:
    from app.agents.market_trend_agent import require_openai
    return require_openai()()


def _market_trend(ctx: StepContext) -> Any:
    from app.agents import market_trend_agent as agent
    client = _client()
    docs = agent.collect_with_web_search(client, ctx.vehicle_line, ctx.market, ctx.task, MAX_WEB_SOURCES)
    draft = agent.extract_market_trends_with_openai(client, ctx.vehicle_line, ctx.market, ctx.task, docs) if docs else {}
    return agent.build_result(ctx.vehicle_line, ctx.market, ctx.query, docs, draft)


def _competitor(ctx: StepContext) -> Any:
    from app.agents import competitor_agent as agent
    docs, draft = agent.research_with_openai(_client(), ctx.vehicle_line, ctx.market, ctx.task, max_sources=MAX_WEB_SOURCES)
    return agent.build_result(ctx.vehicle_line, ctx.market, ctx.query, docs, draft)


def _evidence_agent(agent: Any, model: str | None = None) -> AgentRunner:
    """Customer Feedback and Baseline: retrieval uses the request alone, the draft also sees the steering."""
    def run(ctx: StepContext) -> Any:
        pack = agent.collect_evidence(agent.knowledge_tools(), ctx.query, ctx.vehicle_line, ctx.market)
        draft: dict[str, Any] = {"findings": [], "skipped": []}
        if pack.hits:
            prompt = agent.build_prompt(agent.scope_label(ctx.vehicle_line), agent.scope_label(ctx.market), ctx.task, pack)
            draft = agent.draft_with_openai(_client(), prompt, *([model] if model else []))
        return agent.build_result(ctx.vehicle_line, ctx.market, ctx.query, pack, draft)
    return run


def _customer_feedback(ctx: StepContext) -> Any:
    from app.agents import customer_feedback_agent as agent
    return _evidence_agent(agent)(ctx)


def _baseline(ctx: StepContext) -> Any:
    from app.agents import baseline_agent as agent
    return _evidence_agent(agent, agent.BASELINE_MODEL)(ctx)


def _sales_portfolio(ctx: StepContext) -> Any:
    from app.agents import sales_portfolio_agent as agent
    proposed = agent.propose_option_terms_with_openai(_client(), agent.scope_label(ctx.vehicle_line), ctx.task)
    return agent.run(ctx.vehicle_line, ctx.market, ctx.query, option_terms=agent.option_terms_from_draft(proposed))


def _clustering(ctx: StepContext) -> Any:
    from app.agents import clustering_agent as agent
    findings = ctx.accepted("findings")
    draft = (agent.propose_clusters_with_openai(_client(), ctx.vehicle_line, ctx.market, findings, note=ctx.steering)
             if findings else {})
    return agent.build_result(ctx.vehicle_line, ctx.market, findings, draft)


def _requirements_drafting(ctx: StepContext) -> Any:
    from app.agents import requirements_drafting_agent as agent
    clusters, findings = ctx.accepted("clusters"), ctx.accepted("findings")
    draft = (agent.draft_requirements_with_openai(_client(), ctx.vehicle_line, ctx.market, clusters, findings,
                                                  note=ctx.steering) if clusters else {})
    return agent.build_result(ctx.vehicle_line, ctx.market, clusters, draft, findings)


def _prioritization(ctx: StepContext) -> Any:
    """Deterministic. A steering note can re-weight: `business_signal=0.35` in the note overrides that weight."""
    from app.agents import prioritization_agent as agent
    overrides = {name: float(value) for name, value in WEIGHT_RE.findall(ctx.note or "")}
    weights = agent.ScoringWeights().with_overrides(overrides) if overrides else None
    requirements = ctx.accepted("requirements")
    markets = sorted({m for r in requirements for m in r.get("markets") or []} or
                     ({ctx.market} if ctx.market != "ALL" else set()))
    sales = agent.load_sales(ctx.vehicle_line, markets) if markets and ctx.vehicle_line != "ALL" else []
    return agent.build_result(ctx.vehicle_line, ctx.market, requirements, ctx.accepted("findings"),
                              weights=weights, sales=sales)


def _documentation(ctx: StepContext) -> Any:
    from app.agents import documentation_agent as agent
    return agent.build_result(ctx.vehicle_line, ctx.market, ctx.query, ctx.steps, ctx.decisions, run_id=ctx.run_id)


RUNNERS: dict[str, AgentRunner] = {
    "Baseline Agent": _baseline,
    "Customer Feedback Agent": _customer_feedback,
    "Sales & Portfolio Agent": _sales_portfolio,
    "Competitor Agent": _competitor,
    "Market & Trend Agent": _market_trend,
    "Clustering Agent": _clustering,
    "Requirements Drafting Agent": _requirements_drafting,
    "Prioritization Agent": _prioritization,
    "Documentation Agent": _documentation,
}
