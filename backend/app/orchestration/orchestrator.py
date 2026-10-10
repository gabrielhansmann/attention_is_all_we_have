"""The orchestrator: reads a request, then decides in a loop which agent to call next (decision 0018).

After every agent result it is asked again: call another agent, or finish. The model proposes; code decides.
`check_call` is the rule set an agent call must pass (known, built, not run before, earlier stages done), and the
loop in `loop.py` refuses anything that fails it, so a bad model answer costs a retry, never a wrong step.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.config import get_settings, load_env

from .catalog import BY_NAME, CATALOG, ORDER, _DEFAULT_FOR_STAGE, get

LINES = ("F70", "G60", "G68", "G70")
MARKETS = ("EU", "CN", "US", "RoW")
SUMMARY_CHARS = 1500          # how much of an agent's answer the orchestrator model reads per step


class OrchestratorError(RuntimeError):
    """The orchestrator could not decide (model unavailable or unusable output)."""


@dataclass(frozen=True)
class Scope:
    title: str
    vehicle_line: str | None      # None = all lines
    market: str | None            # None = all markets


@dataclass(frozen=True)
class Decision:
    action: Literal["call", "finish"]
    agent: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class Outcome:
    """What an earlier call in this run produced, as the orchestrator sees it."""
    agent: str
    stage: int
    accepted: bool                # False: the agent failed or the Critic left nothing usable
    summary: str
    findings: int = 0
    evidence: tuple[tuple[str, str], ...] = ()     # (finding id, finding text) the answer may cite


class Orchestrator(Protocol):
    def scope(self, request: str) -> Scope: ...
    def decide(self, request: str, scope: Scope, history: list[Outcome], notes: list[str],
               calls_left: int) -> Decision: ...
    def answer(self, request: str, scope: Scope, history: list[Outcome], notes: list[str]) -> str | None: ...


# ---------------------------------------------------------------- rules every call must pass

def check_call(agent: str | None, history: list[Outcome]) -> str | None:
    """None if the call is allowed, otherwise the reason it is not (shown to the model so it can correct itself)."""
    if not agent or agent not in BY_NAME:
        return f"unknown agent: {agent}"
    spec = get(agent)
    if not spec.available:
        return f"{agent} is not built yet"
    if any(o.agent == agent for o in history):
        return f"{agent} already ran in this request"
    for stage in range(1, spec.stage):
        if not any(o.stage == stage and o.accepted for o in history):
            return (f"{agent} works on the output of earlier stages: it needs a successful stage {stage} agent "
                    f"first (for example {_DEFAULT_FOR_STAGE[stage]})")
    return None


# ---------------------------------------------------------------- rule-based orchestrator (tests, no API key)

class RuleOrchestrator:
    """Keyword orchestrator for tests and local work without an OpenAI key. It picks a target set from the request
    wording and calls its agents in pipeline order; unlike the model it does not react to what the agents found."""

    RULES = (
        ("Competitor Agent", ("competitor", "competitive", "rival", "benchmark", "versus", " vs ")),
        ("Market & Trend Agent", ("trend", "future", "2030", "outlook", "emerging")),
        ("Customer Feedback Agent", ("customer", "feedback", "complain", "complaint", "dislike", "owner", "say about")),
        ("Sales & Portfolio Agent", ("sales", "volume", "option", "standard", "equipment", "uptake", "variant")),
        ("Baseline Agent", ("previous generation", "predecessor", "carry over", "baseline")),
    )
    CHAIN = ("requirement", "derive", "prioriti", "roadmap")

    def scope(self, request: str) -> Scope:
        text = f" {request.lower()} "
        line = next((l for l in LINES if l.lower() in text), None)
        market = next((m for m, kws in (("EU", ("europe", " eu ")), ("US", (" us ", "usa", "united states", "america")),
                                        ("CN", ("china", "chinese")), ("RoW", ("rest of world",))) if any(k in text for k in kws)), None)
        return Scope(request.strip()[:60] or "Research request", line, market)

    def target(self, request: str) -> list[str]:
        text = f" {request.lower()} "
        picked = {a for a, kws in self.RULES if any(k in text for k in kws)}
        if any(k in text for k in self.CHAIN):
            picked |= {"Clustering Agent", "Requirements Drafting Agent"}
            if "prioriti" in text:
                picked.add("Prioritization Agent")
        if not picked:
            return []
        top = max(get(a).stage for a in picked)
        for stage in range(1, top):
            if not any(get(a).stage == stage for a in picked):
                picked.add(_DEFAULT_FOR_STAGE[stage])
        return sorted(picked, key=lambda a: ORDER[a])

    def decide(self, request, scope, history, notes, calls_left) -> Decision:
        done = {o.agent for o in history}
        for agent in self.target(request):
            if agent not in done:
                return Decision("call", agent, "Matches the request wording.")
        return Decision("finish")

    def answer(self, request, scope, history, notes) -> str | None:
        return None                     # no model: the thread falls back to the agents' own summaries


# ---------------------------------------------------------------- LLM orchestrator

SCOPE_SYSTEM = (
    "You read a product-requirements research request from a BMW product manager. Reply with JSON only: "
    '{"title": "<max 60 chars>", "vehicle_line": null, "market": null}. '
    "vehicle_line is one of F70, G60, G68, G70 (F70 is the 1 Series, G60 and G68 the 5 Series, G70 the 7 Series) "
    "and market one of EU, CN, US, RoW; use null when the request does not state it."
)

DECIDE_SYSTEM = (
    "You are the orchestrator of a product-requirements research system for BMW product managers. You answer a "
    "request by calling specialist agents one at a time. After each agent's result you are asked again: call "
    "another agent, or finish. Work like this:\n"
    "- Start with the fewest agents that can answer the request. A question about what customers say needs only a "
    "research agent. Add Clustering, Requirements Drafting, Prioritization or Documentation only when the request "
    "asks for requirements, a ranking or a dossier.\n"
    "- Read each result. Call another agent only when the results so far leave a gap the request needs filled, or when "
    "an agent failed and another can cover the same ground. Do not call agents to be thorough.\n"
    "- Never call an agent twice. Later stages need successful earlier stages (stage 2 needs a stage 1 result, and so on).\n"
    "- Finish as soon as the request is answered, or when nothing more can be learned with the agents left.\n"
    "- Topics: equipment, options, packages, what is standard or optional, prices, uptake or sales volumes -> Sales & "
    "Portfolio Agent; what customers say, complain about or want -> Customer Feedback Agent; rival vehicles -> "
    "Competitor Agent; where the market is heading -> Market & Trend Agent; what must carry over from the previous "
    "generation -> Baseline Agent. A request that is clearly not about vehicles or the automotive market needs no agent: finish.\n"
    'Reply with JSON only: {"action": "call", "agent": "<name>", "reason": "<one sentence specific to this '
    'request>"} or {"action": "finish"}.'
)

ANSWER_SYSTEM = (
    "You are the orchestrator of a BMW product-requirements research system, and you are now answering the product "
    "manager who asked. Agents have finished; their results are below. Write the answer yourself, in your own words, "
    "addressed to the PM. Do not repeat or paste the agents' summaries.\n"
    "- Open with the direct answer to the question in one or two sentences.\n"
    "- Then the three to five points that matter most, most important first, each one short, with how strongly the "
    "evidence backs it (for example how many comments) when the results say so.\n"
    "- If the question names a model or line that the results do not cover (for example it asks about the X3 but the "
    "results are for G60 and G70), say that first and what the answer is based on instead.\n"
    "- If requirement drafting or prioritization ran, name the requirements that were drafted and how they rank.\n"
    "- Say plainly what is uncertain, thin or missing. Call an agent failed only if it is marked FAILED. Do not "
    "mention agents by name unless it helps the PM.\n"
    "- Finish with complete sentences.\n"
    "- If it would help, end with one concrete next step the PM can ask for, such as deriving requirements.\n"
    "- Use only what the results say. Never invent numbers. No file names, sheet names or row numbers.\n"
    "- Cite a finding by putting its id in square brackets right after the claim, for example [abc123]. Use only ids "
    "listed in the results.\n"
    "- Plain markdown: short paragraphs and a bullet list, bold only for the key phrase of a point. Under 180 words.\n"
    'Reply with JSON only: {"answer": "<markdown>"}.'
)

ANSWER_SUMMARY_CHARS = 3000   # the answer needs more of each step than a routing decision does
EVIDENCE_PER_STEP = 12
EVIDENCE_CHARS = 400


class LLMOrchestrator:
    def __init__(self, client=None, model: str | None = None):
        self._client = client
        self.model = model or get_settings().openai_chat_model

    def _openai(self):
        if self._client is None:
            load_env()
            if not os.environ.get("OPENAI_API_KEY"):
                raise OrchestratorError("OPENAI_API_KEY is not set")
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def _ask(self, system: str, user: str) -> dict[str, Any]:
        try:
            resp = self._openai().chat.completions.create(
                model=self.model, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return json.loads(resp.choices[0].message.content)
        except OrchestratorError:
            raise
        except Exception as e:
            raise OrchestratorError(f"orchestrator model call failed ({type(e).__name__})") from e

    def scope(self, request: str) -> Scope:
        return parse_scope(self._ask(SCOPE_SYSTEM, f"Request: {request}"), request)

    def decide(self, request, scope, history, notes, calls_left) -> Decision:
        return parse_decision(self._ask(DECIDE_SYSTEM, decide_prompt(request, scope, history, notes, calls_left)))


    def answer(self, request, scope, history, notes) -> str | None:
        if not any(o.accepted for o in history):
            return None
        return parse_answer(self._ask(ANSWER_SYSTEM, answer_prompt(request, scope, history, notes)), history)


def answer_prompt(request: str, scope: Scope, history: list[Outcome], notes: list[str]) -> str:
    blocks = []
    for o in history:
        if not o.accepted:
            blocks.append(f"{o.agent}: FAILED. {o.summary.splitlines()[0] if o.summary else ''}".strip())
            continue
        lines = "\n".join(f"[{fid}] {text[:EVIDENCE_CHARS]}" for fid, text in o.evidence[:EVIDENCE_PER_STEP])
        blocks.append(f"{o.agent}: {o.findings} findings\n{o.summary[:ANSWER_SUMMARY_CHARS]}" + (f"\nFindings you may cite:\n{lines}" if lines else ""))
    extra = "".join(f"\nNote: {n}" for n in notes)
    return (f"Request: {request}\nScope: vehicle line {scope.vehicle_line or 'all'}, market {scope.market or 'all'}\n\n"
            + "\n\n".join(blocks) + extra)


def parse_answer(data: Any, history: list[Outcome]) -> str | None:
    """The model's answer, with any citation it invented removed. None if there is nothing usable."""
    text = data.get("answer") if isinstance(data, dict) else None
    if not isinstance(text, str) or len(text.strip()) < 20:
        return None
    known = {fid for o in history for fid, _ in o.evidence}
    text = re.sub(r"\s?\[([^\]\s]+)\]", lambda m: m.group(0) if m.group(1) in known else "", text.strip())
    return text[:4000]


