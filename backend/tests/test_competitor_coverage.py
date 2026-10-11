"""Coverage grows across sources without changing numerical identity or citation rules."""
import json
import time
from types import SimpleNamespace

import pytest

from app.comparisons import research as crawler


class Connection:
    def commit(self):
        pass

    def rollback(self):
        pass


def doc(url='https://example.org/technical', **kw):
    return {'id':url,'type':'web','file':url,'page':1,'heading':'Example Motors Compact',
            'content':'Smartphone integration is available for this vehicle family.',**kw}


def test_first_numeric_success_does_not_skip_complementary_sources(monkeypatch):
    calls=[]
    monkeypatch.setattr(crawler,'scrape',lambda c,cl,url,**kw:calls.append(url) or [doc(url)])
    monkeypatch.setattr(crawler,'find_technical_sources',lambda *a,**kw:[])
    monkeypatch.setattr(crawler,'extract_observations',lambda cl,n,v,p,m,docs:
        ([{'metric':'power','value':90,'chunk_id':docs[0]['id']}] if docs[0]['file'].endswith('.pdf') else
         [{'metric':'connectivity','value':None,'text_value':'Available smartphone integration','chunk_id':docs[0]['id']}],[]))
    values,_=crawler.collect_target(Connection(),object(),{'name':'Example Motors Compact'},'Variant A','ICE','EU',
        ['https://example.org/data.pdf','https://example.org/equipment'],time.monotonic()+100,{})
    assert calls==['https://example.org/data.pdf','https://example.org/equipment']
    assert {v['metric'] for v in values}=={'power','connectivity'}


def test_missing_fields_drive_search_after_successful_measurement(monkeypatch):
    queries=[]
    def search(*a,**kw):
        queries.append(kw['metrics'])
        return ['https://example.org/equipment'] if len(queries)==1 else []
    monkeypatch.setattr(crawler,'find_technical_sources',search)
    monkeypatch.setattr(crawler,'scrape',lambda c,cl,url,**kw:[doc(url)])
    monkeypatch.setattr(crawler,'extract_observations',lambda cl,n,v,p,m,docs:
        ([{'metric':'torque','value':200}] if docs[0]['file'].endswith('.pdf') else
         [{'metric':'comfort','value':None,'text_value':'Cabin equipment'}],[]))
    values,_=crawler.collect_target(Connection(),object(),{'name':'Example Motors Compact'},'Variant A','ICE','EU',
        ['https://example.org/data.pdf'],time.monotonic()+100,{})
    assert 'torque' not in queries[0] and 'comfort' in queries[0]
    assert set(queries[1]) <= {'connectivity','assistance','comfort'}
    assert {v['metric'] for v in values}=={'torque','comfort'}


def test_linked_pdf_is_not_downloaded_again_as_a_seed(monkeypatch):
    calls=[]
    monkeypatch.setattr(crawler,'scrape',lambda c,cl,url,**kw:calls.append(url) or [doc(url),doc('https://example.org/spec.pdf')])
    monkeypatch.setattr(crawler,'extract_observations',lambda *a:([{'metric':'torque','value':200}],[]))
    monkeypatch.setattr(crawler,'find_technical_sources',lambda *a,**kw:['https://example.org/spec.pdf'])
    crawler.collect_target(Connection(),object(),{'name':'Example Motors Compact'},'Variant A','ICE','EU',
        ['https://example.org/page','https://example.org/spec.pdf'],time.monotonic()+100,{})
    assert calls==['https://example.org/spec.pdf','https://example.org/page']


def test_model_family_features_are_labelled_and_cannot_supply_numeric_values():
    source=doc()
    claim={'metric':'connectivity','chunk_id':source['id'],'quote_lines':[1,1],
           'scope_field':'heading','scope_level':'model_family','powertrain':'ICE'}
    values,notes=crawler.validate_extract({'observations':[claim]},[source],'ICE','Variant A','Example Motors Compact')
    assert not notes and len(values)==1
    assert values[0]['basis']=='model_family_documented_feature'
    assert 'selected-variant availability unconfirmed' in values[0]['text_value']
    assert values[0]['quote']==source['content'] and values[0]['value'] is None
    for changes in ({'metric':'power','value':90,'unit':'kW'}, {'scope_field':'content'}, {'scope_level':'exact_variant'}):
        assert not crawler.validate_extract({'observations':[{**claim,**changes}]},[source],'ICE','Variant A','Example Motors Compact')[0]
    assert not crawler.validate_extract({'observations':[claim]},[source],'ICE','Variant A','Other Motors Compact')[0]


