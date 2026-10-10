"""Chat API tests against the real database, rolled back after every test (see conftest.db)."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conn, get_planner
from app.main import app
from app.orchestration.planner import PlannedAgent, PlannerError, PlanProposal, normalize_plan


class FakePlanner:
    def __init__(self, proposal=None, error=None):
        self.proposal, self.error, self.seen = proposal, error, []

    def plan(self, request):
        self.seen.append(request)
        if self.error:
            raise self.error
        return self.proposal


def proposal(*agents, line=None, market=None, title="A title"):
    return PlanProposal(title=title, vehicle_line=line, market=market,
                        steps=normalize_plan([PlannedAgent(a, f"because {a}") for a in agents]))


@pytest.fixture
def client(db):
    holder = {"planner": FakePlanner(proposal("Market & Trend Agent", line="G60", market="US"))}
    app.dependency_overrides[get_conn] = lambda: db
    app.dependency_overrides[get_planner] = lambda: holder["planner"]
    c = TestClient(app)
    c.holder, c.db = holder, db
    yield c
    app.dependency_overrides.clear()


def kinds(messages):
    return [m["kind"] for m in messages]


def test_agents_endpoint_lists_the_catalog_in_pipeline_order(client):
    body = client.get("/api/agents").json()
    assert [a["stage"] for a in body] == sorted(a["stage"] for a in body)
    assert {a["name"]: a["available"] for a in body}["Market & Trend Agent"] is True
    assert {a["name"]: a["available"] for a in body}["Competitor Agent"] is False


def test_a_request_becomes_a_stored_plan_of_planned_steps(client):
    client.holder["planner"] = FakePlanner(proposal("Competitor Agent", "Market & Trend Agent", line="G60", market="US",
                                                    title="Competitive trends"))
    r = client.post("/api/conversations", json={"request": "What do we need to stay competitive in the US?"})
    assert r.status_code == 201
    body = r.json()
    assert body["conversation"]["title"] == "Competitive trends"
    assert (body["conversation"]["vehicle_line"], body["conversation"]["market_code"]) == ("G60", "US")
    assert kinds(body["messages"]) == ["request", "plan", "system_note"]
    plan = next(m for m in body["messages"] if m["kind"] == "plan")
    assert [s["agent"] for s in plan["payload"]["steps"]] == ["Competitor Agent", "Market & Trend Agent"]
    assert "not built yet" in plan["content"].lower() and "Competitor Agent" in body["messages"][2]["content"]
    run = body["runs"][0]
    assert (run["vehicle_line"], run["market"]) == ("G60", "US")
    assert [(s["position"], s["agent_name"], s["status"], s["available"]) for s in run["steps"]] == \
        [(1, "Competitor Agent", "planned", False), (2, "Market & Trend Agent", "planned", True)]
    assert run["steps"][0]["plan_reason"] == "because Competitor Agent"
    audit = client.db.execute("select action, actor from public.audit_event where entity_id = %s", (run["id"],)).fetchall()
    assert audit == [{"action": "plan_created", "actor": "orchestrator"}]


def test_scope_is_optional_and_means_all(client):
    client.holder["planner"] = FakePlanner(proposal("Market & Trend Agent"))
    body = client.post("/api/conversations", json={"request": "Which trends matter?"}).json()
    assert (body["runs"][0]["vehicle_line"], body["runs"][0]["market"]) == ("ALL", "ALL")
    assert body["conversation"]["vehicle_line"] is None


def test_a_request_with_no_usable_agents_gets_a_note_and_no_run(client):
    client.holder["planner"] = FakePlanner(PlanProposal("x", None, None, []))
    body = client.post("/api/conversations", json={"request": "hello there"}).json()
    assert kinds(body["messages"]) == ["request", "system_note"] and body["runs"] == []
    assert body["conversation"]["title"] == "New research request"


def test_posting_to_an_existing_conversation_and_reading_the_thread(client):
    cid = client.post("/api/conversations", json={}).json()["conversation"]["id"]
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Which trends matter for the G60?"})
    assert r.status_code == 201 and kinds(r.json()["messages"]) == ["request", "plan"]
    thread = client.get(f"/api/conversations/{cid}").json()
    assert kinds(thread["messages"]) == ["request", "plan"] and len(thread["runs"]) == 1
    assert client.holder["planner"].seen == ["Which trends matter for the G60?"]


def test_planner_failure_is_a_503_and_stores_nothing(client):
    cid = client.post("/api/conversations", json={}).json()["conversation"]["id"]
    client.holder["planner"] = FakePlanner(error=PlannerError("OPENAI_API_KEY is not set"))
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Which trends matter?"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]
    assert client.get(f"/api/conversations/{cid}").json()["messages"] == []


def test_unknown_and_archived_conversations(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/conversations/{missing}").status_code == 404
    assert client.post(f"/api/conversations/{missing}/messages", json={"content": "trends please"}).status_code == 404
    cid = client.post("/api/conversations", json={}).json()["conversation"]["id"]
    assert client.patch(f"/api/conversations/{cid}", json={"status": "archived"}).json()["status"] == "archived"
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "trends please"})
    assert r.status_code == 409
    assert cid not in [c["id"] for c in client.get("/api/conversations").json()]
    assert cid in [c["id"] for c in client.get("/api/conversations?status=archived").json()]


def test_request_validation(client):
    cid = client.post("/api/conversations", json={}).json()["conversation"]["id"]
    for body in ({"content": "hi"}, {"content": "x" * 4001}, {}):
        assert client.post(f"/api/conversations/{cid}/messages", json=body).status_code == 422
    assert client.post("/api/conversations", json={"request": "no"}).status_code == 422
    assert client.get("/api/conversations?status=deleted").status_code == 422


def test_conversations_list_most_recently_active_first(client):
    a = client.post("/api/conversations", json={"title": "older"}).json()["conversation"]["id"]
    b = client.post("/api/conversations", json={"title": "newer"}).json()["conversation"]["id"]
    client.db.execute("update public.conversation set updated_at = now() - interval '1 day' where id = %s", (a,))
    assert [c["id"] for c in client.get("/api/conversations").json()][:2] == [b, a]


def test_the_pm_can_edit_the_plan_before_anything_starts(client):
    client.holder["planner"] = FakePlanner(proposal("Competitor Agent", "Market & Trend Agent"))
    body = client.post("/api/conversations", json={"request": "competitive trends"}).json()
    run_id = body["runs"][0]["id"]
    r = client.put(f"/api/runs/{run_id}/plan", json={"agents": ["Customer Feedback Agent", "Market & Trend Agent"]})
    assert r.status_code == 200
    out = r.json()
    assert [(s["position"], s["agent_name"], s["planned_by"]) for s in out["run"]["steps"]] == \
        [(1, "Customer Feedback Agent", "pm"), (2, "Market & Trend Agent", "orchestrator")]
    change = out["messages"][0]
    assert change["kind"] == "plan_change" and change["role"] == "pm"
    assert change["payload"]["removed"] == ["Competitor Agent"] and change["payload"]["added"] == ["Customer Feedback Agent"]
    thread = client.get(f"/api/conversations/{body['conversation']['id']}").json()
    assert [s["agent_name"] for s in thread["runs"][0]["steps"]] == ["Customer Feedback Agent", "Market & Trend Agent"]
    actions = [a["action"] for a in client.db.execute(
        "select action from public.audit_event where entity_id = %s order by timestamp, action", (run_id,)).fetchall()]
    assert sorted(actions) == ["plan_created", "plan_edited"]


def test_plan_edits_are_checked_and_locked_once_an_agent_starts(client):
    body = client.post("/api/conversations", json={"request": "trends please"}).json()
    run_id = body["runs"][0]["id"]
    bad = client.put(f"/api/runs/{run_id}/plan", json={"agents": ["Requirements Drafting Agent", "Customer Feedback Agent"]})
    assert bad.status_code == 422 and "needed before" in bad.json()["detail"]
    assert client.put(f"/api/runs/{run_id}/plan", json={"agents": ["Oracle Agent"]}).status_code == 422
    assert client.put(f"/api/runs/{run_id}/plan", json={"agents": []}).status_code == 422
    assert client.put("/api/runs/00000000-0000-0000-0000-000000000000/plan", json={"agents": ["Competitor Agent"]}).status_code == 404
    client.db.execute("update public.step set status = 'running' where run_id = %s and position = 1", (run_id,))
    locked = client.put(f"/api/runs/{run_id}/plan", json={"agents": ["Competitor Agent"]})
    assert locked.status_code == 409 and "already started" in locked.json()["detail"]


def test_thread_order_is_stable_even_though_a_request_writes_several_messages_at_once(client):
    """Messages of one request share a transaction timestamp; the sequence number keeps their order."""
    client.holder["planner"] = FakePlanner(proposal("Competitor Agent", "Market & Trend Agent"))
    for _ in range(8):
        body = client.post("/api/conversations", json={"request": "competitive trends please"}).json()
        assert kinds(body["messages"]) == ["request", "plan", "system_note"]
        assert kinds(client.get(f"/api/conversations/{body['conversation']['id']}").json()["messages"]) == \
            ["request", "plan", "system_note"]
        assert [m["seq"] for m in body["messages"]] == sorted(m["seq"] for m in body["messages"])


# ---- the real connection dependency (no override): read-only checks, so nothing is ever committed

def test_real_dependency_reads_through_a_dict_row_connection(db):
    c = TestClient(app)          # no overrides: uses app.api.deps.get_conn against the real database
    r = c.get("/api/conversations")
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert c.get("/api/agents").status_code == 200


def test_missing_or_unreachable_database_is_a_503_without_details(monkeypatch):
    from app.api import deps
    from app.config import Settings

    base = Settings(db_url=None, openai_api_key_set=False, openai_chat_model="m", embed_model="e", cors_origins=[])
    monkeypatch.setattr(deps, "get_settings", lambda: base)
    r = TestClient(app).get("/api/conversations")
    assert r.status_code == 503 and r.json()["detail"] == "database not configured"

    bad = Settings(db_url="postgresql://user:hunter2@127.0.0.1:1/postgres", openai_api_key_set=False,
                   openai_chat_model="m", embed_model="e", cors_origins=[])
    monkeypatch.setattr(deps, "get_settings", lambda: bad)
    r = TestClient(app).get("/api/conversations")
    assert r.status_code == 503 and "hunter2" not in r.text and "127.0.0.1" not in r.text
