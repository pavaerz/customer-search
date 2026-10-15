"""Controlled real acquisition sample; paid calls counted in the real ledger.

Business state and page captures stay in an isolated DB. A finite pilot is not a
campaign query limit. No sends, purchases or promotion of snippets.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,domain
from sales.serper_provider import search
from sales.research_store import ResearchStore
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb,resolve_publisher,document
from sales.commercial_planner import hypothesis
from sales.prospect_scope import acquisition_exclusion
from sales.source_identity import source_entities
from sales.providers import blocked
from sales.research_strategies import NOISE

ROOT=Path(__file__).resolve().parents[1]
QUERIES=[
 ('change','lavorazioni meccaniche Veneto nuova linea prodotti 2026 -agenzia'),
 ('change','site:venetoeconomia.it impresa espansione mercati 2026'),
 ('companies','elenco aziende subfornitura meccanica Padova associati'),
]

def run():
    destination=ROOT/'data'/'pilot50'/now().replace(':','-');destination.mkdir(parents=True,mode=0o700)
    real=Store();real.init()
    path=destination/'sample.sqlite3'
    with sqlite3.connect(real.path) as src,sqlite3.connect(path) as dst:src.backup(dst)
    os.chmod(path,0o600)
    store=Store(path);store.init()
    report={'started_at':now(),'queries':[],'candidates':[],'requests':0,'split':'new evaluation sample; not used to author initial rules','limits':['Small sample; triage only. Not a conversion benchmark.']}
    pages={};original_get=ResearchWeb.get
    def capture(web,url,refresh=False):
        page=original_get(web,url,refresh);pages[url]=page;return page
    def save():
        (destination/'pages.json').write_text(json.dumps(pages,ensure_ascii=False))
        (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    filters={'target':'b2b','groups':['direct'],'projects':['website'],'regions':['Veneto']}
    selected=[];seen=set()
    for strategy,q in QUERIES:
        result,cached=search(real,q)
        report['requests']+=not cached
        report['queries'].append({'query':q,'strategy':strategy,'cached':cached,'results':result['results']})
        count=0
        for item in result['results']:
            payload={'url':item['url'],'title':item.get('title',''),'strategy':strategy,'region':'Veneto','filters':filters,'hypothesis':hypothesis(strategy,'Veneto'),'research_intent':'signal' if strategy!='companies' else 'company'}
            reason=('Fonte esclusa dalla policy di accesso' if blocked(item['url']) or NOISE.search(item['url']) else acquisition_exclusion(item,payload))
            if reason:report['candidates'].append({'url':item['url'],'prefilter':reason});continue
            if domain(item['url']) in seen or count>=4:continue
            seen.add(domain(item['url']));count+=1;selected.append(payload)
        save()
    with patch.object(ResearchWeb,'get',capture):
        for payload in selected:
            row={'url':payload['url'],'payload':payload}
            try:
                r=triage(store,payload,lambda:None)
                row['triage']=r
                if r.get('resolve'):
                    page=pages[payload['url']];doc=document(page)
                    row['entities']=source_entities(page,doc)
                    # Real production resolver; it may use the local model, never a paid model.
                    row['resolved']=resolve_publisher(store,page,{**payload,'publisher':True,'directory':r['details'].get('directory',False)},lambda:None)
            except Exception as exc:row['error']=str(exc)[:700]
            report['candidates'].append(row);save()
            print(json.dumps({'url':row['url'],'state':row.get('triage',{}).get('state'),'reason':row.get('triage',{}).get('reason'),'error':row.get('error'),'resolved':len(row.get('resolved',{}).get('discovered',[]))},ensure_ascii=False),flush=True)
    report['finished_at']=now()
    report['summary']={'queries':len(report['queries']),'requests':report['requests'],'pages_captured':len(pages),'sampled':len(selected),'businesses_identified':sum(bool(x.get('triage',{}).get('details',{}).get('company_ready')) for x in report['candidates']),'articles_resolved':sum(bool(x.get('resolved',{}).get('discovered') or x.get('resolved',{}).get('resolve_queries')) for x in report['candidates']),'technical_errors':sum('error' in x for x in report['candidates']),'qualified':None}
    save();(ROOT/'docs/pilot50-latest.json').write_text(json.dumps({'directory':str(destination.relative_to(ROOT)),'summary':report['summary'],'limits':report['limits']},ensure_ascii=False,indent=2))
    print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':run()
