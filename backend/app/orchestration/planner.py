"""Turn a PM's research request into a plan: which agents, in which order, and why.

The model proposes; code decides. Whatever the planner returns is validated against the catalog,
deduplicated, ordered by pipeline stage, and completed with the prerequisites a later stage needs.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings, load_env

from .catalog import BY_NAME, CATALOG, ORDER, _DEFAULT_FOR_STAGE, get

LINES = ("F70", "G60", "G68", "G70")
MARKETS = ("EU", "CN", "US", "RoW")


class PlannerError(RuntimeError):
    """The planner could not produce a usable plan (model unavailable or unusable output)."""


class PlanError(ValueError):
    """A plan that violates the pipeline rules; the message says what to change."""


@dataclass
class PlannedAgent:
    agent: str
    reason: str
    added_as_prerequisite: bool = False


@dataclass
class PlanProposal:
    title: str
    vehicle_line: str | None        # None = all lines
    market: str | None              # None = all markets
    steps: list[PlannedAgent] = field(default_factory=list)

    @property
    def unavailable(self) -> list[str]:
        return [s.agent for s in self.steps if not get(s.agent).available]


class Planner(Protocol):
    def plan(self, request: str) -> PlanProposal: ...


# ---------------------------------------------------------------- deterministic rules

def normalize_plan(selection: list[PlannedAgent]) -> list[PlannedAgent]:
    """Dedupe, order by catalog order, and add prerequisites: an agent at stage s needs one agent at each
    earlier stage (a research agent, Clustering, Drafting, ...), because later stages work on their output."""
    seen: dict[str, PlannedAgent] = {}
    for s in selection:
        get(s.agent)  # raises on an unknown name
        seen.setdefault(s.agent, s)
    plan = list(seen.values())
    top = max((get(s.agent).stage for s in plan), default=0)
    for stage in range(1, top):
        if not any(get(s.agent).stage == stage for s in plan):
            name = _DEFAULT_FOR_STAGE[stage]
            plan.append(PlannedAgent(name, f"Needed as input for {_next_stage_names(plan, stage)}.",
                                     added_as_prerequisite=True))
    return sorted(plan, key=lambda s: ORDER[s.agent])


def _next_stage_names(plan: list[PlannedAgent], stage: int) -> str:
    later = sorted({s.agent for s in plan if get(s.agent).stage > stage}, key=lambda n: ORDER[n])
    return ", ".join(later[:2]) or "the later steps"


def check_edited_plan(names: list[str]) -> list[PlannedAgent]:
    """Validate a plan the PM edited. Unlike the planner, never adds agents silently: it says what is missing."""
    if not names:
        raise PlanError("a plan needs at least one agent")
    if len(set(names)) != len(names):
        raise PlanError("an agent can appear only once in a plan")
    for n in names:
        if n not in BY_NAME:
            raise PlanError(f"unknown agent: {n}")
    ordered = sorted(names, key=lambda n: ORDER[n])
    top = max(get(n).stage for n in ordered)
    for stage in range(1, top):
        if not any(get(n).stage == stage for n in ordered):
            raise PlanError(f"{_DEFAULT_FOR_STAGE[stage]} (or another stage {stage} agent) is needed before "
                            f"{', '.join(n for n in ordered if get(n).stage > stage)}")
    return [PlannedAgent(n, "") for n in ordered]


# ---------------------------------------------------------------- rule-based planner (tests, no API key)

class RulePlanner:
    """Keyword planner. Used in tests and for local work without an OpenAI key; it is deliberately simple."""

    RULES = (
        ("Competitor Agent", ("competitor", "competitive", "rival", "benchmark", "versus", " vs ")),
        ("Market & Trend Agent", ("trend", "future", "2030", "outlook", "emerging")),
        ("Customer Feedback Agent", ("customer", "feedback", "complain", "complaint", "dislike", "owner", "say about")),
        ("Sales & Portfolio Agent", ("sales", "volume", "option", "standard", "equipment", "uptake", "variant")),
        ("Baseline Agent", ("previous generation", "predecessor", "carry over", "baseline")),
    )
    CHAIN = ("requirement", "derive", "prioriti", "roadmap")

    def plan(self, request: str) -> PlanProposal:
        text = f" {request.lower()} "
        picked = [PlannedAgent(a, "Matches the request wording.") for a, kws in self.RULES if any(k in text for k in kws)]
        if any(k in text for k in self.CHAIN):
            picked += [PlannedAgent("Clustering Agent", "Groups the findings into themes."),
                       PlannedAgent("Requirements Drafting Agent", "The request asks for requirements.")]
            if "prioriti" in text:
                picked.append(PlannedAgent("Prioritization Agent", "The request asks for a priority order."))
        line = next((l for l in LINES if l.lower() in text), None)
        market = next((m for m, kws in (("EU", ("europe", " eu ")), ("US", (" us ", "usa", "united states", "america")),
                                        ("CN", ("china", "chinese")), ("RoW", ("rest of world",))) if any(k in text for k in kws)), None)
        return PlanProposal(title=request.strip()[:60], vehicle_line=line, market=market,
                            steps=normalize_plan(picked) if picked else [])


# ---------------------------------------------------------------- LLM planner

SYSTEM = (
    "You are the orchestrator of a product-requirements research system for BMW product managers. "
    "Given a request, choose which agents are needed to answer it, using only the agent names provided. "
    "Choose the fewest agents that answer the question: a question about what customers say needs only research "
    "agents; add Clustering, Requirements Drafting, Prioritization or Documentation only when the request asks for "
    "requirements, a ranking or a dossier. Give each agent a one-sentence reason specific to the request. "
    "Also extract the scope if the request states it: vehicle_line one of F70, G60, G68, G70 (F70 is the 1 Series, "
    "G60 and G68 the 5 Series, G70 the 7 Series) and market one of EU, CN, US, RoW; use null when not stated. "
    "Topic to agent: equipment, options, packages, what is standard or optional on a variant, prices, option uptake or "
    "sales volumes -> Sales & Portfolio Agent; what customers say, complain about or want -> Customer Feedback Agent; "
    "rival vehicles or what competitors offer -> Competitor Agent; where the market is heading, future expectations "
    "-> Market & Trend Agent; what must carry over from the previous generation -> Baseline Agent. "
    "Any question about BMW vehicles, their equipment, customers, sales, competitors or the market needs at least one "
    "agent. Return an empty agents list only when the request is clearly not about vehicles or the automotive market. "
    'Reply with JSON only: {"title": "<max 60 chars>", "vehicle_line": null, "market": null, '
    '"agents": [{"name": "...", "reason": "..."}]}'
)


class LLMPlanner:
    def __init__(self, client=None, model: str | None = None):
        self._client = client
        self.model = model or get_settings().openai_chat_model

    def _openai(self):
        if self._client is None:
            load_env()
            if not os.environ.get("OPENAI_API_KEY"):
                raise PlannerError("OPENAI_API_KEY is not set")
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def plan(self, request: str) -> PlanProposal:
        catalog = "\n".join(f"- {a.name}: {a.description}" for a in CATALOG)
        try:
            resp = self._openai().chat.completions.create(
                model=self.model, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": f"Agents:\n{catalog}\n\nRequest: {request}"}])
            data = json.loads(resp.choices[0].message.content)
        except PlannerError:
            raise
        except Exception as e:
            raise PlannerError(f"planner model call failed ({type(e).__name__})") from e
        return parse_proposal(data, request)


def parse_proposal(data: dict, request: str) -> PlanProposal:
    """Validate model output. Unknown agent names are dropped; unknown scope values become None."""
    if not isinstance(data, dict):
        raise PlannerError("planner returned something other than an object")
    picked = []
    for item in data.get("agents") or []:
        if isinstance(item, dict) and item.get("name") in BY_NAME:
            picked.append(PlannedAgent(item["name"], str(item.get("reason") or "").strip()[:300]))
    line = data.get("vehicle_line") if data.get("vehicle_line") in LINES else None
    market = data.get("market") if data.get("market") in MARKETS else None
    title = str(data.get("title") or request).strip()[:60] or "Research request"
    return PlanProposal(title=title, vehicle_line=line, market=market, steps=normalize_plan(picked) if picked else [])
