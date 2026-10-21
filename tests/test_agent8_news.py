"""Synthetic full news pipeline. No real prospects or external calls."""
import copy,json,unittest
from unittest.mock import patch
import test_agent6_campaign32 as support
from test_agent8_proactive import pages,browser,ROOT
from sales.agent6 import schema,news,news_review,commercial_policy
from sales.agent6.api import preview
from sales.agent6.worklist import listing
from sales.commercial.coordinator import run_campaign

ARTICLE='https://press.example/alfa-linea'
SIGNAL='Alfa Srl lancia una nuova linea di macchinari industriali per il mercato italiano.'


class NewsCycle(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp();self.store=self.base.store;self.rs=self.base.rs
        self.rs.stop(self.base.c['id']);self.rs.paused(self.base.c['id'])
        f=copy.deepcopy(self.base.filters);f['commercial_engines']=['NEWS'];f['work_budget']['max_reads']=6
        f['deep_plan_token']=preview(self.store,f)['approval_token'];self.c=self.rs.create(f)
        self.pages=pages();self.calls=[];self.reads=[];self.searches=[];self.defects=True
        self.pages[ARTICLE]={'url':ARTICLE,'status':200,'checked_at':'2026-10-19T12:00:00+00:00',
            'html':'<title>Alfa Srl, nuova linea di macchinari</title><meta property="article:published_time" content="2026-10-18">'
                '<h1>Notizie territoriali</h1><p>Alfa Srl</p><p>'+SIGNAL+'</p><a href="'+ROOT+'">Alfa Srl</a>'}
    def tearDown(self):self.base.tearDown()
    def model(self,p,cfg,check):
        self.calls.append(p)
        if p['task']==schema.PLAN:
            q=support.query('azienda nuova linea prodotti Veneto');q['strategy']='new_product_line'
            q['hypothesis']='Verificare impresa, evento e lacuna pertinente nel sito; non presume domanda.'
            return {'output':{'decision':'search' if not p['round'] else 'stop','queries':[q] if not p['round'] else [],'reason':'Fixture news plan'},'usage':{}}
        if p['task']==news_review.TASK:
            return {'output':{'decision':'COMPLETE_PROJECT','observation_ids':[o['id'] for o in p['observations']],
                'business_fact_ids':[f['id'] for f in p['business_facts']],
                'reason':'Ipotesi da discutere: la nuova offerta non è raggiungibile attraverso il catalogo e il percorso di richiesta.',
                'scope':'Riprogettazione dei percorsi prodotti e contatto, compreso mobile.',
                'why_not_small_fix':'I percorsi interrotti e la struttura mobile richiedono una revisione coordinata; una pagina aggiunta non collega il catalogo al contatto.',
                'objections':['Priorità e budget restano sconosciuti.'],'unknowns':[],
                'event_ids':[p['events'][0]['id']],'event_relation':'Nuova linea di macchinari e percorso prodotti/catalogo non raggiungibile nel campione.',
                'existing_solution_check':'Le pagine campionate non offrono un percorso catalogo e richiesta funzionante; nessuna disponibilità di acquisto presunta.'},'usage':{}}
        analyses=[]
        for rid in p['result_ids']:
            spans=[s for e in p['evidence'] if e['result_id']==rid for s in e['segments']]
            facts=[]
            for field,text in [('entity','Alfa Srl'),('signal',SIGNAL)]:
                segment=next((s for s in spans if s['text']==text),None)
                if segment:facts.append({'field':field,'ref':{'segment_id':segment['segment_id']}})
            analyses.append({'result_id':rid,'kind':'COMPANY_SIGNAL','kind_ref':facts[-1]['ref'],'facts':facts,
                'hypothesis':'Evento aziendale, identità e conseguenze digitali da verificare.','missing':[]})
        return {'output':{'analyses':analyses},'usage':{}}
    def run_case(self):
        def search(store,p,check):
            self.searches.append(p)
            if p.get('news_context'):return [{'url':ROOT,'title':'Alfa Srl','content':'Produzione macchinari industriali.'}]
            return [{'url':ARTICLE,'title':'Alfa Srl','content':SIGNAL}]
        def read(url):self.reads.append(url);return self.pages[url]
        with patch('socket.create_connection',side_effect=AssertionError('No network')),patch('sales.agent6.ai.infer',side_effect=self.model),patch('sales.agent6.coordinator.acquire',side_effect=search),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=read),patch('sales.commercial.browser.review',side_effect=lambda store,p,*a,**kw:browser(p,self.defects)):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:return [json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(self.c['id'],))]

    def test_event_without_web_request_reaches_correct_company_and_audit(self):
        records=self.run_case();audits=[r for r in records if r.get('website_audit')]
        self.assertEqual(len(audits),1,[(r['state'],r['reason']) for r in records]);b=audits[0]
        self.assertEqual(b['state'],'POTENTIAL',b['reason']);self.assertEqual(b['entity_name'],'Alfa Srl')
        self.assertEqual(b['official_domain'],ROOT);self.assertFalse(b['explicit_demand'])
        self.assertEqual(b['budget']['kind'],'UNKNOWN');self.assertIsNone(b['news_correlation']['event_date'])
        self.assertEqual(b['news_correlation']['status'],'EVENT_AND_SITE_CORRELATED')
        self.assertTrue(any(f['field']=='signal' and f['url']==ARTICLE for f in b['facts']))
        self.assertTrue(all('press.example' not in c['value'] for c in b['contacts']))
        self.assertEqual(sum(p['task']==news_review.TASK for p in self.calls),1)
        self.assertEqual(listing(self.store,{'view':'ready','group':'company'})['total'],1)

    def test_no_website_gap_does_not_turn_news_into_opportunity(self):
        for path in ('catalogo','preventivo'):self.pages[ROOT+path]['status']=200
        self.defects=False;records=self.run_case()
        self.assertFalse(any(r['state'] in ('POTENTIAL','VERIFIED') for r in records))
        self.assertFalse(any(p['task']==news_review.TASK for p in self.calls))

    def test_old_article_still_identifies_company_but_is_not_current_demand(self):
        self.pages[ARTICLE]['html']=self.pages[ARTICLE]['html'].replace('2026-10-18','2023-10-18')
        records=self.run_case();b=next(r for r in records if r.get('website_audit'))
        self.assertTrue(b['identity_verified']);self.assertEqual(b['state'],'NEEDS_REVIEW')
        self.assertFalse(b['news_correlation']['event_current'])
        self.assertFalse(any(p['task']==news_review.TASK for p in self.calls))

    def test_missing_official_link_uses_attributed_company_resolution(self):
        self.pages[ARTICLE]['html']=self.pages[ARTICLE]['html'].replace('<a href="'+ROOT+'">Alfa Srl</a>','')
        records=self.run_case()
        self.assertTrue(any(p.get('news_context') and '"Alfa Srl"' in p['query'] for p in self.searches))
        self.assertTrue(any(r['state']=='POTENTIAL' for r in records))

    def test_wrong_official_company_is_not_linked_to_event(self):
        for page in self.pages.values():
            if page['url']!=ARTICLE:page['html']=page['html'].replace('Alfa Srl','Beta Srl')
        records=self.run_case();b=next(r for r in records if r.get('website_audit'))
        self.assertEqual(b['state'],'REJECTED');self.assertFalse(b['news_correlation']['identity_linked'])
        self.assertFalse(any(f['field']=='signal' for f in b['facts']))
        self.assertFalse(any(p['task']==news_review.TASK for p in self.calls))

    def test_event_query_requires_concrete_change_and_verification_hypothesis(self):
        q=support.query('azienda nuova linea prodotti Veneto');q['hypothesis']='Verificare un gap nel sito ufficiale.'
        self.assertTrue(commercial_policy.assess_query(q,'NEWS')['allowed'])
        for text in ('statistiche espansione imprese Veneto','agenzia portfolio rebranding Veneto','aziende Veneto siti web'):
            self.assertFalse(commercial_policy.assess_query({**q,'query':text},'NEWS')['allowed'])
        self.assertFalse(news.direction({'flow':'NEWS','kind':'COMPANY_SIGNAL','state':'DISCOVERED','entity_name':'Alfa Srl',
            'facts':[{'field':'entity','quote':'Alfa Srl'},{'field':'signal','quote':'Le imprese venete investono nel digitale.'}]}))

    def test_invalid_event_reference_cannot_pass_ai_validation(self):
        payload={'observations':[],'business_facts':[],'events':[{'id':'e1'}],'event_current':True}
        value={'decision':'NEEDS_REVIEW','observation_ids':[],'business_fact_ids':[],'reason':'unknown','scope':'',
            'why_not_small_fix':'','objections':[],'unknowns':['scope'],'event_ids':['invented'],'event_relation':'','existing_solution_check':''}
        with self.assertRaisesRegex(ValueError,'unknown_news_event'):news_review.validate(value,payload)


if __name__=='__main__':unittest.main()
