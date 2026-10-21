"""Frozen campaign-15 replay. No providers, browsers, real DB or external calls."""
import copy,gzip,json,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
from sales.db import Store
from sales.commercial.discovery import assess,followup_allowed
from sales.commercial.indexed_jobs import parse_indexed_job,resolution
from sales.commercial.inspection import inspect
from sales.commercial.rebuild import evaluate as rebuild_evaluate

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/commercial3b'

def load(name):
    with gzip.open(FIXTURE/name,'rt',encoding='utf8') as f:return json.load(f)

def main():
    data=load('campaign15.json.gz');documents=load('campaign15-pages.json.gz');pages=documents['pages']
    states=lambda rows:{state:sum(r['state']==state for r in rows) for state in ('VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE')}
    original=[r['body'] for r in sorted(data['commercial_revisions'],key=lambda r:r['id'])]
    results=[];read_urls=[]
    def read(web,url):
        # Missing saved data is NOT a simulated 404 or a fresh browser result.
        if url not in pages:raise LookupError('Originale non presente nella fixture: '+url)
        read_urls.append(url);return copy.deepcopy(pages[url])
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'replay.sqlite3');store.init()
        for rev in sorted(data['commercial_revisions'],key=lambda r:r['id']):
            b=rev['body'];after=copy.deepcopy(b);scope='saved_incomplete_retained';limit=None
            if b.get('social'):
                scope='saved_social_hint_retained'
                if b['social']['source']=='linkedin':
                    after['social']['indexed_job']=parse_indexed_job(b['discovery'])
                    after['social']['resolution_plan']=resolution(b['discovery'])
            elif b['engine']=='WEBSITE_REBUILD' and b.get('screening'):
                source=[pages[url] for url in dict.fromkeys([b['website'],b['url']]) if url in pages]
                if source:
                    after=rebuild_evaluate(b['identity'],source,b['geography'],copy.deepcopy(b['screening']),copy.deepcopy(b.get('browser')))
                    scope='saved_screening_and_browser_requalified_no_remeasurement'
            elif b['url'] in pages:
                try:
                    with patch('sales.commercial.inspection.ResearchWeb.get',read),patch('sales.commercial.browser.review',side_effect=AssertionError('Browser forbidden in saved-evidence replay')):
                        found=inspect(store,{'url':b['url'],'commercial_engine':b['engine'],'allowed_regions':b.get('policy',{}).get('scope',{}).get('regions'),'max_reads':6})
                    after=found['result'];scope='original_saved_html_inspection'
                except LookupError as exc:limit=str(exc);scope='not_replayed_missing_original'
            results.append({'revision':rev['id'],'engine':b['engine'],'url':b['url'],'scope':scope,'limit':limit,
                            'before':{'state':b['state'],'score':b['score'],'reason':b['reason']},
                            'after':{'state':after['state'],'score':after['score'],'reason':after['reason'],
                                     'commercial_intent':after.get('commercial_intent'),'verification':after.get('verification'),
                                     'evidence':after.get('evidence'),'browser_outcome':after.get('browser_outcome'),
                                     'social':after.get('social'),'limits':after.get('limits'),'partner_hint':after.get('partner_hint')},
                            'parent_result':after})
    direct=[];follow=[]
    for row in data['commercial_discovery']:
        b=row['body'];origin=b.get('origin',{});decision=assess(b,row['engine'],origin)
        summary={'id':row['id'],'engine':row['engine'],'url':row['url'],'before':row['decision'],'after_filter':decision['decision'],'reason':decision['reason']}
        if origin.get('parent_task'):
            parent=next((r['parent_result'] for r in results if r['engine']==row['engine'] and r['url']==origin['parent']),{})
            summary['parent_path_allowed']=followup_allowed(parent,origin);follow.append(summary)
        else:direct.append(summary)
    for row in results:row.pop('parent_result')
    k=next(r for r in results if r['revision']==757)
    assert k['scope']=='original_saved_html_inspection',k
    assert k['after']['state']!='VERIFIED',k
    assert k['after']['commercial_intent']['commercial_role'] in ('SELLER','PARTNERSHIP_SELLER'),k
    assert all(not r['parent_path_allowed'] for r in follow)
    assert all(next(r for r in results if r['revision']==n)['after']['social']['resolution_plan'] for n in (768,))
    assert next(r for r in results if r['revision']==755)['after']['state']=='UNVERIFIABLE'
    assert next(r for r in results if r['revision']==770)['after']['social']['resolution_plan'] is None
    diego=next(r for r in results if r['revision']==760)
    assert diego['after']['state']=='REJECTED' and diego['after']['partner_hint']['current_open_request'] is False
    report={
        'scope':'A: replay of saved original HTML/evidence only. No real campaigns or browser remeasurement. B synthetic queue and C local browser tests are reported separately.',
        'fixtures':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.glob('*.gz')},
        'historical':{'campaign_id':15,'states':states(original),'correct_verified_in_reviewed_positive_sample':0,'label_provenance':'HISTORICAL_SYSTEM_LABEL; known issue judgments from campaign15 report, not independent ground truth','false_verified_in_reviewed_positive_sample':0,
                      'reviewed_positive_sample':0,'browser_completed':0,'browser_partial':2,'browser_failure_codes':['rendering_timeout','rendering_timeout'],
                      'candidate_tasks_budget':1,'resources':data['commercial_resources']},
        'replay':{'states':states([r['after'] for r in results]),'scopes':{s:sum(r['scope']==s for r in results) for s in sorted({r['scope'] for r in results})},
                  'kforge_verified':k['after']['state']=='VERIFIED','kforge_commercial_role':k['after']['commercial_intent']['commercial_role'],
                  'diegohelp_current_request':False,'diegohelp_partner_hint_retained':bool(diego['after']['partner_hint']),
                  'new_verified_confirmed':0,'external_calls':0,'api_credits':0,'browser_runs':0,'saved_html_reads':len(read_urls),
                  'linkedin_parsed_and_resolution_planned':1,'incompatible_linkedin_resolution_avoided':1,'linkedin_resolutions_executed':0,'instagram_verdurazon_retained':True,
                  'direct_preflight_admitted':sum(r['after_filter']=='admit' for r in direct),
                  'seller_intent_excluded':sum(r['reason'] in ('seller_intent','service_seller') for r in direct),
                  'followups_allowed':sum(r['parent_path_allowed'] for r in follow),
                  'original_pending_tasks_completed':0,'pending_tasks_http_completability':'Unknown without saved HTTP evidence; synthetic queue test proves unrelated tasks continue.',
                  'real_browser_completed_after':'Not measured; original partial evidence remains partial.'},
        'decisions':results,'discovery':direct,'followups':follow,
        'limits':['Not a market precision or conversion estimate. Historical rows unchanged.',
                  'No missing page replaced with fabricated HTTP response. Saved unverified cases retain uncertainty.',
                  'Publication/contract absent in indexed sources remain unknown.',
                  'Past browser resources/timeouts are not fixed by replay. Local browser tests are separate.',
                  'Historical browser-deferred task is not rewritten; HTTP evidence stays saved.']}
    output=ROOT/'implementation-report/phase-3b-replay.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['replay'],ensure_ascii=False,indent=2));print(output)

if __name__=='__main__':main()
