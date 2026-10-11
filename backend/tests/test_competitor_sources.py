"""Crawler recovery and citation correctness; specifications below are synthetic fixtures."""
from types import SimpleNamespace
import json
import time

import pytest

from app.comparisons import research as crawler
from app.comparisons.sources import extract_html, technical_links
from app.ingest.upload import UploadError


def document(**changes):
    return {'id':'c','type':'web','file':'https://example.org/spec.pdf','page':1,
            'content':'Selected variant 30 TFSI\nMax. power in kW 90\nEngine torque in Nm 200',**changes}


def fact(**changes):
    return {'metric':'power','chunk_id':'c','quote_lines':[2,2],
            'scope_lines':[1,1],'value':90,'unit':'kW','powertrain':'ICE',**changes}


def test_pdf_original_rows_are_copied_without_rewriting_quotes():
    values,notes=crawler.validate_extract({'observations':[fact(quote='model-rewritten text')]},[document()],'ICE','30 TFSI')
    assert not notes and values[0]['quote']=='Max. power in kW 90'
    assert values[0]['scope_quote']=='Selected variant 30 TFSI'


def test_extraction_enforces_schema_and_separate_identity_lines():
    calls=[]
    draft={'observations':[{'metric':'power','chunk_id':'c','quote_start':2,'quote_end':2,
        'scope_chunk_id':'c','scope_field':'content','scope_start':1,'scope_end':1,
        'value':90,'unit':'kW','powertrain':'ICE'}],'gaps':[]}
    def complete(**kw):
        calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(draft)))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    values,_=crawler.extract_observations(client,'Test model','30 TFSI','ICE','EU',[document()])
    assert values[0]['quote']=='Max. power in kW 90' and len(calls)==1
    assert calls[0]['response_format']['json_schema']['strict']


def test_engine_and_boost_are_not_silently_treated_as_system_power():
    docs=[document(content='Selected variant 30 TFSI\nEngine power 90 kW + 10 kW MHEV boost')]
    assert not crawler.validate_extract({'observations':[fact()]},docs,'ICE','30 TFSI')[0]


def test_unrelated_standard_cannot_hide_otherwise_comparable_values():
    assert not crawler.validate_extract({'observations':[fact(standard='system')]},[document()],'ICE','30 TFSI')[0]


@pytest.mark.parametrize('span',[[0,2],[2,4],[2,1],[True,2],[1,8],'2',[2]])
def test_invalid_line_spans_cannot_supply_values(span):
    assert not crawler.validate_extract({'observations':[fact(quote_lines=span)]},[document()],'ICE','30 TFSI')[0]


def test_continuation_page_requires_variant_in_actual_pdf_filename():
    item=fact(quote_lines=[1,1],scope_field='file')
    continuation=document(file='https://example.org/TD-Test-30-TFSI.pdf',page=2,content='Max. power in kW 90')
    values,_=crawler.validate_extract({'observations':[item]},[continuation],'ICE','30 TFSI')
    assert values[0]['scope_quote']=='TD-Test-30-TFSI.pdf'
    assert not crawler.validate_extract({'observations':[item]},[document(page=2,content=continuation['content'])],'ICE','30 TFSI')[0]


def test_scope_line_from_another_pdf_page_is_rejected():
    docs=[document(id='header'),document(page=2,content='Different variant\nMax. power in kW 90')]
    assert not crawler.validate_extract({'observations':[fact(scope_chunk_id='header')]},docs,'ICE','30 TFSI')[0]


def test_technical_filename_recovers_identity_without_an_invented_scope_quote():
    doc=document(file='https://example.org/TD-Test-30-TFSI.pdf',page=2,content='Max. power in kW 90')
    item=fact(quote_lines=[1,1],scope_lines=[1,1])
    values,_=crawler.validate_extract({'observations':[item]},[doc],'ICE','30 TFSI')
    assert values[0]['scope_quote']=='TD-Test-30-TFSI.pdf'
    for filename in ('random-hash-30TFSI.pdf','TD-Test-35-TFSI.pdf'):
        assert not crawler.validate_extract({'observations':[item]},[{**doc,'file':'https://example.org/'+filename}],'ICE','30 TFSI')[0]


