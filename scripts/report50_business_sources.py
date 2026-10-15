"""Rebuild the measured source-discovery report from retained pilot artifacts."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/pilot50-source-mix'
def read(name):return json.loads((DATA/name).read_text())

def report():
    sources=read('source-report.json');replay=read('source-replay.json')
    articles=read('article-replay.json');before=read('plastica-review.json');after=read('plastica-recheck.json')
    pairs=read('paired-results.json');final=read('paired-final-results.json')
    usage=json.loads((ROOT/'docs/preservation50-business-sources.json').read_text())
    report={'split':'development; not an independent commercial precision benchmark',
            'serper_requests':usage['serper_requests_delta'],
            'source_trial':{'attempted':len(sources['sources']),'read':sum(s['status']=='read' for s in sources['sources']),
                            'articles_offered':len(sources['candidates']),'pages_captured':sources['pages_captured'],'serper_requests':0,
                            'frozen_replay_same_candidates':sources['candidates']==replay['candidates'],
                            'currently_enabled_regions':['Veneto','Lombardia','Piemonte'],
                            'deferred_region':'Toscana: all six sampled archive articles dated 2024; other Tuscany discovery remains enabled'},
            'article_review':{'sample':len(articles['rows']),'explicit_body_scoped':sum(bool(r['body_scope']) for r in articles['rows']),
                              'subscription_previews_now_unverifiable':sum(bool(r['access_limit']) for r in articles['rows']),
                              'resolution_routes_before':sum(r['before_resolve'] for r in articles['rows']),
                              'resolution_routes_after':sum(r['after_resolve'] for r in articles['rows'])},
            'queries':[{'region':q['region'],'version':q['version'],'comparison':q.get('comparison','final_same_event'),
                        'returned':len(q['results']),'query':q['query']} for q in pairs+final],
            'company_check':{'name':'Plastica LG','identity':after['investigation']['identity']['identity_status'],
                             'region':after['investigation']['identity']['region'],'documents':len(after['investigation']['documents']),
                             'before':before['investigation']['assessment']['status'],'after':after['investigation']['assessment']['status'],
                             'budget':after['investigation']['assessment']['budget'],
                             'editorial_context_characters_before':len(next(d['research_text'] for d in before['investigation']['documents'] if not d['official'])),
                             'editorial_context_characters_after':len(next(d['research_text'] for d in after['investigation']['documents'] if not d['official']))},
            'qualified_in_completed_company_checks':0,'precision_at_20':None,'commercial_effectiveness_proven':False,
            'limits':['Query variants were developed with this sample. No independent success claim.',
                      'Correcting publisher domains did not increase returned URLs in the two paired queries: both remain empty.',
                      'Final first-query variant returned 10 URLs in Lombardy and zero in Piedmont; URL counts do not establish company relevance.',
                      'The deep company sample is one, not all source articles. A real commercial opportunity has not been established.',
                      'The local model retains the recovered company expansion passage as business context; further reasoning quality remains to be validated.',
                      'No customer was contacted and no pilot prospect was added to the production CRM.']}
    (ROOT/'docs/pilot50-business-sources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'sources':report['source_trial'],'articles':report['article_review'],'company':report['company_check']},ensure_ascii=False))

if __name__=='__main__':report()
