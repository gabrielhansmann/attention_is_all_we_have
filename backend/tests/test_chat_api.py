"""Chat API tests against the real database, rolled back after every test (see conftest.db).
The orchestrator and the agents are fakes (see orch_fakes.py)."""
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from langgraph.checkpoint.memory import InMemorySaver

from app.api.deps import get_checkpointer, get_conn, get_connect, get_orchestrator, get_runners
from app.main import app
from app.orchestration.agents import RUNNERS
from app.orchestration.orchestrator import OrchestratorError, Scope
from orch_fakes import FEEDBACK, FINISH, TREND, FakeAgent, ScriptedOrchestrator, call


@pytest.fixture
def client(db):
    holder = {"orchestrator": ScriptedOrchestrator(call(TREND), FINISH)}
    runners = {name: FakeAgent(name) for name in RUNNERS}
    app.dependency_overrides[get_conn] = lambda: db
    app.dependency_overrides[get_connect] = lambda: (lambda: nullcontext(db))
    app.dependency_overrides[get_orchestrator] = lambda: holder["orchestrator"]
    app.dependency_overrides[get_runners] = lambda: runners
    app.dependency_overrides[get_checkpointer] = lambda: (lambda: nullcontext(InMemorySaver()))
    c = TestClient(app)
    c.holder, c.db = holder, db
    yield c
    app.dependency_overrides.clear()


def kinds(messages):
    return [m["kind"] for m in messages]


def thread(client, body):
    """The POST answers at once with the stored request; the orchestrator's work (already finished here, because
    the test client runs background tasks before returning) shows up when the thread is read."""
    return client.get(f"/api/conversations/{body['conversation']['id']}").json()


def test_agents_endpoint_lists_the_catalog_in_pipeline_order(client):
    body = client.get("/api/agents").json()
    assert [a["stage"] for a in body] == sorted(a["stage"] for a in body)
    assert all(a["available"] for a in body)


def test_a_request_opens_a_run_and_the_orchestrator_works_through_it(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), call(TREND), FINISH,
                                                         scope=Scope("Competitive trends", "G60", "US"))
    r = client.post("/api/conversations", json={"request": "What do we need to stay competitive in the US?"})
    assert r.status_code == 201 and kinds(r.json()["messages"]) == ["request"]
    body = thread(client, r.json())
    assert body["conversation"]["title"] == "Competitive trends"
    assert (body["conversation"]["vehicle_line"], body["conversation"]["market_code"]) == ("G60", "US")
    assert kinds(body["messages"]) == ["request", "system_note", "step_card", "system_note", "step_card", "final_result"]
    run = body["runs"][0]
    assert (run["vehicle_line"], run["market"], run["status"]) == ("G60", "US", "completed")
    assert [(s["position"], s["agent_name"], s["status"], s["planned_by"]) for s in run["steps"]] == \
        [(1, FEEDBACK, "accepted", "orchestrator"), (2, TREND, "accepted", "orchestrator")]
    assert client.db.execute("select created_by from public.pipeline_run where id = %s", (run["id"],)).fetchone() == {"created_by": "tester@example.com"}
    assert client.db.execute("select created_by from public.conversation where id = %s", (body["conversation"]["id"],)).fetchone() == {"created_by": "tester@example.com"}
    assert body["messages"][0]["payload"] == {"author": "tester@example.com"}


def test_scope_is_optional_and_means_all(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(call(TREND), FINISH, scope=Scope("t", None, None))
    body = thread(client, client.post("/api/conversations", json={"request": "Which trends matter?"}).json())
    assert (body["runs"][0]["vehicle_line"], body["runs"][0]["market"]) == ("ALL", "ALL")
    assert body["conversation"]["vehicle_line"] is None


def test_a_request_that_needs_no_agent_gets_a_note_and_an_aborted_run(client):
    client.holder["orchestrator"] = ScriptedOrchestrator(FINISH)
    body = thread(client, client.post("/api/conversations", json={"request": "hello there"}).json())
    assert kinds(body["messages"]) == ["request", "system_note"] and body["runs"][0]["status"] == "aborted"


def test_posting_to_an_existing_conversation_and_reading_the_thread(client):
    cid = client.post("/api/conversations", json={}).json()["conversation"]["id"]
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Which trends matter for the G60?"})
    assert r.status_code == 201 and kinds(r.json()["messages"]) == ["request"]       # answered at once; the work follows
    thread = client.get(f"/api/conversations/{cid}").json()
    assert kinds(thread["messages"]) == ["request", "system_note", "step_card", "final_result"] and len(thread["runs"]) == 1
    assert client.holder["orchestrator"].seen_requests == ["Which trends matter for the G60?"]


def test_orchestrator_failure_before_the_run_is_a_503_and_stores_nothing(client):
    cid = client.post("/api/conversations", json={}).json()["conversation"]["id"]
    client.holder["orchestrator"] = ScriptedOrchestrator(scope_error=OrchestratorError("OPENAI_API_KEY is not set"))
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": "Which trends matter?"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]
    assert client.get(f"/api/conversations/{cid}").json()["messages"] == []


def test_the_removed_review_endpoints_are_gone(client):
    zero = "00000000-0000-0000-0000-000000000000"
    assert client.put(f"/api/runs/{zero}/plan", json={"agents": [FEEDBACK]}).status_code == 404
    assert client.post(f"/api/runs/{zero}/start").status_code == 404
    for action in ("accept", "retry", "reject", "edit"):
        assert client.post(f"/api/steps/{zero}/{action}", json={}).status_code == 404


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
    ids=[c["id"] for c in client.get("/api/conversations").json()]
    assert ids.index(b)<ids.index(a)


def test_thread_order_is_stable_even_though_a_run_writes_several_messages_at_once(client):
    """Messages of one request share a transaction timestamp; the sequence number keeps their order."""
    for _ in range(5):
        client.holder["orchestrator"] = ScriptedOrchestrator(call(FEEDBACK), call(TREND), FINISH)
        body = thread(client, client.post("/api/conversations", json={"request": "competitive trends please"}).json())
        assert kinds(body["messages"]) == ["request", "system_note", "step_card", "system_note", "step_card", "final_result"]
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
