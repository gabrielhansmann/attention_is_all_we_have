"""Meaningful comparison invariants. Numbers here are test fixtures, never application data."""
from uuid import uuid4
import pytest
from app.knowledge.models import compare, validate_variant
from app.comparisons.research import has_number, validate_extract, search_urls
from app.comparisons.catalog import parse_catalog


def obs(model, value, **kwargs):
    return {'id':str(uuid4()),'model_id':model,'metric':'power','label':'System power','section':'Performance','value':value,'upper_value':None,'unit':'kW','standard':'','basis':'system','period':'current_offering','direction':'higher','powertrain':'ICE','type':'web','research_id':'job','citation':{'file':'https://example.org/spec','locator':'passage 1'},**kwargs}


def members(*names):
    return [{'rival_id':n,'name':n} for n in names]


def test_median_mean_exclude_anchor_and_duplicate_pages():
    result=compare([obs('own',100)], [obs('a',40),obs('a',40),obs('b',70),obs('c',190)],members('a','b','c'),'ICE')[0]
    assert result['mean']==100
    assert result['median']==70
    assert result['delta']==0
    assert result['median_delta']==30
    assert result['n']==3


def test_even_median_and_zero_are_real_values():
    result=compare([obs('own',0)],[obs('a',0),obs('b',40)],members('a','b'),'ICE')[0]
    assert result['median']==20 and result['mean']==20 and result['n']==2


@pytest.mark.parametrize('changes',[{'unit':'PS'},{'standard':'EPA'},{'basis':''},{'period':''},{'period':'2019'},{'powertrain':'BEV'}])
def test_incomparable_values_have_no_vote(changes):
    result=compare([obs('own',100)],[obs('rival',999,**changes)],members('rival'),'ICE')[0]
    assert result['mean'] is None and result['median'] is None and result['n']==0
    assert len(result['excluded'])==1


def test_intervals_aggregate_endpoints_never_midpoints():
    result=compare([obs('own',100,upper_value=120)],[obs('a',40,upper_value=80),obs('b',70,upper_value=100),obs('c',190,upper_value=220)],members('a','b','c'),'ICE')[0]
    assert result['mean'] is None and result['median'] is None
    assert result['median_range']=={'lower':70,'upper':100}
    assert result['mean_range']['lower']==100
    assert result['mean_range']['upper']==pytest.approx(400/3)
    assert result['delta'] is None


def test_conflicting_sources_in_same_snapshot_are_excluded():
    result=compare([obs('own',100)],[obs('a',40),obs('a',50)],members('a'),'ICE')[0]
    assert result['n']==0
    assert 'Conflicting' in result['excluded'][0]['reason']


def test_manual_model_unknown_powertrain_has_no_mean():
    result=compare([obs('own',100)],[obs('a',40)],members('a'),None)[0]
    assert result['n']==0


def test_numeric_quote_requires_whole_token_and_supports_german_decimal():
    assert not has_number('190 kW',90)
    assert has_number('Beschleunigung 8,3 s',8.3)
    assert has_number('Gepäckraum 1.200 l',1200)
    assert not has_number('Nothing measured',1)


def test_extraction_rejects_unquoted_value_and_wrong_standard():
    docs=[{'id':'c','content':'Audi test variant power 90 kW; range 400 km EPA','file':'https://example.org','page':1}]
    item={'metric':'power','chunk_id':'c','quote':'power 90 kW','scope_quote':'Audi test variant','value':99,'unit':'kW','powertrain':'ICE'}
    assert validate_extract({'observations':[item]},docs,'ICE')[0]==[]
    item={**item,'metric':'range','value':400,'unit':'km','quote':'range 400 km EPA','standard':'WLTP'}
    assert validate_extract({'observations':[item]},docs,'ICE')[0]==[]