def test_wrapped_wheelbase_row_preserves_units_and_reported_interval():
    source=doc(url='https://example.org/TD-Example-Variant-A.pdf',content='Radstand von – bis // Spurweite vorne / hinten\n2800 – 2805 // 1600 / 1610\nin mm')
    claim={'metric':'wheelbase','chunk_id':source['id'],'quote_lines':[1,3],
           'scope_field':'file','value':2800,'upper_value':2805,'unit':'mm','powertrain':'ICE'}
    values,_=crawler.validate_extract({'observations':[claim]},[source],'ICE','Variant A','Example Motors Compact')
    assert values[0]['value']==2800 and values[0]['upper_value']==2805
    assert 'in mm' in values[0]['quote']
    repaired,_=crawler.validate_extract({'observations':[{**claim,'quote_lines':[1,2]}]},[source],'ICE','Variant A','Example Motors Compact')
    assert repaired[0]['quote']==values[0]['quote']
    assert not crawler.validate_extract({'observations':[claim]},[{**source,'content':source['content'].replace('in mm','')}],'ICE','Variant A','Example Motors Compact')[0]


def test_coverage_targets_respect_powertrain():
    assert 'consumption' not in crawler.missing_metrics([],'BEV')
    assert not {'range','charging','energy_consumption'} & set(crawler.missing_metrics([],'ICE'))
    assert 'power' not in crawler.missing_metrics([{'metric':'power','value':0}],'ICE')
    assert 'comfort' in crawler.missing_metrics([{'metric':'comfort','value':None}],'ICE')


@pytest.mark.parametrize('key,label,raw,wrong',[
    ('weight','Leergewicht ohne Fahrer / mit Fahrer /\n1500 / 1575 / 2000\nZul. Gesamtgewicht in kg',1500,1575),
    ('towing','Anhängelast bei 8% / 12% Steigung gebremst //\n2000 / 1800 // 750\nungebremst in kg',1800,2000),
    ('wheelbase','Radstand // Spurweite\n2800 – 2805 // 1600 / 1610\nin mm',2800,1600),
])
def test_wrapped_rows_use_the_correct_value_column(key,label,raw,wrong):
    source=doc(url='https://example.org/TD-Example-Variant-A.pdf',content=label)
    item={'metric':key,'chunk_id':source['id'],'quote_lines':[2,2],'scope_field':'file',
          'value':raw,'unit':crawler.METRICS[key][2],'powertrain':'ICE'}
    values,_=crawler.validate_extract({'observations':[item]},[source],'ICE','Variant A','Example Motors Compact')
    assert values[0]['value']==raw and values[0]['quote']==crawler.compact(label)
    assert not crawler.validate_extract({'observations':[{**item,'value':wrong}]},[source],'ICE','Variant A','Example Motors Compact')[0]


def test_unit_in_a_neighbouring_row_cannot_validate_wheelbase():
    for text in ('Width in mm 1800\nWheelbase 2800','Wheelbase 2800\nWidth in mm 1800'):
        source=doc(url='https://example.org/TD-Example-Variant-A.pdf',content=text)
        item={'metric':'wheelbase','chunk_id':source['id'],'quote_lines':[1,2],
              'scope_field':'file','value':2800,'unit':'mm','powertrain':'ICE'}
        assert not crawler.validate_extract({'observations':[item]},[source],'ICE','Variant A','Example Motors Compact')[0]


def test_catalog_top_speed_uses_the_selected_variant_column():
    from app.comparisons.catalog import parse_catalog
    model={'variants':[{'name':'Variant A','powertrain':'ICE'},{'name':'Variant B','powertrain':'ICE'}]}
    source={'id':'catalog','file':'internal.pdf','page':1,'content':'TECHNISCHE WERTE\nBMW Variant A Variant B\nHöchstgeschwindigkeit in km/h 210 230'}
    values,_=parse_catalog(model,'Variant B',[source])
    assert values[0]['metric']=='top_speed' and values[0]['value']==230
    assert values[0]['basis']=='maximum' and 'Variant B' in values[0]['scope_quote']


