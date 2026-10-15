"""Frozen-page regression for lost facts and shared article templates.

Uses actual local inference on the same original pages. No web/search calls and
no production CRM writes. Development regression, not independent precision.
"""
import json,sqlite3,sys,time,hashlib
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,digest
from sales.research_analysis import document,LocalResearcher
from sales.research_rules import qualify,validate_signals

ROOT=Path(__file__).resolve().parents[1]

def run(report_name='regression50-evidence-origins.json'):
    pointer=json.loads((ROOT/'docs/evidence-origin-baseline.json').read_text())
    baseline=ROOT/pointer['directory'];old=json.loads((baseline/'report.json').read_text())
    for relative,expected in pointer['sha256'].items():
        assert hashlib.sha256((baseline/relative).read_bytes()).hexdigest()==expected,'Baseline changed: '+relative
    raw=json.loads((baseline/'raw-claims.json').read_text())
    dest=ROOT/'data/evidence-origin-replay'/now().replace(':','-');dest.mkdir(parents=True,mode=0o700)
    store=Store(dest/'replay.sqlite3');store.init()
    with closing(sqlite3.connect(baseline/'replay.sqlite3')) as source,store.connect() as target:
        for row in source.execute('SELECT * FROM cache'):target.execute('INSERT OR IGNORE INTO cache VALUES (?,?,?)',row)
    docs=[]
    for previous in raw['documents']:
        page=json.loads((baseline/'pages'/(digest(previous['url'])+'.json')).read_text())
        docs.append(document(page,previous.get('provider','Pagina originale'),previous.get('official',False)))
    target_url='https://www.automazioneveneto.com/online-nuovo-sito-web-aziendale/'
    old_doc=next(d for d in raw['documents'] if d['url']==target_url)
    new_doc=next(d for d in docs if d['url']==target_url)
    retained,errors=validate_signals(raw['proposed'],raw['documents'])
    start=time.monotonic()
    signals,proposal,review,limits=LocalResearcher(store,progress=lambda message:print(message,flush=True)).analyze(old['identity'],docs,old['assessment']['coverage'])
    assessment=qualify(old['identity'],docs,signals,proposal,review,limits=limits)
    report={'checked_at':now(),'baseline':pointer['directory'],'split':'development regression, not independent precision',
        'search_requests':0,'web_requests':0,'seconds':round(time.monotonic()-start,2),
        'unchanged_proposed_claims':len(raw['proposed']),
        'before_retained':len(raw['validated']),'after_retained_same_claims':len(retained),
        'same_claims_errors':errors,
        'target_before':[s for s in raw['validated'] if s['url']==target_url],
        'target_after_dedup_only':[s for s in retained if s['url']==target_url],
        'article_chars_before':len(old_doc['research_text']),'article_chars_after':len(new_doc['research_text']),
        'target_after_real_analysis':[s for s in signals if s['url']==target_url],
        'before_status':old['assessment']['status'],'assessment':assessment,'documents':docs}
    (dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    summary={k:v for k,v in report.items() if k not in ('assessment','documents')}
    summary.update(directory=str(dest.relative_to(ROOT)),status=assessment['status'],why=assessment['why'],limits=limits)
    (ROOT/'docs'/report_name).write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'directory':str(dest.relative_to(ROOT)),'before':len(report['target_before']),
                     'after':len(report['target_after_real_analysis']),'status':assessment['status'],'limits':limits}),flush=True)

if __name__=='__main__':run()