def decide_prompt(request: str, scope: Scope, history: list[Outcome], notes: list[str], calls_left: int) -> str:
    catalog = "\n".join(f"- {a.name} (stage {a.stage}{'' if a.available else ', not built yet'}): {a.description}"
                        for a in CATALOG)
    scope_text = f"vehicle line {scope.vehicle_line or 'all'}, market {scope.market or 'all'}"
    if history:
        results = "\n\n".join(
            f"[{i}] {o.agent}: {'succeeded' if o.accepted else 'FAILED'}"
            + (f", {o.findings} findings" if o.accepted else "") + f"\n{o.summary[:SUMMARY_CHARS]}"
            for i, o in enumerate(history, 1))
    else:
        results = "(no agent has run yet)"
    extra = "".join(f"\nYour last choice was refused: {n}. Choose differently." for n in notes)
    return (f"Agents:\n{catalog}\n\nRequest: {request}\nScope: {scope_text}\n\nResults so far:\n{results}\n\n"
            f"You may make at most {calls_left} more calls.{extra}")


def parse_scope(data: Any, request: str) -> Scope:
    """Validate model output. Unknown scope values become None."""
    if not isinstance(data, dict):
        raise OrchestratorError("the orchestrator returned something other than an object")
    line = data.get("vehicle_line") if data.get("vehicle_line") in LINES else None
    market = data.get("market") if data.get("market") in MARKETS else None
    title = str(data.get("title") or request).strip()[:60] or "Research request"
    return Scope(title, line, market)


def parse_decision(data: Any) -> Decision:
    if not isinstance(data, dict) or data.get("action") not in ("call", "finish"):
        raise OrchestratorError("the orchestrator returned no usable decision")
    if data["action"] == "finish":
        return Decision("finish")
    return Decision("call", str(data.get("agent") or "").strip(), str(data.get("reason") or "").strip()[:300])
