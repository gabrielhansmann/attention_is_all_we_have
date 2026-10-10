import pytest

from app.orchestration.catalog import CATALOG, get
from app.orchestration.orchestrator import (ANSWER_SYSTEM, DECIDE_SYSTEM, Decision, LLMOrchestrator, OrchestratorError, Outcome,
                                            RuleOrchestrator, Scope, answer_prompt, check_call, decide_prompt, parse_answer, parse_decision, parse_scope)


def done(agent, accepted=True, summary="s", findings=1):
    return Outcome(agent, get(agent).stage, accepted, summary, findings)


def test_catalog_is_in_pipeline_order_and_every_agent_is_built():
    assert [a.stage for a in CATALOG] == sorted(a.stage for a in CATALOG)
    assert all(a.available for a in CATALOG)


def test_a_research_agent_can_be_called_first_and_only_once():
    assert check_call("Competitor Agent", []) is None
    assert "already ran" in check_call("Competitor Agent", [done("Competitor Agent")])
    assert "already ran" in check_call("Competitor Agent", [done("Competitor Agent", accepted=False)])   # a failed agent is not retried


def test_unknown_agents_are_refused():
    assert "unknown agent" in check_call("Oracle Agent", [])
    assert "unknown agent" in check_call(None, [])


def test_a_later_stage_needs_a_successful_agent_at_each_earlier_stage():
    assert "stage 1" in check_call("Clustering Agent", [])
    assert "stage 1" in check_call("Clustering Agent", [done("Competitor Agent", accepted=False)])   # failed does not count
    assert check_call("Clustering Agent", [done("Competitor Agent")]) is None
    assert "stage 2" in check_call("Requirements Drafting Agent", [done("Competitor Agent")])
    chain = [done("Competitor Agent"), done("Clustering Agent"), done("Requirements Drafting Agent")]
    assert check_call("Prioritization Agent", chain) is None


def test_rule_orchestrator_reads_scope():
    s = RuleOrchestrator().scope("What do G60 customers in the US complain about?")
    assert (s.vehicle_line, s.market) == ("G60", "US")
    s = RuleOrchestrator().scope("Which trends matter?")
    assert (s.vehicle_line, s.market) == (None, None)


def test_rule_orchestrator_calls_its_agents_in_order_then_finishes():
    o, request = RuleOrchestrator(), "Derive requirements and prioritize them for the G70 customers"
    scope, history, order = o.scope(request), [], []
    while (d := o.decide(request, scope, history, [], 8)).action == "call":
        assert check_call(d.agent, history) is None          # whatever it picks is allowed
        order.append(d.agent)
        history.append(done(d.agent))
    assert order == ["Customer Feedback Agent", "Clustering Agent", "Requirements Drafting Agent", "Prioritization Agent"]
    assert o.decide("hello there", Scope("", None, None), [], [], 8) == Decision("finish")


def test_parse_decision_accepts_only_call_or_finish():
    assert parse_decision({"action": "finish"}) == Decision("finish")
    assert parse_decision({"action": "call", "agent": "Competitor Agent", "reason": " r "}) == Decision("call", "Competitor Agent", "r")
    for bad in (["x"], {"action": "dance"}, {}):
        with pytest.raises(OrchestratorError):
            parse_decision(bad)


def test_parse_scope_drops_bad_values():
    s = parse_scope({"title": "T", "vehicle_line": "Z9", "market": "US"}, "req")
    assert (s.title, s.vehicle_line, s.market) == ("T", None, "US")
    with pytest.raises(OrchestratorError):
        parse_scope("nope", "req")


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


def test_the_model_sees_the_catalog_the_request_and_what_earlier_agents_found():
    scope = Scope("T", "G60", None)
    history = [done("Customer Feedback Agent", summary="Seats are too hot.", findings=3),
               done("Competitor Agent", accepted=False, summary="could not finish")]
    text = decide_prompt("Why are G60 owners unhappy?", scope, history, ["Competitor Agent already ran"], 5)
    assert all(a.name in text for a in CATALOG)
    assert "Why are G60 owners unhappy?" in text and "vehicle line G60, market all" in text
    assert "Seats are too hot." in text and "3 findings" in text and "FAILED" in text
    assert "Competitor Agent already ran" in text and "at most 5 more calls" in text
    assert "(no agent has run yet)" in decide_prompt("q", scope, [], [], 8)


def test_llm_orchestrator_asks_once_per_decision_and_validates_the_answer():
    client = FakeClient('{"action":"call","agent":"Market & Trend Agent","reason":"asks about trends"}')
    o = LLMOrchestrator(client=client, model="m")
    d = o.decide("Which trends matter?", Scope("T", None, None), [], [], 8)
    assert d == Decision("call", "Market & Trend Agent", "asks about trends")
    sent = client.calls[0]
    assert sent["temperature"] == 0 and sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][0]["content"] == DECIDE_SYSTEM
    s = LLMOrchestrator(client=FakeClient('{"title":"Trends","vehicle_line":"G60","market":null}'), model="m").scope("x")
    assert (s.title, s.vehicle_line) == ("Trends", "G60")


def test_llm_failures_are_errors_not_silent_fallbacks():
    with pytest.raises(OrchestratorError):
        LLMOrchestrator(client=FakeClient("not json"), model="m").decide("x", Scope("", None, None), [], [], 8)

    class Boom(FakeClient):
        def create(self, **kw):
            raise RuntimeError("secret-key-in-message")
    with pytest.raises(OrchestratorError) as e:
        LLMOrchestrator(client=Boom(""), model="m").scope("x")
    assert "secret-key" not in str(e.value)


def test_the_answer_is_written_by_the_model_from_findings_and_drops_invented_citations():
    history = [Outcome("Customer Feedback Agent", 1, True, "looked at 24 rows\nFindings: ...", 2,
                       (("f1", "Menus are too deep."), ("f2", "Voice assistant starts unprompted."))),
               Outcome("Competitor Agent", 1, False, "Competitor Agent could not finish: no key")]
    prompt = answer_prompt("What do owners dislike?", Scope("T", "G60", "US"), history, ["stopped early"])
    assert "[f1] Menus are too deep." in prompt and "FAILED" in prompt and "stopped early" in prompt
    reply = '{"answer": "Owners mostly dislike deep menus [f1], and the assistant misfires [zzz] [f2]."}'
    client = FakeClient(reply)
    text = LLMOrchestrator(client=client, model="m").answer("q", Scope("T", None, None), history, [])
    assert text == "Owners mostly dislike deep menus [f1], and the assistant misfires [f2]."
    assert client.calls[0]["messages"][0]["content"] == ANSWER_SYSTEM


def test_no_answer_is_written_when_no_agent_succeeded_or_the_reply_is_unusable():
    failed = [Outcome("Competitor Agent", 1, False, "failed")]
    assert LLMOrchestrator(client=FakeClient('{"answer": "x"}'), model="m").answer("q", Scope("", None, None), failed, []) is None
    ok = [Outcome("Customer Feedback Agent", 1, True, "s", 1, (("f1", "t"),))]
    assert parse_answer({"answer": "ok"}, ok) is None
    assert RuleOrchestrator().answer("q", Scope("", None, None), ok, []) is None
