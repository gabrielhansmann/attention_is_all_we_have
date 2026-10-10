"""Step runner tests against the real database, rolled back after every test (see conftest.db).
The agents are fakes: no model, web or knowledge-layer call is made."""
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conn, get_connect, get_planner, get_runners
from app.main import app
from app.orchestration.agents import RUNNERS, StepContext
from app.orchestration.planner import PlannedAgent, PlanProposal, normalize_plan

FEEDBACK, TREND, CLUSTERING = "Customer Feedback Agent", "Market & Trend Agent", "Clustering Agent"
FILE, LOCATOR = "G60_feedback_hackathon.xlsx", "sheet Feedback_Explorer, row 12"


class FakePlanner:
    def __init__(self, *agents):
        self.agents = agents

    def plan(self, request):
        return PlanProposal(title="A title", vehicle_line="G60", market="US",
                            steps=normalize_plan([PlannedAgent(a, f"because {a}") for a in self.agents]))


def finding(text="Seat ventilation is too weak.", locator=LOCATOR):
    return {"text": text, "signal_type": "complaint", "evidence_level": "Verified", "source_file": FILE,
            "locator": locator, "market": "US", "vehicle_line": "G60", "assumptions": [], "out_of_scope_reason": None}


def cited(agent, *findings):
    bullets = "\n".join(f"- {f['text']} ({FILE}, {f['locator']})" for f in findings) or "- No findings."
    return {"agent_name": agent, "vehicle_line": "G60", "market": "US", "findings": list(findings),
            "summary": f"{agent} looked at the G60 / US feedback.\n\nFindings:\n{bullets}"}


