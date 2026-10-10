"""Orchestration loop tests against the real database, rolled back after every test (see conftest.db).
The orchestrator and the agents are fakes: no model, web or knowledge-layer call is made."""
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.deps import get_checkpointer, get_conn, get_connect, get_orchestrator, get_runners
from app.main import app
from app.orchestration import loop, service
from app.orchestration.agents import RUNNERS, StepContext
from app.orchestration.orchestrator import OrchestratorError
from orch_fakes import CLUSTERING, FEEDBACK, FINISH, LOCATOR, TREND, FakeAgent, ScriptedOrchestrator, call, cited, finding


@pytest.fixture
def client(db):
    runners = {name: FakeAgent(name) for name in RUNNERS}
    holder = {"orchestrator": ScriptedOrchestrator(call(FEEDBACK), call(TREND), FINISH)}
    app.dependency_overrides[get_conn] = lambda: db
    app.dependency_overrides[get_connect] = lambda: (lambda: nullcontext(db))
    app.dependency_overrides[get_orchestrator] = lambda: holder["orchestrator"]
    app.dependency_overrides[get_runners] = lambda: runners
    app.dependency_overrides[get_checkpointer] = lambda: (lambda: nullcontext(InMemorySaver()))
    c = TestClient(app)          # background tasks run before the response returns, so the loop has ended
    c.holder, c.db, c.runners = holder, db, runners
    yield c
    app.dependency_overrides.clear()


def new_run(client, request="What do US customers say about seat comfort?"):
    body = client.post("/api/conversations", json={"request": request}).json()
    return client.get(f"/api/conversations/{body['conversation']['id']}").json()


def steps(thread):
    return [(s["agent_name"], s["status"]) for s in thread["runs"][0]["steps"]]


def audit(client, entity_id):
    return [r["action"] for r in client.db.execute(
        "select action from public.audit_event where entity_id = %s order by timestamp, id", (entity_id,)).fetchall()]


def test_the_orchestrator_calls_agents_one_after_another_without_anyone_approving(client):
    thread = new_run(client)
    run = thread["runs"][0]
    assert run["status"] == "completed" and steps(thread) == [(FEEDBACK, "accepted"), (TREND, "accepted")]
    assert [m["kind"] for m in thread["messages"]] == \
        ["request", "system_note", "step_card", "system_note", "step_card", "final_result"]
    decision = thread["messages"][1]
    assert decision["content"] == f"Calling {FEEDBACK}: because {FEEDBACK}"
    assert decision["payload"]["decision"]["agent"] == FEEDBACK and decision["step_id"] == run["steps"][0]["id"]
    card = thread["messages"][2]
    assert (card["role"], card["step_id"], card["payload"]["failed"]) == ("agent", run["steps"][0]["id"], False)
    assert LOCATOR in card["content"] and card["payload"]["output"]["findings"][0]["id"]   # ids let later agents cite
    final = thread["messages"][-1]
    assert FEEDBACK in final["content"] and TREND in final["content"] and LOCATOR in final["content"]
    assert [s["plan_reason"] for s in run["steps"]] == [f"because {FEEDBACK}", f"because {TREND}"]


def test_the_orchestrator_reads_each_result_before_choosing_the_next_agent(client):
    new_run(client)
    first, second, third = client.holder["orchestrator"].calls
    assert first["history"] == [] and first["calls_left"] == loop.MAX_AGENT_CALLS
    assert [(o.agent, o.accepted, o.findings) for o in second["history"]] == [(FEEDBACK, True, 1)]
    assert LOCATOR in second["history"][0].summary                       # it sees the cited answer, not just a status
    assert [o.agent for o in third["history"]] == [FEEDBACK, TREND] and third["calls_left"] == loop.MAX_AGENT_CALLS - 2


def test_a_later_agent_gets_the_findings_of_the_earlier_one_and_nothing_else(client):
    new_run(client)
    ctx = client.runners[TREND].seen[0]
    assert (ctx.vehicle_line, ctx.market, ctx.query) == ("G60", "US", "What do US customers say about seat comfort?")
    assert [f["text"] for f in ctx.accepted("findings")] == ["Seat ventilation is too weak."]
    assert client.runners[FEEDBACK].seen[0].accepted("findings") == []


def test_it_can_stop_after_one_agent_when_that_answers_the_request(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), FINISH)
    thread = new_run(client)
    assert steps(thread) == [(FEEDBACK, "accepted")] and thread["runs"][0]["status"] == "completed"
    assert client.runners[TREND].seen == []


def test_a_call_the_rules_refuse_is_sent_back_and_the_step_is_never_created(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(CLUSTERING), call("Oracle Agent"), call(FEEDBACK), FINISH)
    thread = new_run(client)
    assert steps(thread) == [(FEEDBACK, "accepted")]
    notes = [c["notes"] for c in client.holder["orchestrator"].calls]
    assert notes[0] == [] and len(notes[1]) == 1 and "stage 1" in notes[1][0]
    assert len(notes[2]) == 2 and "unknown agent" in notes[2][1]
    assert client.runners[CLUSTERING].seen == []


