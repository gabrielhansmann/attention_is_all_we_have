"""Requirement register, decisions, tracking and dossiers. Real database, rolled back after every test; no model or
embedding call is made (the evidence search is a fake)."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.deps import get_conn
from app.knowledge.tools import Citation
from app.main import app
from app.orchestration import register, service, tracking

FINDING = {"id": "f-1", "text": "Seat ventilation is too weak.", "source": "G60_feedback.xlsx", "locator": "sheet A, row 1",
           "signal_type": "complaint", "vehicle_line": "G60", "market": "US"}
REQ_ID = str(uuid4())
REQUIREMENT = {"id": REQ_ID, "title": "Stronger seat ventilation", "vehicle_line": "G60", "markets": ["US"],
               "description": {"text": "Seat ventilation reaches comfort in two minutes.", "finding_ids": ["f-1"], "citations": []},
               "metric": {"text": "Time to comfort <= 120 s", "finding_ids": ["f-1"], "citations": []},
               "acceptance_criteria": [], "linked_finding_ids": ["f-1"], "evidence_level": "Verified"}
SCORE = {"requirement_id": REQ_ID, "composite": 0.62, "proposed_tier": "High", "customer_relevance": 0.8,
         "business_signal": 0.4, "strategic_fit": 0.5, "effort_proxy": 0.5}


@pytest.fixture
def client(db):
    app.dependency_overrides[get_conn] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def run(db):
    conv = service.create_conversation(db, "test")
    r = db.execute("insert into public.pipeline_run (trigger, vehicle_line, market, query_text, created_by, conversation_id, status) "
                   "values ('pm_query','G60','US','seat ventilation','t',%s,'completed') returning *", (conv["id"],)).fetchone()
    outputs = [("Customer Feedback Agent", 1, {"findings": [FINDING]}),
               ("Requirements Drafting Agent", 3, {"requirements": [REQUIREMENT]}),
               ("Prioritization Agent", 4, {"scores": [SCORE]}),
               ("Documentation Agent", 5, {"dossier": "# Dossier\n- Seat ventilation [f-1]"})]
    for i, (name, stage, output) in enumerate(outputs):
        db.execute("insert into public.step (run_id, agent_name, stage, status, position, structured_output_refs) "
                   "values (%s,%s,%s,'accepted',%s,%s)", (r["id"], name, stage, i, Jsonb({"output": output})))
    register.sync_run(db, r["id"])
    return r


def test_a_finished_run_files_its_requirements_with_their_score(client, run):
    body = client.get("/api/requirements", params={"run_id": str(run["id"])}).json()
    [req] = body["requirements"]
    assert req["title"] == "Stronger seat ventilation" and req["status"] == "draft"
    assert req["score"]["composite"] == 0.62 and req["code"].startswith("R-")
    assert req["actions"] == ["approve", "reject", "challenge"]


def test_syncing_twice_keeps_one_row_and_never_overwrites_a_decision(client, db, run):
    client.post(f"/api/requirements/{REQ_ID}/decision", json={"action": "approve"})
    register.sync_run(db, run["id"])
    rows = client.get("/api/requirements", params={"run_id": str(run["id"])}).json()["requirements"]
    assert [r["status"] for r in rows] == ["tracked"]


def test_decisions_follow_the_lifecycle_and_are_audited(client, run):
    d = lambda action, note=None: client.post(f"/api/requirements/{REQ_ID}/decision", json={"action": action, "note": note})
    assert d("reject").status_code == 409                       # a reason is required
    assert d("supersede", "x").status_code == 409                # only a tracked requirement can be superseded
    ok = d("approve")
    assert ok.status_code == 200 and ok.json()["status"] == "tracked" and ok.json()["tracked_at"]
    assert ok.json()["actions"] == ["challenge", "supersede", "acknowledge"]
    assert d("challenge", "Need a US study").json()["status"] == "challenged"
    history = client.get(f"/api/requirements/{REQ_ID}").json()["history"]
    assert [e["action"] for e in history] == ["challenge", "approve"]
    assert history[0]["rationale"] == "Need a US study" and history[0]["actor"] == "tester@example.com"


def test_unknown_requirement_is_404(client):
    assert client.get(f"/api/requirements/{uuid4()}").status_code == 404
    assert client.post(f"/api/requirements/{uuid4()}/decision", json={"action": "approve"}).status_code == 404


def hit(cid, text, polarity):
    c = Citation("feedback", cid, "G60_feedback.xlsx", f"row {cid}", text)
    return SimpleNamespace(citation=c, text=text, meta={"polarity": polarity, "vehicle_line": "G60", "market_code": "US"})


def test_a_tracking_check_flags_new_and_contradicting_evidence_until_acknowledged(client, db, run):
    client.post(f"/api/requirements/{REQ_ID}/decision", json={"action": "approve"})
    fake = lambda query, **kw: [hit("n-1", "Seat ventilation is much too weak again", "negative"),
                                hit("n-2", "Seat ventilation works great and is fast", "positive")]
    result = tracking.check(db, "tester@example.com", search=fake)
    assert result["checked"] == 1 and not result["errors"]
    assert {f["flag_type"] for f in result["flags"]} == {"new_evidence", "contradicting"}

    [row] = client.get("/api/tracking").json()["requirements"]
    assert len(row["flags"]) == 2 and client.get("/api/tracking").json()["last_checked"]

    client.post(f"/api/requirements/{REQ_ID}/decision", json={"action": "acknowledge"})
    assert client.get("/api/tracking").json()["requirements"][0]["flags"] == []


def test_a_draft_is_not_checked(db, run):
    assert tracking.check(db, search=lambda *a, **k: [])["checked"] == 0


def test_dossiers_come_with_their_findings(client, run):
    [d] = [d for d in client.get("/api/dossiers").json() if d["run_id"] == str(run["id"])]
    assert d["dossier"].startswith("# Dossier") and d["findings"][0]["id"] == "f-1"
