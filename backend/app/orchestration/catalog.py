"""The agents the orchestrator can plan, in pipeline order (docs/architecture/01-agents.md).

`available` says whether the agent is implemented. A plan may name an agent that is not built yet so the
PM sees what the question really needs; such a step cannot run until the agent exists. The Critic is not
a step: it sits inside every step between the agent and the PM.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    stage: int            # 1 situation analysis, 2 structure, 3 requirements, 4 prioritization, 5 documentation
    description: str      # shown to the planner model and to the PM
    available: bool


CATALOG: tuple[AgentSpec, ...] = (
    AgentSpec("Baseline Agent", 1, "Previous-generation feedback, portfolio documents and sales trend: what must carry over.", False),
    AgentSpec("Customer Feedback Agent", 1, "What customers say: complaints, unmet needs and praise from the feedback and customer studies, with counts and sample sizes.", False),
    AgentSpec("Sales & Portfolio Agent", 1, "Revealed preference: which options are standard or optional per variant, option uptake and sales volumes by market.", False),
    AgentSpec("Competitor Agent", 1, "Rival vehicles: specs, reviews and teardown data from the web, to find competitor advantages.", False),
    AgentSpec("Market & Trend Agent", 1, "Where the market is heading: cited web trend research. Findings are assumptions, not facts.", True),
    AgentSpec("Clustering Agent", 2, "Groups findings into themes and maps them onto the domain taxonomy, removing duplicates.", False),
    AgentSpec("Requirements Drafting Agent", 3, "Turns clusters into draft requirements with a metric and acceptance criteria.", False),
    AgentSpec("Prioritization Agent", 4, "Scores each draft requirement with an explainable breakdown.", False),
    AgentSpec("Documentation Agent", 5, "Compiles the accepted steps into a dossier with the audit trail.", False),
)
BY_NAME = {a.name: a for a in CATALOG}
ORDER = {a.name: i for i, a in enumerate(CATALOG)}

# Default agent to add when a later stage needs an earlier one that the plan lacks.
_DEFAULT_FOR_STAGE = {1: "Customer Feedback Agent", 2: "Clustering Agent", 3: "Requirements Drafting Agent",
                      4: "Prioritization Agent"}


def get(name: str) -> AgentSpec:
    try:
        return BY_NAME[name]
    except KeyError:
        raise ValueError(f"unknown agent: {name}") from None