def test_discovery_urls_only_come_from_search_tools_not_model_text():
    data={'output':[{'type':'web_search_call','action':{'sources':[{'url':'https://example.org/real?utm_source=openai'}]}},{'type':'message','content':[{'text':'https://example.org/invented','annotations':[]}]}]}
    assert search_urls(data)=={'https://example.org/real'}


def test_catalog_variant_columns_ranges_and_hybrid_system_power():
    model={'variants':[{'name':'A','powertrain':'PHEV'},{'name':'A xDrive','powertrain':'PHEV'},{'name':'B xDrive','powertrain':'PHEV'}]}
    doc={'id':'c','file':'provided.pdf','page':1,'content':'TECHNISCHE WERTE.\nBMW Plug-In-Hybrid A A xDrive B xDrive\nLeistung in kW (PS)1,2 220 (299) 230 (313) 360 (489)\nNennleistung in kW (PS) 140 (190) 140 (190) 230 (313)\nBeschleunigung 0–100 km/h in s 6,3 6,2 4,3\nKraftstoffverbrauch, kombiniert WLTP in l/100 km7 2,6 – 2,1 3,0 – 2,6 3,3 – 2,8\nGepäckraumvolumen in l 300 – 1.000 320 – 1.100 340 – 1.200'}
    result,gaps=parse_catalog(model,'A xDrive',[doc])
    lookup={o['metric']:o for o in result}
    assert lookup['power']['value']==230
    assert lookup['acceleration']['value']==6.2
    assert lookup['consumption']['value']==2.6 and lookup['consumption']['upper_value']==3.0
    assert lookup['consumption']['basis']=='weighted_combined'
    assert lookup['boot']['value']==320 and lookup['boot']['upper_value'] is None
    assert not gaps


def test_catalog_missing_cells_are_omitted():
    model={'variants':[{'name':'A','powertrain':'ICE'},{'name':'B','powertrain':'ICE'}]}
    doc={'id':'c','file':'provided.pdf','page':1,'content':'TECHNISCHE WERTE.\nBMW A B\nBeschleunigung 0–100 km/h in s 6,2'}
    result,gaps=parse_catalog(model,'B',[doc])
    assert not result and any('ambiguous' in g for g in gaps)


def test_variant_cannot_be_taken_from_another_model():
    with pytest.raises(ValueError):validate_variant({'variants':[{'name':'A','powertrain':'ICE'}]},'B')


def test_context_bound_conversation_and_followup_use_server_scope(db):
    from app.knowledge import models
    from app.orchestration import service
    model=models.add_model(db,f'Manual test {uuid4()}','Reference','BEV')
    conversation=service.create_conversation(db,actor='test',model_id=model['id'],variant='Reference',market='EU')
    class ForbiddenScope:
        def scope(self,request):raise AssertionError('A model chat must not rescope itself from free text.')
    result=service.post_request(db,conversation['id'],'Compare this with G70 US',ForbiddenScope(),'test')
    assert result['run']['vehicle_line']=='EXTERNAL'
    assert result['run']['market']=='EU'
    assert result['run']['comparison_context']['model']['id']==model['id']
    assert result['run']['comparison_context']['variant']=='Reference'


def test_registry_covers_dataset_lines_and_variants(db):
    from app.knowledge import models
    registered=models.list_models(db)
    inventory=models.inventory(db)
    own=[m for m in registered if m['origin']=='dataset']
    assert {m['vehicle_line'] for m in own}=={l['key'] for l in inventory['lines']}
    assert sum(len(m['variants']) for m in own)==len(inventory['variants'])


