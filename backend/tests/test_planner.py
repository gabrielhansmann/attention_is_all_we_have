import pytest

from app.orchestration.catalog import CATALOG, get
from app.orchestration.planner import (LLMPlanner, PlanError, PlannedAgent, PlannerError, RulePlanner,
                                       check_edited_plan, normalize_plan, parse_proposal)


def names(plan):
    return [s.agent for s in plan]


def test_catalog_is_in_pipeline_order_and_every_agent_is_built():
    assert [a.stage for a in CATALOG] == sorted(a.stage for a in CATALOG)
    assert all(a.available for a in CATALOG)


def test_normalize_orders_dedupes_and_keeps_research_only_plans_small():
    plan = normalize_plan([PlannedAgent("Market & Trend Agent", "a"), PlannedAgent("Competitor Agent", "b"),
                           PlannedAgent("Competitor Agent", "dup")])
    assert names(plan) == ["Competitor Agent", "Market & Trend Agent"]
    assert not any(s.added_as_prerequisite for s in plan)


def test_a_later_stage_pulls_in_the_stages_before_it():
    plan = normalize_plan([PlannedAgent("Prioritization Agent", "rank")])
    assert names(plan) == ["Customer Feedback Agent", "Clustering Agent", "Requirements Drafting Agent",
                           "Prioritization Agent"]
    assert [s.added_as_prerequisite for s in plan] == [True, True, True, False]


def test_an_existing_research_agent_satisfies_stage_one():
    plan = normalize_plan([PlannedAgent("Competitor Agent", "x"), PlannedAgent("Requirements Drafting Agent", "y")])
    assert names(plan) == ["Competitor Agent", "Clustering Agent", "Requirements Drafting Agent"]


def test_unknown_agent_is_rejected():
    with pytest.raises(ValueError):
        normalize_plan([PlannedAgent("Oracle Agent", "")])


def test_pm_edits_never_add_agents_silently():
    assert names(check_edited_plan(["Market & Trend Agent", "Competitor Agent"])) == ["Competitor Agent", "Market & Trend Agent"]
    with pytest.raises(PlanError, match="needed before"):
        check_edited_plan(["Requirements Drafting Agent", "Customer Feedback Agent"])  # no Clustering
    for bad in ([], ["Competitor Agent", "Competitor Agent"], ["Nope Agent"]):
        with pytest.raises(PlanError):
            check_edited_plan(bad)


def test_rule_planner_reads_scope_and_picks_agents():
    p = RulePlanner().plan("What do G60 customers in the US complain about?")
    assert p.vehicle_line == "G60" and p.market == "US"
    assert names(p.steps) == ["Customer Feedback Agent"]
    p = RulePlanner().plan("Derive requirements and prioritize them for the 7 Series G70 in China")
    assert p.vehicle_line == "G70" and p.market == "CN"
    assert names(p.steps)[-2:] == ["Requirements Drafting Agent", "Prioritization Agent"]
    assert RulePlanner().plan("hello there").steps == []


def test_parse_proposal_drops_unknown_agents_and_bad_scope():
    p = parse_proposal({"title": "T", "vehicle_line": "Z9", "market": "US", "agents": [
        {"name": "Competitor Agent", "reason": "r"}, {"name": "Made Up Agent", "reason": "x"}, "junk"]}, "req")
    assert p.vehicle_line is None and p.market == "US"
    assert names(p.steps) == ["Competitor Agent"]
    assert parse_proposal({"agents": []}, "req").steps == []
    with pytest.raises(PlannerError):
        parse_proposal(["not", "an", "object"], "req")


class FakeClient:
    """Stands in for the OpenAI client: records the call and returns canned JSON."""
    def __init__(self, content):
        self.content, self.calls = content, []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        msg = type("M", (), {"content": self.content})
        return type("R", (), {"choices": [type("C", (), {"message": msg})]})


def test_llm_planner_sends_the_catalog_and_validates_the_answer():
    client = FakeClient('{"title":"Trends","vehicle_line":"G60","market":null,"agents":[{"name":"Market & Trend Agent","reason":"asks about trends"}]}')
    p = LLMPlanner(client=client, model="m").plan("Which trends matter for the G60?")
    assert names(p.steps) == ["Market & Trend Agent"] and p.vehicle_line == "G60"
    sent = client.calls[0]
    assert sent["temperature"] == 0 and sent["response_format"] == {"type": "json_object"}
    assert all(a.name in sent["messages"][1]["content"] for a in CATALOG)


def test_llm_planner_failures_are_planner_errors_not_silent_fallbacks():
    with pytest.raises(PlannerError):
        LLMPlanner(client=FakeClient("not json"), model="m").plan("x")

    class Boom(FakeClient):
        def create(self, **kw):
            raise RuntimeError("secret-key-in-message")
    with pytest.raises(PlannerError) as e:
        LLMPlanner(client=Boom(""), model="m").plan("x")
    assert "secret-key" not in str(e.value)
    assert get("Competitor Agent").stage == 1