def test_the_loop_stops_when_the_orchestrator_keeps_asking_for_refused_calls(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), call(FEEDBACK), call(FEEDBACK), call(FEEDBACK), call(TREND))
    thread = new_run(client)
    assert thread["runs"][0]["status"] == "completed" and steps(thread) == [(FEEDBACK, "accepted")]
    notes = [m["content"] for m in thread["messages"] if m["kind"] == "system_note" and m["step_id"] is None]
    assert any("kept choosing agents that cannot run" in n for n in notes)
    assert client.runners[TREND].seen == []


def test_the_call_budget_ends_the_run_with_what_it_has(client, db):
    orchestrator = ScriptedOrchestrator(call(FEEDBACK), call(TREND), call("Competitor Agent"))
    body = service.post_request(db, service.create_conversation(db)["id"], "competitive trends", orchestrator)
    loop.orchestrate(lambda: nullcontext(db), body["run"]["id"], orchestrator, client.runners, max_calls=2,
                     checkpointer=lambda: nullcontext(InMemorySaver()))
    thread = service.list_runs(db, body["run"]["conversation_id"])[0]
    assert thread["status"] == "completed" and [s["agent_name"] for s in thread["steps"]] == [FEEDBACK, TREND]
    messages = service.list_messages(db, body["run"]["conversation_id"])
    assert "stopped after 2 agent calls" in [m for m in messages if m["kind"] == "system_note" and not m["step_id"]][0]["content"]
    assert messages[-1]["kind"] == "final_result"


def test_a_failing_agent_is_reported_to_the_orchestrator_which_goes_on_without_it(client):
    client.runners[FEEDBACK] = FakeAgent(FEEDBACK, RuntimeError("model unavailable"))
    thread = new_run(client)
    assert steps(thread) == [(FEEDBACK, "rejected"), (TREND, "accepted")]
    step = thread["runs"][0]["steps"][0]
    assert "could not finish: RuntimeError: model unavailable" in step["human_readable_summary"]
    card = thread["messages"][2]
    assert card["payload"]["failed"] is True and card["payload"]["output"] is None
    seen = client.holder["orchestrator"].calls[1]["history"]
    assert [(o.agent, o.accepted) for o in seen] == [(FEEDBACK, False)]
    assert client.runners[TREND].seen[0].accepted("findings") == []        # nothing a failed step produced is passed on
    final = thread["messages"][-1]
    assert "Coverage gaps" in final["content"] and final["payload"]["coverage_gaps"] == [FEEDBACK]
    assert audit(client, step["id"]) == ["step_started", "step_failed"]


def test_a_run_where_every_agent_failed_still_ends_with_a_clear_result(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), FINISH)
    client.runners[FEEDBACK] = FakeAgent(FEEDBACK, RuntimeError("down"))
    thread = new_run(client)
    assert thread["runs"][0]["status"] == "completed"
    assert "No agent produced a usable result" in thread["messages"][-1]["content"]


def test_a_request_that_needs_no_agent_gets_a_note_and_an_aborted_run(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(FINISH)
    thread = new_run(client, "hello there")
    assert thread["runs"][0]["status"] == "aborted" and thread["runs"][0]["steps"] == []
    assert [m["kind"] for m in thread["messages"]] == ["request", "system_note"]
    assert "could not tell which agents are needed" in thread["messages"][1]["content"]


def test_an_orchestrator_failure_keeps_what_the_agents_found(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), OrchestratorError("model call failed"))
    thread = new_run(client)
    assert thread["runs"][0]["status"] == "completed" and thread["messages"][-1]["kind"] == "final_result"
    assert any("could not decide the next step" in m["content"] for m in thread["messages"])


def test_an_orchestrator_failure_before_any_agent_aborts_the_run(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(OrchestratorError("OPENAI_API_KEY is not set"))
    thread = new_run(client)
    assert thread["runs"][0]["status"] == "aborted" and thread["messages"][-1]["kind"] == "system_note"
    assert "OPENAI_API_KEY" in thread["messages"][-1]["content"]


def test_an_unexpected_crash_never_leaves_the_run_in_progress(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), ZeroDivisionError("boom"))
    thread = new_run(client)
    assert thread["runs"][0]["status"] == "aborted"
    assert "internal error (ZeroDivisionError)" in thread["messages"][-1]["content"] and "boom" not in thread["messages"][-1]["content"]