class FakeAgent:
    """Records every context it is called with and answers from a list (the last answer repeats)."""

    def __init__(self, name, *answers):
        self.name, self.answers, self.seen = name, list(answers) or [cited(name, finding())], []

    def __call__(self, ctx: StepContext):
        self.seen.append(ctx)
        answer = self.answers[min(len(self.seen), len(self.answers)) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture
def client(db):
    runners = {name: FakeAgent(name) for name in RUNNERS}
    holder = {"planner": FakePlanner(FEEDBACK, TREND)}
    app.dependency_overrides[get_conn] = lambda: db
    app.dependency_overrides[get_connect] = lambda: (lambda: nullcontext(db))
    app.dependency_overrides[get_planner] = lambda: holder["planner"]
    app.dependency_overrides[get_runners] = lambda: runners
    c = TestClient(app)
    c.holder, c.db, c.runners = holder, db, runners
    yield c
    app.dependency_overrides.clear()


def new_run(client, request="What do US customers say about seat comfort?"):
    return client.post("/api/conversations", json={"request": request}).json()


def detail(client, body):
    return client.get(f"/api/conversations/{body['conversation']['id']}").json()


def steps(client, body):
    return [(s["agent_name"], s["status"]) for s in detail(client, body)["runs"][0]["steps"]]


def step_id(client, body, position=1):
    return detail(client, body)["runs"][0]["steps"][position - 1]["id"]


def start(client, body):
    return client.post(f"/api/runs/{body['runs'][0]['id']}/start")


def audit(client, entity_id):
    return [r["action"] for r in client.db.execute(
        "select action from public.audit_event where entity_id = %s order by timestamp, id", (entity_id,)).fetchall()]


def test_start_runs_only_the_first_agent_and_puts_its_cited_answer_up_for_review(client):
    body = new_run(client)
    assert start(client, body).status_code == 200
    assert steps(client, body) == [(FEEDBACK, "awaiting_review"), (TREND, "planned")]
    assert client.runners[TREND].seen == []
    thread = detail(client, body)
    card = thread["messages"][-1]
    assert (card["kind"], card["role"], card["step_id"]) == ("step_card", "agent", step_id(client, body))
    assert LOCATOR in card["content"] and card["payload"]["failed"] is False
    assert card["payload"]["output"]["findings"][0]["id"]            # ids are assigned so later agents can cite
    assert thread["runs"][0]["steps"][0]["human_readable_summary"] == card["content"]
    assert audit(client, step_id(client, body)) == ["step_started", "step_finished"]


def test_accept_starts_the_next_agent_with_the_accepted_output_and_the_last_accept_compiles_the_result(client):
    body = new_run(client)
    start(client, body)
    assert client.post(f"/api/steps/{step_id(client, body)}/accept", json={}).status_code == 200
    assert steps(client, body) == [(FEEDBACK, "accepted"), (TREND, "awaiting_review")]
    ctx = client.runners[TREND].seen[0]
    assert (ctx.vehicle_line, ctx.market, ctx.query) == ("G60", "US", "What do US customers say about seat comfort?")
    assert [f["text"] for f in ctx.accepted("findings")] == ["Seat ventilation is too weak."]
    assert "final_result" not in [m["kind"] for m in detail(client, body)["messages"]]

    done = client.post(f"/api/steps/{step_id(client, body, 2)}/accept", json={"note": "fine"}).json()
    assert done["run"]["status"] == "completed"
    final = done["messages"][-1]
    assert final["kind"] == "final_result" and FEEDBACK in final["content"] and LOCATOR in final["content"]
    assert audit(client, body["runs"][0]["id"]) == ["plan_created", "run_completed"]


def test_an_unaccepted_step_never_reaches_the_next_agent(client):
    body = new_run(client)
    start(client, body)
    rejected = client.post(f"/api/steps/{step_id(client, body)}/reject", json={"note": "wrong market", "proceed": True})
    assert rejected.status_code == 200
    assert steps(client, body) == [(FEEDBACK, "rejected"), (TREND, "awaiting_review")]
    assert client.runners[TREND].seen[0].accepted("findings") == []
    done = client.post(f"/api/steps/{step_id(client, body, 2)}/accept", json={}).json()
    final = done["messages"][-1]
    assert "Coverage gaps" in final["content"] and "wrong market" in final["content"]
    assert final["payload"]["coverage_gaps"] == [FEEDBACK]


def test_reject_without_proceeding_aborts_the_run_and_shows_no_result(client):
    body = new_run(client)
    start(client, body)
    out = client.post(f"/api/steps/{step_id(client, body)}/reject", json={"note": "not useful", "proceed": False}).json()
    assert out["run"]["status"] == "aborted" and [m["kind"] for m in out["messages"]] == ["pushback", "system_note"]
    assert steps(client, body) == [(FEEDBACK, "rejected"), (TREND, "planned")] and client.runners[TREND].seen == []
    assert client.post(f"/api/runs/{body['runs'][0]['id']}/start").status_code == 409


def test_retry_reruns_the_same_agent_with_the_steering_note(client):
    body = new_run(client)
    start(client, body)
    sid = step_id(client, body)
    assert client.post(f"/api/steps/{sid}/retry", json={"note": ""}).status_code == 422
    out = client.post(f"/api/steps/{sid}/retry", json={"note": "only EU respondents"})
    assert out.status_code == 200 and out.json()["messages"][0]["kind"] == "pushback"
    agent = client.runners[FEEDBACK]
    assert [c.note for c in agent.seen] == [None, "only EU respondents"]
    assert "PM steering: only EU respondents" in agent.seen[1].task
    step = detail(client, body)["runs"][0]["steps"][0]
    assert (step["status"], step["attempt"], step["pm_note"]) == ("awaiting_review", 2, "only EU respondents")
    assert client.runners[TREND].seen == []
    assert audit(client, sid) == ["step_started", "step_finished", "step_retried", "step_finished"]


def test_edit_rewrites_the_summary_and_the_diff_is_audited(client):
    body = new_run(client)
    start(client, body)
    sid = step_id(client, body)
    before = detail(client, body)["runs"][0]["steps"][0]["human_readable_summary"]
    out = client.post(f"/api/steps/{sid}/edit", json={"summary": "Tightened by the PM.", "note": "merged two points"})
    assert out.status_code == 200
    step = out.json()["run"]["steps"][0]
    assert (step["status"], step["human_readable_summary"]) == ("awaiting_review", "Tightened by the PM.")
    event = client.db.execute("select before, after, rationale from public.audit_event where entity_id = %s "
                              "and action = 'step_edited'", (sid,)).fetchone()
    assert (event["before"], event["after"], event["rationale"]) == \
        ({"summary": before}, {"summary": "Tightened by the PM."}, "merged two points")


def test_the_critic_sends_an_uncited_claim_back_before_the_pm_sees_it(client):
    uncited = cited(FEEDBACK, {**finding("Customers love the seats."), "locator": "", "source_file": ""})
    agent = client.runners[FEEDBACK] = FakeAgent(FEEDBACK, uncited, cited(FEEDBACK, finding()))
    body = new_run(client)
    start(client, body)
    assert [c.instruction is None for c in agent.seen] == [True, False]
    assert "find a citation or drop the claim" in agent.seen[1].instruction.lower()
    card = detail(client, body)["messages"][-1]
    assert card["payload"]["critic"]["attempts"] == 2 and "love the seats" not in card["content"]


def test_a_claim_that_stays_uncited_is_dropped_and_reported(client):
    uncited = {**finding("Customers love the seats."), "locator": "", "source_file": ""}
    answer = cited(FEEDBACK, finding())
    answer["findings"].append(uncited)
    client.runners[FEEDBACK] = FakeAgent(FEEDBACK, answer)
    body = new_run(client)
    start(client, body)
    card = detail(client, body)["messages"][-1]
    assert [f["text"] for f in card["payload"]["output"]["findings"]] == ["Seat ventilation is too weak."]
    assert card["payload"]["critic"]["retries_exhausted"] is True
    assert [d["text"] for d in card["payload"]["critic"]["dropped"]] == ["Customers love the seats."]
    assert "claim_dropped" in audit(client, step_id(client, body))


def test_a_failing_agent_ends_in_review_with_a_card_that_says_so(client):
    client.runners[FEEDBACK] = FakeAgent(FEEDBACK, RuntimeError("model unavailable"))
    body = new_run(client)
    assert start(client, body).status_code == 200
    step = detail(client, body)["runs"][0]["steps"][0]
    assert step["status"] == "awaiting_review" and "could not finish: RuntimeError: model unavailable" in \
        step["human_readable_summary"]
    card = detail(client, body)["messages"][-1]
    assert card["payload"]["failed"] is True and card["payload"]["output"] is None
    assert audit(client, step["id"]) == ["step_started", "step_failed"]
    client.runners[FEEDBACK] = FakeAgent(FEEDBACK)
    assert client.post(f"/api/steps/{step['id']}/retry", json={"note": "try again"}).status_code == 200
    assert detail(client, body)["messages"][-1]["payload"]["failed"] is False


def test_actions_are_refused_outside_their_state(client):
    body = new_run(client)
    planned = step_id(client, body, 2)
    assert client.post(f"/api/steps/{planned}/accept", json={}).status_code == 409
    start(client, body)
    assert start(client, body).status_code == 409                       # a run starts once
    assert client.put(f"/api/runs/{body['runs'][0]['id']}/plan", json={"agents": [TREND]}).status_code == 409
    assert client.post(f"/api/steps/{planned}/retry", json={"note": "go ahead"}).status_code == 409
    assert client.post("/api/steps/00000000-0000-0000-0000-000000000000/accept", json={}).status_code == 404


def test_synthesis_steps_are_checked_against_the_accepted_findings(client):
    """A cluster may only rest on findings the PM accepted earlier in the run."""
    client.holder["planner"] = FakePlanner(FEEDBACK, CLUSTERING)

    def clustering(ctx):
        ids = [f["id"] for f in ctx.accepted("findings")]
        return {"agent_name": CLUSTERING, "summary": "Clustering Agent looked at the accepted findings.",
                "clusters": [{"id": "c1", "label": "Seat comfort", "member_finding_ids": ids},
                             {"id": "c2", "label": "Invented", "member_finding_ids": ["not-a-finding"]}]}

    client.runners[CLUSTERING] = clustering
    body = new_run(client)
    start(client, body)
    client.post(f"/api/steps/{step_id(client, body)}/accept", json={})
    card = detail(client, body)["messages"][-1]
    assert [c["label"] for c in card["payload"]["output"]["clusters"]] == ["Seat comfort"]
    assert [d["item"] for d in card["payload"]["critic"]["dropped"]]


def test_context_task_carries_steering_and_the_weight_pattern_reads_a_nudge():
    from app.orchestration.agents import WEIGHT_RE

    ctx = StepContext(query="q", vehicle_line="G60", market="US", run_id="r", note="drop paywalled sources",
                      instruction="find a citation or drop the claim: x")
    assert ctx.task == "q\nPM steering: drop paywalled sources\nfind a citation or drop the claim: x"
    assert StepContext(query="q", vehicle_line="G60", market="US", run_id="r").task == "q"
    assert WEIGHT_RE.findall("please use business_signal=0.35 and effort_proxy = .1") == \
        [("business_signal", "0.35"), ("effort_proxy", ".1")]