def test_html_local_heading_identifies_variant_but_sibling_heading_cannot():
    doc=document(file='https://example.org/technical',heading='Selected 30 TFSI',content='Max. power in kW 90')
    item=fact(quote_lines=[1,1],scope_field='heading')
    assert crawler.validate_extract({'observations':[item]},[doc],'ICE','30 TFSI')[0]
    sibling=document(id='other',file=doc['file'],heading='Selected 35 TFSI',content='Selected 30 TFSI')
    item=fact(quote_lines=[1,1],scope_field='content',scope_chunk_id='other')
    assert not crawler.validate_extract({'observations':[item]},[doc,sibling],'ICE','30 TFSI')[0]


def test_html_table_preserves_cell_boundaries_and_publisher_pdf_links():
    raw=b'<title>Technical data</title><h2>Selected 30 TFSI</h2><table><tr><th>Maximum system power in kW</th><td>90 for the selected model variant</td></tr></table><a href="/technical-30-TFSI.pdf">Data sheet</a><a href="https://unrelated.example/technical.pdf">External</a>'
    title,passages,links=extract_html('https://example.org/model','text/html',raw)
    assert title=='Technical data'
    assert any('kW 90' in p.text and p.heading=='Selected 30 TFSI' for p in passages)
    assert links==['https://example.org/technical-30-TFSI.pdf']
    assert not technical_links('https://example.org/model',['javascript:fake.pdf','https://user:password@example.org/a.pdf','https://localhost/a.pdf'])


def test_robots_cache_checks_each_path_without_refetching(monkeypatch):
    calls=[]
    def fetch(url,**kw):
        calls.append(url)
        return 'text/plain',b'User-agent: *\nDisallow: /private\n'
    monkeypatch.setattr(crawler,'fetch_bytes',fetch)
    cache={}
    assert crawler.permitted('https://example.org/public',cache=cache)
    assert not crawler.permitted('https://example.org/private/data.pdf',cache=cache)
    assert calls==['https://example.org/robots.txt']


def test_unavailable_robots_remains_fail_closed(monkeypatch):
    def fail(*args,**kw):raise UploadError('Source could not be reached.')
    monkeypatch.setattr(crawler,'fetch_bytes',fail)
    with pytest.raises(UploadError,match='not scraped'):
        crawler.permitted('https://example.org/spec.pdf',cache={})


def test_json_tool_citations_do_not_require_an_extra_llm_call():
    assert crawler.read_search_json(object(),'{"urls":[]}\nsource citation')=={'urls':[]}


def test_technical_search_rejects_invented_urls(monkeypatch):
    response=SimpleNamespace(output_text='{"urls":["https://example.org/actual.pdf","https://example.org/invented.pdf"]}',
        model_dump=lambda:{'output':[{'type':'web_search_call','action':{'sources':[{'url':'https://example.org/actual.pdf'}]}}]})
    client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:response))
    assert crawler.find_technical_sources(client,'Test model','30 TFSI','EU',time.monotonic()+60)==['https://example.org/actual.pdf']


def test_discovery_confirms_variant_and_pdf_before_using_marketing_lead():
    calls=[]
    def response(variant,url):
        candidate={'name':'Test model','variant':variant,'powertrain':'ICE','reason':'Source-selected candidate','urls':[url]}
        return SimpleNamespace(output_text=json.dumps({'candidates':[candidate]}),
            model_dump=lambda:{'output':[{'type':'web_search_call','action':{'sources':[{'url':url}]}}]})
    results=iter([response('old search lead','https://example.org/marketing'),response('30 TFSI','https://example.org/TD-30-TFSI.pdf')])
    def create(**kw):calls.append(kw);return next(results)
    client=SimpleNamespace(responses=SimpleNamespace(create=create))
    result=crawler.discover(client,{'name':'Reference BMW','markets':['EU']},'Reference','ICE','EU',deadline=time.monotonic()+60)
    assert len(calls)==2
    assert result['candidates'][0]['variant']=='30 TFSI'
    assert result['candidates'][0]['urls']==['https://example.org/TD-30-TFSI.pdf']