def test_the_critic_sends_an_uncited_claim_back_before_the_orchestrator_sees_it(client):
    uncited = cited(FEEDBACK, {**finding("Customers love the seats."), "locator": "", "source_file": ""})
    agent = client.runners[FEEDBACK] = FakeAgent(FEEDBACK, uncited, cited(FEEDBACK, finding()))
    thread = new_run(client)
    assert [c.instruction is None for c in agent.seen] == [True, False]
    assert "find a citation or drop the claim" in agent.seen[1].instruction.lower()
    card = thread["messages"][2]
    assert card["payload"]["critic"]["attempts"] == 2 and "love the seats" not in card["content"]
    assert "love the seats" not in client.holder["orchestrator"].calls[1]["history"][0].summary


def test_a_claim_that_stays_uncited_is_dropped_and_reported(client):
    uncited = {**finding("Customers love the seats."), "locator": "", "source_file": ""}
    answer = cited(FEEDBACK, finding())
    answer["findings"].append(uncited)
    client.runners[FEEDBACK] = FakeAgent(FEEDBACK, answer)
    thread = new_run(client)
    card = thread["messages"][2]
    assert [f["text"] for f in card["payload"]["output"]["findings"]] == ["Seat ventilation is too weak."]
    assert card["payload"]["critic"]["retries_exhausted"] is True
    assert [d["text"] for d in card["payload"]["critic"]["dropped"]] == ["Customers love the seats."]
    assert "claim_dropped" in audit(client, thread["runs"][0]["steps"][0]["id"])


def test_synthesis_steps_are_checked_against_the_accepted_findings(client):
    """A cluster may only rest on findings an earlier, successful step produced."""
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), call(CLUSTERING), FINISH)

    def clustering(ctx):
        ids = [f["id"] for f in ctx.accepted("findings")]
        return {"agent_name": CLUSTERING, "summary": "Clustering Agent looked at the accepted findings.",
                "clusters": [{"id": "c1", "label": "Seat comfort", "member_finding_ids": ids},
                             {"id": "c2", "label": "Invented", "member_finding_ids": ["not-a-finding"]}]}

    client.runners[CLUSTERING] = clustering
    thread = new_run(client)
    card = [m for m in thread["messages"] if m["kind"] == "step_card"][-1]
    assert [c["label"] for c in card["payload"]["output"]["clusters"]] == ["Seat comfort"]
    assert [d["item"] for d in card["payload"]["critic"]["dropped"]]


def test_the_audit_trail_names_the_orchestrator_for_decisions_and_the_user_for_the_request(client):
    thread = new_run(client)
    run, first = thread["runs"][0], thread["runs"][0]["steps"][0]
    assert audit(client, run["id"]) == ["run_started", "run_completed"]
    started = client.db.execute("select actor, after from public.audit_event where entity_id = %s and action = 'run_started'",
                                (run["id"],)).fetchone()
    assert started["actor"] == "orchestrator" and started["after"]["requested_by"] == "tester@example.com"
    assert audit(client, first["id"]) == ["step_started", "step_finished"]
    row = client.db.execute("select launched_by, resolved_by, pm_note from public.step where id = %s", (first["id"],)).fetchone()
    assert (row["launched_by"], row["resolved_by"], row["pm_note"]) == ("orchestrator", "orchestrator", None)


def test_one_request_at_a_time_per_conversation(client, db):
    cid = service.create_conversation(db)["id"]
    service.post_request(db, cid, "first question", ScriptedOrchestrator())      # opened but its loop never ran
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "a second question"})
    assert r.status_code == 409 and "still being worked on" in r.json()["detail"]


def test_a_follow_up_is_a_new_run_once_the_first_has_ended(client):
    thread = new_run(client)
    cid = thread["conversation"]["id"]
    client.holder["orchestrator"] = ScriptedOrchestrator(call(TREND), FINISH)
    assert client.post(f"/api/conversations/{cid}/messages", json={"content": "And the trends?"}).status_code == 201
    runs = client.get(f"/api/conversations/{cid}").json()["runs"]
    # both runs share one test transaction, so their created_at ties and their order is not meaningful here
    assert [r["status"] for r in runs] == ["completed", "completed"]
    assert sorted(s["agent_name"] for r in runs for s in r["steps"]) == sorted([FEEDBACK, TREND, TREND])


def test_context_task_carries_steering_and_the_weight_pattern_reads_a_nudge():
    from app.orchestration.agents import WEIGHT_RE

    ctx = StepContext(query="q", vehicle_line="G60", market="US", run_id="r", note="drop paywalled sources",
                      instruction="find a citation or drop the claim: x")
    assert ctx.task == "q\nPM steering: drop paywalled sources\nfind a citation or drop the claim: x"
    assert StepContext(query="q", vehicle_line="G60", market="US", run_id="r").task == "q"
    assert WEIGHT_RE.findall("please use business_signal=0.35 and effort_proxy = .1") == \
        [("business_signal", "0.35"), ("effort_proxy", ".1")]