def test_technical_table_in_middle_of_brochure_is_retained(monkeypatch):
    import pdfplumber
    pages=[SimpleNamespace(page_number=i,extract_text=lambda i=i:
        'Selected Variant A\nMaximum power in kW 90\nTorque in Nm 200' if i==30 else
        'A general introduction without specifications or equipment descriptions.') for i in range(1,61)]
    class PDF:
        metadata={'Title':'Current brochure'}
        def __enter__(self):return self
        def __exit__(self,*a):pass
    pdf=PDF();pdf.pages=pages
    monkeypatch.setattr(pdfplumber,'open',lambda *a:pdf)
    _,passages,_=crawler.parse_source('https://example.org/brochure.pdf','application/pdf',b'fixture')
    assert len(passages)<=24 and any(p.page==30 and '90' in p.text for p in passages)
    assert [p.page for p in passages]==sorted(p.page for p in passages)
    ticks=iter([10,10,12])
    monkeypatch.setattr(crawler.time,'monotonic',lambda:next(ticks))
    _,limited,_=crawler.parse_source('https://example.org/brochure.pdf','application/pdf',b'fixture',deadline=11)
    assert [p.page for p in limited]==[1]


def test_missing_source_search_is_bounded_even_when_urls_repeat(monkeypatch):
    searched=[];downloaded=[]
    monkeypatch.setattr(crawler,'scrape',lambda c,cl,url,**kw:downloaded.append(url) or [doc(url)])
    monkeypatch.setattr(crawler,'extract_observations',lambda *a:([{'metric':'torque','value':200}],[]))
    monkeypatch.setattr(crawler,'find_technical_sources',lambda *a,**kw:searched.append(kw['metrics']) or ['https://example.org/spec.pdf'])
    _,notes=crawler.collect_target(Connection(),object(),{'name':'Example Motors Compact'},'Variant A','ICE','EU',
        ['https://example.org/spec.pdf'],time.monotonic()+100,{})
    assert len(searched)==2 and downloaded==['https://example.org/spec.pdf']
    assert any('Still missing' in n for n in notes)


@pytest.mark.parametrize('mode', ['automatic', 'manual_failed', 'manual_family', 'manual_success', 'disabled'])
def test_refresh_preserves_selected_variants_until_manual_evidence_is_validated(monkeypatch, mode):
    from app.knowledge import models
    calls=[];links=[];stored=[]
    prior={'rival_id':'rival','rival_variant':'Original','powertrain':'ICE','enabled':mode!='disabled',
           'selection':'manual','reason':'Previously chosen','discovery_url':'https://example.org/original.pdf'}
    monkeypatch.setattr(models,'get_model',lambda *a:{'id':'anchor','variants':[]})
    monkeypatch.setattr(models,'validate_variant',lambda *a:'ICE')
    monkeypatch.setattr(models,'start_research',lambda *a:{'id':'job'})
    monkeypatch.setattr(models,'finish_research',lambda *a:None)
    monkeypatch.setattr(models,'documents',lambda *a:[{'id':'internal'}])
    monkeypatch.setattr(models,'rivals',lambda *a,**kw:[prior] if kw['include_disabled'] else [])
    monkeypatch.setattr(models,'add_model',lambda *a:{'id':'rival','name':'Example Motors Compact'})
    monkeypatch.setattr(models,'link_rival',lambda *a:links.append(a[5:]))
    monkeypatch.setattr(models,'store_observations',lambda *a:stored.append(a[3:]) or len(a[-1]))
    monkeypatch.setattr(models,'overview',lambda *a:{'rivals':[prior]})
    monkeypatch.setattr('app.comparisons.catalog.parse_catalog',lambda *a:([],[]))
    monkeypatch.setattr(crawler,'discover',lambda *a,**kw:{'candidates':[
        {'name':'Example Motors Compact','variant':'Discovered','powertrain':'ICE',
         'urls':['https://example.org/discovered.pdf']}],'notes':[]})
    values=[] if mode=='manual_failed' else [{'metric':'comfort','value':None,'basis':'model_family_documented_feature'}] if mode=='manual_family' else [{'metric':'power','value':90}]
    def collect(c,cl,t,v,p,m,urls,*a):
        calls.append((v,urls))
        return values,[]
    monkeypatch.setattr(crawler,'collect_target',collect)
    manual=mode.startswith('manual')
    crawler.research(Connection(),'anchor','Reference','EU',client=object(),
                     **({'rival_name':'Example Motors Compact','rival_variant':'Requested',
                         'source_url':'https://example.org/requested.pdf'} if manual else {}))
    if mode=='disabled':
        assert not calls and not links
    elif manual:
        assert calls[0][0]=='Requested'
        assert bool(links)==(mode=='manual_success')
        if links:assert links[0][0]=='Requested' and links[0][-1]=='manual'
    else:
        assert calls==[('Original',['https://example.org/original.pdf','https://example.org/discovered.pdf'])]
        assert not links
        assert stored[-1][0]=='Original'
