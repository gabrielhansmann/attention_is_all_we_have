"""Real workspace reads, missing-value behavior and transactional requirement reviews."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api import workspace as workspace_api
from app.api.deps import get_conn
from app.main import app

client = TestClient(app)


@pytest.fixture
def workspace_db(db):
    app.dependency_overrides[get_conn] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_conn, None)


def requirement(db, *, status='pm_review', markets=None, line='G60'):
    return db.execute(
        "insert into public.requirement (title, description, vehicle_line, markets, status, origin) "
        "values (%s, 'Real stored description', %s, %s, %s, 'pm_query') returning id",
        (f'Review {uuid4()}', line, markets if markets is not None else ['EU'], status)).fetchone()['id']


def test_workspace_uses_database_scope_labels(workspace_db):
    key = f'T-{uuid4()}'
    workspace_db.execute("insert into public.ontology (kind, key, label) values ('vehicle_line', %s, 'New database line')", (key,))
    response = client.get('/api/workspace/config')
    assert response.status_code == 200
    assert {'key': key, 'label': 'New database line'} in response.json()['lines']
    scoped = client.get('/api/workspace', params={'line': key}).json()
    assert scoped['counts']['feedback'] == scoped['counts']['catalog_options'] == 0
    assert scoped['requirements'] == scoped['sales'] == scoped['options'] == []


def test_workspace_preserves_missing_scores_and_real_zero(workspace_db):
    unscored = requirement(workspace_db)
    zero = requirement(workspace_db)
    workspace_db.execute(
        "insert into public.score (requirement_id, customer_relevance, business_signal, strategic_fit, effort_proxy, "
        "confidence, composite, weight_vector_version, computed_by) values (%s,0,0,0,0,0,0,'real-v1','Test')", (zero,))
    response = client.get('/api/workspace?line=G60&market=EU')
    assert response.status_code == 200
    rows = {r['id']: r for r in response.json()['requirements']}
    assert rows[str(unscored)]['score'] is None and rows[str(unscored)]['confidence'] is None
    assert rows[str(zero)]['score'] == rows[str(zero)]['confidence'] == 0
    assert rows[str(unscored)]['metric'] is None and rows[str(unscored)]['citations'] == []


def test_workspace_filters_requirements_but_includes_shared_scope(workspace_db):
    eu = requirement(workspace_db)
    us = requirement(workspace_db, markets=['US'])
    shared = requirement(workspace_db, markets=[], line='ALL')
    other = requirement(workspace_db, line='F70')
    ids = {r['id'] for r in client.get('/api/workspace?line=G60&market=EU').json()['requirements']}
    assert {str(eu), str(shared)} <= ids
    assert str(us) not in ids and str(other) not in ids


def test_workspace_resolves_stored_web_citations(workspace_db):
    req_id = requirement(workspace_db)
    source = workspace_db.execute("insert into public.source (type, uri) values ('web','https://example.test/research') returning id").fetchone()['id']
    finding = workspace_db.execute(
        "insert into public.finding (source_id, locator, text, signal_type, evidence_level, extracted_by) "
        "values (%s,'section Comfort','Stored source excerpt','market_trend','Interpreted','Test') returning id", (source,)).fetchone()['id']
    workspace_db.execute("insert into public.requirement_finding (requirement_id,finding_id) values (%s,%s)", (req_id, finding))
    row = next(r for r in client.get('/api/workspace').json()['requirements'] if r['id'] == str(req_id))
    assert row['citations'][0]['file'] == 'https://example.test/research'
    assert row['citations'][0]['quote'] == 'Stored source excerpt'


def test_requirement_review_is_saved_and_audited(workspace_db):
    req_id = requirement(workspace_db)
    response = client.patch(f'/api/requirements/{req_id}/status', json={'status':'tracked', 'expected_status':'pm_review', 'reason':'Source supports this requirement'})
    assert response.status_code == 200 and response.json()['status'] == 'tracked'
    row = workspace_db.execute('select status from public.requirement where id = %s', (req_id,)).fetchone()
    assert row['status'] == 'tracked'
    event = workspace_db.execute("select * from public.audit_event where entity_id = %s and action = 'requirement_status_changed'", (req_id,)).fetchone()
    assert event['actor'] == 'tester@example.com' and event['rationale'] == 'Source supports this requirement'
    assert event['before'] == {'status':'pm_review'} and event['after'] == {'status':'tracked'}
    snapshot = client.get('/api/workspace?line=G60&market=EU').json()
    assert any(a['id'] == str(event['id']) for a in snapshot['audits'])


def test_stale_or_invalid_review_changes_nothing(workspace_db):
    req_id = requirement(workspace_db)
    for expected, new in [('draft','tracked'), ('pm_review','superseded')]:
        response = client.patch(f'/api/requirements/{req_id}/status', json={'status':new, 'expected_status':expected, 'reason':'Reason recorded'})
        assert response.status_code == 409
    assert workspace_db.execute('select status from public.requirement where id=%s', (req_id,)).fetchone()['status'] == 'pm_review'
    assert workspace_db.execute('select count(*) as n from public.audit_event where entity_id=%s', (req_id,)).fetchone()['n'] == 0
    assert client.patch(f'/api/requirements/{uuid4()}/status', json={'status':'tracked','expected_status':'pm_review','reason':'Valid reason'}).status_code == 404


def test_blank_review_and_unknown_scope_are_rejected(workspace_db):
    req_id = requirement(workspace_db)
    assert client.patch(f'/api/requirements/{req_id}/status', json={'status':'tracked','expected_status':'pm_review','reason':'   '}).status_code == 422
    assert client.get('/api/workspace?line=unknown').status_code == 422
    assert client.get('/api/workspace?market=unknown').status_code == 422


def test_only_accepted_agent_outputs_appear_in_workspace(workspace_db):
    run = workspace_db.execute("insert into public.pipeline_run (trigger, vehicle_line, market, created_by) values ('pm_query','G60','EU','test') returning id").fetchone()['id']
    accepted = workspace_db.execute(
        "insert into public.step (run_id,agent_name,stage,status,position,structured_output_refs,resolved_at) "
        "values (%s,'Market & Trend Agent',1,'accepted',1,%s,now()) returning id", (run, Jsonb({'output':{'summary':'Actual stored web research'}}))).fetchone()['id']
    workspace_db.execute(
        "insert into public.step (run_id,agent_name,stage,status,position,structured_output_refs) "
        "values (%s,'Customer Feedback Agent',1,'rejected',2,%s)", (run, Jsonb({'output':{'summary':'Rejected result'}})))
    rows = client.get('/api/workspace?line=G60&market=EU').json()['results']
    assert any(r['id'] == str(accepted) and r['output']['summary'] == 'Actual stored web research' for r in rows)
    assert not any(r['output'].get('summary') == 'Rejected result' for r in rows)


def test_workspace_outage_never_returns_fixtures(workspace_db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('password=secret host=private.example')
    monkeypatch.setattr(workspace_api.workspace, 'snapshot', boom)
    response = client.get('/api/workspace')
    assert response.status_code == 503 and 'secret' not in response.text and 'private.example' not in response.text