def test_comparison_search_model_can_be_configured_independently(monkeypatch):
    monkeypatch.delenv('COMPARISON_SEARCH_MODEL',raising=False)
    monkeypatch.delenv('RESEARCH_AGENT_MODEL',raising=False)
    assert crawler.search_model()=='gpt-4.1'
    monkeypatch.setenv('RESEARCH_AGENT_MODEL','general-research')
    assert crawler.search_model()=='general-research'
    monkeypatch.setenv('COMPARISON_SEARCH_MODEL','comparison-specific')
    assert crawler.search_model()=='comparison-specific'


class Connection:
    def commit(self):pass


def test_stale_sources_leave_capacity_for_new_technical_search(monkeypatch):
    calls=[]
    def scrape(conn,client,url,**kw):
        calls.append(url)
        if url.endswith('actual.pdf'):return [document()]
        raise UploadError('HTTP 404')
    monkeypatch.setattr(crawler,'scrape',scrape)
    monkeypatch.setattr(crawler,'find_technical_sources',lambda *a:['https://example.org/actual.pdf'])
    monkeypatch.setattr(crawler,'extract_observations',lambda *a:([{'metric':'power','value':90}],[]))
    values,notes=crawler.collect_target(Connection(),object(),{'name':'Test model'},'30 TFSI','ICE','EU',
        [f'https://example.org/stale{i}.pdf' for i in range(4)],time.monotonic()+100,{})
    assert values[0]['value']==90
    assert calls[-1]=='https://example.org/actual.pdf' and len(calls)==3
    assert any('HTTP 404' in note for note in notes)


def test_marketing_only_source_triggers_recovery_search(monkeypatch):
    calls=[]
    monkeypatch.setattr(crawler,'scrape',lambda conn,client,url,**kw:calls.append(url) or [document(file=url)])
    monkeypatch.setattr(crawler,'find_technical_sources',lambda *a:['https://example.org/actual.pdf'])
    def extract(client,name,variant,powertrain,market,docs):
        return ([{'metric':'power','value':90}],[]) if docs[0]['file'].endswith('.pdf') else ([],['No specifications'])
    monkeypatch.setattr(crawler,'extract_observations',extract)
    values,_=crawler.collect_target(Connection(),object(),{'name':'Test model'},'30 TFSI','ICE','EU',
        ['https://example.org/marketing'],time.monotonic()+100,{})
    assert values[0]['value']==90 and calls==['https://example.org/marketing','https://example.org/actual.pdf']


def test_expired_collection_does_not_start_network_work(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('No work after the deadline')
    monkeypatch.setattr(crawler,'scrape',forbidden)
    monkeypatch.setattr(crawler,'find_technical_sources',forbidden)
    values,notes=crawler.collect_target(Connection(),object(),{'name':'Test model'},'30 TFSI','ICE','EU',
        ['https://example.org/data'],time.monotonic()-1,{})
    assert not values and notes


def test_real_registry_bulk_reads_match_individual_models_with_fixed_query_budget(db):
    from app.knowledge import models
    models.sync_inventory(db)
    class Counted:
        count=0
        def execute(self,*args,**kw):
            self.count+=1
            return db.execute(*args,**kw)
    counted=Counted()
    registered=models.list_models(counted)
    assert counted.count==4
    for model in registered:
        assert model==models.get_model(db,model['id'])


def test_feedback_examples_keep_counts_and_sources_in_five_queries(db):
    from app.knowledge import models
    model=next(m for m in models.list_models(db) if m['origin']=='dataset' and 'EU' in m['markets'])
    class Counted:
        count=0
        def execute(self,*args,**kw):
            self.count+=1
            return db.execute(*args,**kw)
    counted=Counted()
    sections=models.dataset_sections(counted,model,'EU')
    assert counted.count==5 and sections['feedback']
    for section in sections['feedback']:
        assert len(section['examples'])==min(3,section['n'])
        assert all(e['citation']['quote']==e['comment'] and e['citation']['file']==e['file'] for e in section['examples'])
        assert [e['row_no'] for e in section['examples']]==sorted(e['row_no'] for e in section['examples'])
