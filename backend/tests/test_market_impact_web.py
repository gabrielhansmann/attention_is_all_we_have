"""Citation, geography, privacy and failure boundaries for public feature research."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents import market_impact_web as web
from app.agents.market_trend_agent import SourceDoc
from app.api import market_impact
from app.main import app


def doc(url='https://jdpower.com/study', text='US owners value seat ventilation for comfort.'):
    return SourceDoc(url=url, title='US seat ventilation study', snippet=text, retrieved_at='2026-10-11T12:00:00Z')


def item(**changes):
    return {'source_index': 0, 'market': 'US', 'stance': 'supports', 'excerpt': 'US owners value seat ventilation for comfort.', 'scope_excerpt': 'US owners value seat ventilation for comfort.', **changes}


def test_only_annotated_sources_and_grounded_excerpts_are_accepted():
    rows = [item(source_index=999), item(excerpt='A made up share forecast'), item(market='Mars'), item()]
    result = web.validate_sources([doc()], {'evidence': rows}, 'seat ventilation')
    assert len(result) == 1 and result[0]['url'] == doc().url
    assert result[0]['stance'] == 'supports'
    assert web.validate_sources([doc('https://127.0.0.1/source')], {'evidence': [item()]}, 'seat ventilation') == []


@pytest.mark.parametrize('url', ['https://bmwusa.com/features', 'https://www.reddit.com/r/cars'])
def test_manufacturer_and_social_claims_never_determine_color(url):
    result = web.validate_sources([doc(url)], {'evidence': [item()]}, 'seat ventilation')
    assert result[0]['stance'] == 'context'


def test_us_evidence_cannot_be_counted_as_chinese_or_rest_of_world_evidence():
    result = web.validate_sources([doc()], {'evidence': [item(market='CN'), item(market='RoW')]}, 'seat ventilation')
    assert result == []


def test_catalog_queries_are_generic_public_terms_and_unknown_labels_stay_local():
    assert web.public_topic('19" Leichtmetallräder Triplex-Speiche 933', custom=False) == '19 inch wheels'
    assert web.public_topic('Secret development package 991', custom=False) is None
    assert web.public_topic('Seat ventilation', custom=True) == 'seat ventilation'


def test_web_calls_receive_only_public_query_and_public_summaries(monkeypatch):
    calls = []
    monkeypatch.setattr(web, 'sources_from_web_search_response', lambda *args: [doc()])
    monkeypatch.setattr(web.tools, 'public_web_text', lambda url: ('US seat ventilation study', doc().snippet))
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text='{"evidence":[{"source_index":0,"market":"US","stance":"supports","excerpt":"US owners value seat ventilation for comfort.","scope_excerpt":"US owners value seat ventilation for comfort."}]}')
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = web.research('G60', 'seat ventilation', client=client)
    assert result['markets'][0]['direction'] == 'positive'
    assert len(calls) == 5 and calls[0]['tool_choice'] == 'required'
    assert all(c['store'] is False for c in calls)
    assert 'feedback.xlsx' not in str(calls) and 'polarity_count' not in str(calls)


def test_web_route_isolated_outage_does_not_expose_secrets(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('password=secret host=private')
    monkeypatch.setattr(market_impact.market_impact_web, 'assess', fail)
    response = TestClient(app).post('/api/market-impact/web-assessment', json={'line': 'G60', 'feature': 'Seat ventilation'})
    assert response.status_code == 503 and 'secret' not in response.text and 'private' not in response.text
    assert 'Internal feedback remains available' in response.json()['detail']


def test_indian_availability_article_cannot_be_rewritten_as_chinese_demand():
    article = doc('https://www.autocarindia.com/wheels', 'BMW India has made the 19-inch wheels standard based on customer feedback.')
    claims = [{'source_index': 0, 'market': 'CN', 'stance': 'supports',
               'excerpt': 'Chinese customers welcomed 19-inch wheels.', 'scope_excerpt': 'Chinese customers welcomed 19-inch wheels.'}]
    assert web.validate_sources([article], {'evidence': claims}, '19 inch wheels') == []


def test_shopping_pages_are_excluded_before_reading(monkeypatch):
    monkeypatch.setattr(web.tools, 'public_web_text', lambda url: pytest.fail('must not read excluded shopping sites'))
    assert web.verified_pages([doc('https://carinterior.alibaba.com/guide')], 'seat ventilation') == []


def test_unfetchable_pages_are_evidence_gaps_not_generated_summary_fallbacks(monkeypatch):
    def fail(url): raise RuntimeError('403')
    monkeypatch.setattr(web.tools, 'public_web_text', fail)
    assert web.verified_pages([doc()], 'seat ventilation') == []


def test_verified_mentions_without_classified_market_direction_remain_global_context():
    result = web.general_context([doc()], [], 'seat ventilation')
    assert len(result) == 1 and result[0]['market'] is None and result[0]['stance'] == 'context'
    assert result[0]['summary'] in doc().snippet and len(result[0]['summary'].split()) <= 25
    assert web.general_context([doc()], [{'url': doc().url, 'scope': 'United States evidence'}], 'seat ventilation') == []
