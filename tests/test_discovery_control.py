import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_discovery import seed_campaign, inspect_source
from sales.research_analysis import ResearchWeb
from sales.discovery_control import free_search, health, available, ProviderDeferred, measure, page_read, diagnostics, migrate
from sales.discovery_planner import Planner, query_key
from sales.company_research import selected_strategies
from sales.research_strategies import TEMPLATES


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.store.init()
        self.rs=ResearchStore(self.store);self.c=self.rs.create({'regions':['Veneto']});self.p=Planner(self.rs);self.f=Funnel(self.rs)
    def tearDown(self):self.tmp.cleanup()
    def branch(self):
        with self.store.connect() as c:
            c.execute("INSERT INTO discovery_branches(campaign_id,strategy,region) VALUES (?,'change','Veneto')",(self.c['id'],))
        self.p.tick(self.c)
        return self.query()
    def query(self):
        with self.store.connect() as c:
            r=c.execute("SELECT payload,strategy FROM discovery_frontier WHERE kind='search' ORDER BY id DESC LIMIT 1").fetchone()
        return {'strategy':r['strategy'],'payload':json.loads(r['payload'])}
    def result(self,task,state='rejected',identity=False):
        url='https://alfa.example/event-'+str(task['payload']['page'])
        self.f.transition(self.c,{'url':url,'strategy':'change'},state,'Motivo verificato',{'identity':{'name':'Alfa','website':'https://alfa.example/','identity_status':'verified' if identity else 'unknown'}})
        self.p.observed(self.c,task,[url],1)
    def test_initial_frontier_small_all_strategies(self):
        seed_campaign(self.rs,self.c)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM discovery_queries').fetchone()[0],len(selected_strategies(self.c['filters'])))
            self.assertLessEqual(c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0],20)
        seed_campaign(self.rs,self.c)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM discovery_queries').fetchone()[0],len(selected_strategies(self.c['filters'])))
    def test_canonical_equivalence_preserves_subject_period_and_phrase(self):
        self.assertEqual(query_key({'query':'Veneto ecommerce prodotti'}),query_key({'query':'Prodotti E-commerce Veneto'}))
        self.assertNotEqual(query_key({'query':'"Alfa Beta" Veneto'}),query_key({'query':'"Beta Alfa" Veneto'}))
        self.assertNotEqual(query_key({'query':'Alfa','period':'year'}),query_key({'query':'Alfa','period':''}))
        self.assertNotEqual(query_key({'query':'site:alfa.it prodotti'}),query_key({'query':'site:beta.it prodotti'}))
    def test_no_pagination_before_original_pages(self):
        task=self.branch();self.p.observed(self.c,task,['https://alfa.example/'],1)
        self.assertEqual(self.p.tick(self.c),0)
    def test_noise_changes_hypothesis_without_abandoning_remaining_sectors(self):
        task=self.branch();self.result(task);self.p.tick(self.c)
        second=self.query();self.assertEqual(second['payload']['page'],1)
        self.assertNotEqual(second['payload']['query'],task['payload']['query'])
        self.result(second);self.p.tick(self.c)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT state FROM discovery_branches').fetchone()[0],'active')
        third=self.query();self.assertEqual(third['payload']['page'],1)
        self.assertNotIn(third['payload']['query'],[task['payload']['query'],second['payload']['query']])
    def test_useful_original_unlocks_pagination(self):
        task=self.branch();self.result(task,'promising',True);self.p.tick(self.c)
        self.assertEqual(self.query()['payload']['page'],2)
    def test_one_verified_contact_is_productive_even_among_nine_rejections(self):
        task=self.branch();urls=[]
        for n in range(10):
            url=f'https://company{n}.example/jobs';urls.append(url)
            details={'identity':{'website':f'https://company{n}.example/','identity_status':'verified','contacts':[{'type':'email','value':f'info@company{n}.example'}]}}
            if n==0:details['collaboration']={'url':url,'quote':'Cerchiamo WordPress freelance.','checked_at':now()}
            self.f.transition(self.c,{'url':url,'strategy':'change'},'promising' if n==0 else 'rejected','Originale verificato',details)
        self.p.observed(self.c,task,urls,len(urls));self.p.tick(self.c)
        self.assertEqual(self.query()['payload']['page'],2)
        self.assertEqual(self.rs.campaign(self.c['id'])['qualified'],0)
    def test_portal_is_productive_only_after_company_resolution(self):
        task=self.branch();root=task['payload']['query_key'];url='https://news.example/alfa'
        self.f.transition(self.c,{'url':url,'strategy':'change','root_query_key':root},'needs_review','Editore da risolvere',{'publisher':True})
        self.p.observed(self.c,task,[url],1)
        child={'url':'https://alfa.example/','strategy':'change','root_query_key':root}
        self.f.offer(self.c['id'],'candidate','change',child,'resolved-child')
        self.assertEqual(self.p.tick(self.c),0)
        self.f.transition(self.c,child,'needs_review','Impresa identificata, bisogno da verificare',{'company_ready':True,'identity':{'name':'Alfa','website':child['url'],'identity_status':'verified'}})
        with self.store.connect() as c:c.execute("UPDATE discovery_frontier SET state='done' WHERE fingerprint='resolved-child'")
        self.p.tick(self.c)
        self.assertEqual(self.query()['payload']['page'],2)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT decision FROM discovery_queries WHERE fingerprint=?',(root,)).fetchone()[0],'productive')
            self.assertEqual(c.execute("SELECT count(*) FROM discovery_candidates WHERE state='qualified'").fetchone()[0],0)
    def test_unrelated_company_does_not_make_portal_productive(self):
        task=self.branch();root=task['payload']['query_key'];url='https://news.example/alfa'
        self.f.transition(self.c,{'url':url,'strategy':'change','root_query_key':root},'needs_review','Editore senza soggetto',{'publisher':True})
        self.p.observed(self.c,task,[url],1)
        self.f.transition(self.c,{'url':'https://beta.example/','root_query_key':'other'},'promising','Altra ricerca',{'company_ready':True})
        self.p.tick(self.c)
        self.assertEqual(self.query()['payload']['page'],1)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT decision FROM discovery_queries WHERE fingerprint=?',(root,)).fetchone()[0],'dry')
    def test_inaccessible_is_not_commercial_rejection(self):
        task=self.branch();self.result(task,'unverifiable');self.p.tick(self.c)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT decision FROM discovery_queries').fetchone()[0],'technical')
            self.assertEqual(c.execute('SELECT dry_streak FROM discovery_branches').fetchone()[0],0)
    def test_provider_circuit_persists_and_recovers(self):
        calls=[]
        def fail():calls.append(1);return {'results':[],'unresponsive_engines':[['duckduckgo','CAPTCHA']]}
        with self.assertRaises(ValueError):free_search(self.store,fail)
        with self.assertRaises(ProviderDeferred):free_search(self.store,fail)
        self.assertEqual(len(calls),1);self.assertEqual(health(self.store)['failures'],1)
        with self.store.connect() as c:c.execute("UPDATE discovery_provider_health SET retry_at='2000-01-01'")
        self.assertEqual(free_search(self.store,lambda:{'results':[]}),{'results':[]})
        self.assertTrue(available(self.store));self.assertEqual(health(self.store)['failures'],0)
    def test_paid_credentials_never_trigger_paid_calls(self):
        with patch.dict('os.environ',{'TAVILY_API_KEY':'test','SERPER_API_KEY':'test'}):
            d=diagnostics(self.rs,self.c['id'])
            self.assertTrue(all(not v['enabled'] and v['max_spend_eur']==0 for v in d['paid'].values()))
    def test_stop_no_query_promotion(self):
        self.rs.stop(self.c['id'])
        self.assertIsNone(self.p.offer_query(self.c,'change',{'query':'nuova linea Veneto'}))
    def test_measured_errors_empty_and_cache_distinct(self):
        task={'id':1,'strategy':'change','kind':'search','payload':{'query':'test'}}
        with measure(self.rs,self.c,task):
            page_read({'status':200,'url':'https://a.example','cached':False})
            page_read({'status':200,'url':'https://a.example','cached':False})
            page_read({'status':200,'url':'https://b.example','cached':True})
        with self.assertRaises(ValueError),measure(self.rs,self.c,task):raise ValueError('errore test')
        d=diagnostics(self.rs,self.c['id'])['providers'][0]
        self.assertEqual((d['queries'],d['pages'],d['cached_pages'],d['errors']),(2,1,1,1))
    def test_source_relative_feed_link_independent_of_search(self):
        page={'url':'https://territorio.example/feed','status':200,'checked_at':now(),'html':'<?xml version="1.0"?><rss><channel><item><title>Nuova linea prodotti</title><link>/nuova-linea-alfa</link></item></channel></rss>'}
        with patch.object(ResearchWeb,'get',return_value=page):inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'rss'}},lambda:None)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0],0)
    def test_legacy_adoption_keeps_candidates_and_identity_queries(self):
        self.rs.enqueue(self.c['id'],'search','change',{'query':'"nuova linea" "prodotti" Veneto produzione alimentare','page':1})
        self.rs.enqueue(self.c['id'],'search','change',{'query':'Alfa','page':1,'subject':'Alfa','company_stage':'identify'})
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://alfa.example/','company_host':'alfa.example'})
        self.rs.enqueue(self.c['id'],'search','change',{'query':'Ricerca manuale da conservare','page':1})
        self.p.adopt(self.c)
        with self.store.connect() as c:
            rows=c.execute('SELECT kind,state,payload FROM research_tasks').fetchall()
            self.assertEqual(rows[0]['state'],'superseded');self.assertEqual(rows[1]['state'],'pending');self.assertEqual(rows[2]['state'],'pending');self.assertEqual(rows[3]['state'],'superseded')
        self.p.adopt(self.c)
    def test_followup_uses_observed_verified_company_and_stops_depth(self):
        result={'state':'promising','details':{'identity':{'identity_status':'verified','website':'https://alfa.example/','name':'Alfa','region':'Veneto'},'document':{'text':'Alfa presenta una nuova linea di prodotti.','url':'https://alfa.example/news'}}}
        self.p.follow_company(self.c,{'strategy':'change'},result)
        self.assertIn('site:alfa.example',self.query()['payload']['query'])
        self.p.follow_company(self.c,{'strategy':'change','followup_depth':1},result)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM discovery_queries').fetchone()[0],1)
    def test_resume_retires_generalist_branches(self):
        with self.store.connect() as c:
            c.execute("INSERT INTO discovery_branches(campaign_id,strategy,region,state,reason) VALUES (?,'change','Veneto','paused','Due formulazioni senza riscontri pertinenti nelle pagine originali.')",(self.c['id'],))
            c.execute("INSERT INTO discovery_branches(campaign_id,strategy,region,state,reason) VALUES (?,'process','Veneto','paused','Fonti non verificabili')",(self.c['id'],))
        self.p.adopt(self.c)
        with self.store.connect() as c:states=dict(c.execute('SELECT strategy,state FROM discovery_branches'))
        self.assertEqual(states['change'],'retired')
        self.assertEqual(states['process'],'retired')  # Generic discovery removed; company checks stay available.
        self.assertEqual({s for s,state in states.items() if state=='active'},set(selected_strategies(self.c['filters'])))
        self.assertEqual(states['companies'],'active')
    def test_migration_repeatable_preserves_rows(self):
        seed_campaign(self.rs,self.c);migrate(self.store);migrate(self.store)
        with self.store.connect() as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(c.execute('SELECT count(*) FROM campaigns').fetchone()[0],1)

    def test_trade_association_article_is_not_a_company(self):
        from sales.research_triage import triage
        page={'url':'https://www.confartigianatovicenza.it/articolo/','status':200,'checked_at':now(),'html':'<title>Confartigianato Imprese Vicenza</title><main>Novità sulle trasferte internazionali per le imprese.</main>'}
        with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.store,{'url':page['url'],'strategy':'change'},lambda:None)
        self.assertTrue(r['details']['publisher']);self.assertNotEqual(r['state'],'promising')
    def test_oversized_index_can_offer_declared_sitemap_but_block_cannot(self):
        from urllib.robotparser import RobotFileParser
        rules=RobotFileParser();rules.parse(['User-agent: *','Allow: /','Sitemap: https://territorio.example/news.xml'])
        for error,expected in [('Pagina oltre 1,5 MB: controllo non completato',1),('Accesso escluso da robots.txt',0)]:
            with self.store.connect() as c:c.execute('DELETE FROM discovery_frontier')
            with patch('sales.research_discovery.ResearchWeb') as cls:
                cls.return_value.get.side_effect=ValueError(error);cls.return_value.rules={'https://territorio.example':rules}
                with self.assertRaises(ValueError):inspect_source(self.rs,self.c,{'payload':{'url':'https://territorio.example/news','kind':'html'}},lambda:None)
            with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0],expected)
    def test_rss_summary_routes_discovery_but_is_not_evidence(self):
        page={'url':'https://territorio.example/feed','status':200,'checked_at':now(),'html':'<rss><channel><item><title>Alfa si rinnova</title><link>https://alfa.example/news</link><description>Alfa presenta una nuova linea di prodotti.</description></item></channel></rss>'}
        with patch.object(ResearchWeb,'get',return_value=page):inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'rss'}},lambda:None)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM research_assessments').fetchone()[0],0)
    def test_no_pagination_for_engine_without_support(self):
        task=self.branch();self.result(task,'promising',True)
        with self.store.connect() as c:c.execute('UPDATE discovery_queries SET can_page=0')
        self.p.tick(self.c);self.assertEqual(self.query()['payload']['page'],1)
    def test_local_capabilities_cached_and_paid_not_consulted(self):
        from sales.discovery_control import search_capabilities
        data={'engines':[{'name':'bing','enabled':True,'categories':['general'],'paging':False,'time_range_support':False},{'name':'google','enabled':False,'categories':['general'],'paging':True}]}
        with patch('sales.providers.api_json',return_value=data) as api:
            r=search_capabilities(self.store,'http://127.0.0.1:8888');search_capabilities(self.store,'http://127.0.0.1:8888')
        self.assertFalse(r['paging']);self.assertFalse(r['time_range']);self.assertEqual(api.call_count,1)
        with self.assertRaises(ValueError):search_capabilities(self.store,'https://external.example')

    def test_old_generic_award_notice_is_not_a_company_directory(self):
        from sales.research_triage import triage
        page={'url':'https://cnaveneto.it/premio/','status':200,'checked_at':now(),'html':'<title>CNA Veneto premio startup</title><meta property="article:published_time" content="2024-01-01"><main>Startup: iscrizioni al premio aperte. <a href="https://premiocambiamenti.it/">Iscriviti</a></main>'}
        with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.store,{'url':page['url'],'strategy':'startup','publisher':True},lambda:None)
        self.assertFalse(r.get('resolve'));self.assertNotEqual(r['state'],'promising')
    def test_old_named_directory_still_resolves_without_dating_need(self):
        from sales.research_triage import triage
        page={'url':'https://cnaveneto.it/startup-finaliste/','status':200,'checked_at':now(),'html':'<title>CNA Veneto startup finaliste</title><meta property="article:published_time" content="2024-01-01"><main>Le startup finaliste: <a href="https://alfa.example/">Alfa</a>, prodotti innovativi.</main>'}
        with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.store,{'url':page['url'],'strategy':'startup','publisher':True},lambda:None)
        self.assertTrue(r.get('resolve'));self.assertEqual(r['state'],'needs_review')