def test_final_answer_keeps_frozen_model_context_despite_followup_text(monkeypatch):
    from app.orchestration import loop
    from app.orchestration.orchestrator import Outcome
    packet={'model':{'id':'reference-model','name':'Reference'},'variant':'BEV variant','market':'EU',
            'comparisons':[{'median':70,'mean':100,'n':3}]}
    run={'id':'run','query_text':'Compare G70 US instead','vehicle_line':'EXTERNAL','market':'EU',
         'comparison_context':packet}
    history=[Outcome('Competitor Agent',1,True,'Sourced comparison',1,evidence=(('f1','Reference exceeds the median.'),))]
    monkeypatch.setattr(loop,'_history',lambda conn,run_id:history)

    class AnsweringOrchestrator:
        def answer(self,request,scope,outcomes,notes):
            assert 'MODEL COMPARISON CONTEXT' in request
            assert 'reference-model' in request and 'BEV variant' in request
            assert '"median": 70' in request and '"mean": 100' in request
            assert (scope.vehicle_line,scope.market)==('EXTERNAL','EU')
            assert outcomes==history
            return 'Reference exceeds the selected-cohort median [f1].'

    assert loop._answer(None,run,AnsweringOrchestrator(),None)=='Reference exceeds the selected-cohort median [f1].'


def test_all_dataset_overviews_include_cited_equipment_without_fake_scores(db):
    from app.knowledge import models
    for model in models.list_models(db):
        if model['origin']!='dataset':continue
        for variant in model['variants'] or [{'name':''}]:
            overview=models.overview(db,model['id'],variant['name'],'EU')
            for comparison in overview['comparisons']:
                assert comparison['direction'] in ('higher','lower','neutral')
                for finding in comparison['observations']:
                    assert finding['citation']['id'] and finding['quote']
                if not comparison['unit']:
                    assert comparison['median'] is None and comparison['mean'] is None


def test_existing_manual_family_can_register_additional_variants(db):
    from app.knowledge import models
    name=f'Manual variant test {uuid4()}'
    first=models.add_model(db,name,'A','ICE')
    second=models.add_model(db,name,'B','BEV')
    assert first['id']==second['id']
    assert {v['name'] for v in second['variants']}=={'A','B'}


def test_pdf_table_scope_cannot_be_borrowed_from_another_page():
    docs=[{'id':'a','type':'web','file':'https://example.org/spec.pdf','page':1,'content':'Selected variant A'}, {'id':'b','type':'web','file':'https://example.org/spec.pdf','page':2,'content':'Other variant B; power 80 kW'}]
    draft={'observations':[{'metric':'power','chunk_id':'b','quote':'power 80 kW','scope_quote':'Selected variant A','value':80,'unit':'kW','powertrain':'ICE'}]}
    assert not validate_extract(draft,docs,'ICE','A')[0]


def test_rival_without_observations_can_be_crawled_in_app(monkeypatch):
    from app.comparisons import research as crawler
    from app.knowledge import models
    rival_id=str(uuid4()); target=str(uuid4())
    packet={'model':{'vehicle_line':None},'comparisons':[],'rivals':[{'id':rival_id,'rival_id':target,'rival_variant':'A','powertrain':'ICE','discovery_url':'https://example.org/spec'}]}
    calls=[]
    monkeypatch.setattr(models,'overview',lambda *a:packet)
    monkeypatch.setattr(models,'start_research',lambda *a:{'id':'job'})
    monkeypatch.setattr(models,'finish_research',lambda *a:calls.append(('finish',a[2])))
    monkeypatch.setattr(models,'get_model',lambda *a:{'name':'Source model'})
    monkeypatch.setattr(models,'store_observations',lambda *a:len(a[-1]))
    monkeypatch.setattr(crawler,'scrape',lambda c,cl,url,**kw:calls.append(('crawl',url)) or [{'id':'stored'}])
    monkeypatch.setattr(crawler,'extract_observations',lambda *a:([{'metric':'power','value':80}],[]))
    class Conn:
        def commit(self):pass
        def rollback(self):pass
    crawler.revalidate(Conn(),'anchor','Reference','EU','recrawl',client=object(),rival_id=rival_id)
    assert calls==[('crawl','https://example.org/spec'),('finish','completed')]
    with pytest.raises(models.ModelNotFound):
        crawler.revalidate(Conn(),'anchor','Reference','EU','recrawl',client=object(),rival_id=str(uuid4()))
