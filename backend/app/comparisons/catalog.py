"""Read current internal catalog tables locally; no internal passage leaves the backend."""
from __future__ import annotations

import re
from collections import defaultdict


def number(token: str) -> float:
    return float(token.replace('.','').replace(',','.'))


def parse_catalog(model: dict, variant: str, docs: list[dict]) -> tuple[list[dict],list[str]]:
    from .research import METRICS
    variants={v['name']:v['powertrain'] for v in model['variants']}
    if variant not in variants:return [],['No catalog variant was registered for this model.']
    # Longest names first prevents 520d from consuming the 520d xDrive header.
    pattern=re.compile(r'(?<!\w)(?:'+ '|'.join(re.escape(v) for v in sorted(variants,key=len,reverse=True))+r')(?!\w)',re.I)
    pages=defaultdict(list)
    for doc in docs:pages[(doc['file'],doc['page'])].append(doc)
    result=[];seen=set();notes=[]
    rules=[
        ('power',r'^(?:Leistung in [kK][wW]|Leistung Gesamtfahrzeugantrieb in [kK][wW])', 'system','power'),
        ('acceleration',r'^Beschleunigung 0[–-]100 km/h in s','standing_0_100','plain'),
        ('consumption',r'^Kraftstoffverbrauch, kombiniert WLTP in l/100 km','combined','range'),
        ('energy_consumption',r'^Energieverbrauch, kombiniert WLTP in kWh/100 km','combined','range'),
        ('range',r'^Elektrische Reichweite, WLTP in km','combined','range'),
        ('boot',r'^Gepäckraumvolumen in l','seats_up','boot'),
        ('charging',r'^Maximale Ladeleistung DC in kW','peak_dc','plain'),
    ]
    for group in pages.values():
        headers=[line for d in group for line in d['content'].splitlines() if line.startswith('BMW ') and 'TECHNISCHE WERTE' in '\n'.join(x['content'] for x in group)]
        header=next((line for line in headers if pattern.search(line) and any(m.group().casefold()==variant.casefold() for m in pattern.finditer(line))),None)
        if not header:continue
        matches=list(pattern.finditer(header));names=[m.group().casefold() for m in matches]
        index=names.index(variant.casefold());columns=len(names)
        for d in group:
            for line in d['content'].splitlines():
                for key,label_pattern,basis,kind in rules:
                    found=re.search(label_pattern,line)
                    if not found or key in seen:continue
                    tail=line[found.end():]
                    if kind=='power':
                        cells=[(float(a.replace('.','')),None) for a in re.findall(r'(\d+(?:\.\d{3})*)\s*\(\d+\)',tail)]
                    elif kind=='range':
                        cells=[tuple(sorted((number(a),number(b)))) for a,b in re.findall(r'(\d+(?:[.,]\d+)*)\s*[–-]\s*(\d+(?:[.,]\d+)*)',tail)]
                    elif kind=='boot' and re.search(r'\d\s*[–-]',tail):
                        cells=[(number(a),None) for a,b in re.findall(r'(\d+(?:[.,]\d+)*)\s*[–-]\s*(\d+(?:[.,]\d+)*)',tail)]
                    else:
                        tokens=re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?!\w)',tail)
                        cells=[(number(t),None) for t in tokens]
                    if len(cells)!=columns:
                        notes.append(f'{METRICS[key][1]}: table columns are incomplete or ambiguous; value omitted.');continue
                    value,upper=cells[index]
                    section,label,unit,direction=METRICS[key]
                    # PHEV fuel figures are charge-weighted; never pool with charge-depleted figures.
                    if key in ('consumption','energy_consumption') and variants[variant]=='PHEV':basis='weighted_combined'
                    result.append({'metric':key,'section':section,'label':label,'unit':unit,'direction':direction,'value':value,'upper_value':upper,'text_value':None,'powertrain':variants[variant],'standard':'WLTP' if 'WLTP' in line else '', 'basis':basis,'period':'current_offering','chunk_id':str(d['id']),'quote':line,'scope_quote':header})
                    seen.add(key)
    if not result:notes.append('No unambiguous technical table for this variant in the internal catalog.')
    return result,list(dict.fromkeys(notes))
