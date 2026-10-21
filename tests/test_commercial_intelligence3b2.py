"""3B.2 historical replay plus explicitly synthetic adversarial cases, offline."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.commercial.discovery import assess
from sales.commercial.ai_schema import evidence_bundle,unknown_output,validate_output,fingerprint
from sales.commercial.ai_diagnostics import diagnose
from sales.commercial.evidence import select
from sales.commercial.intent import classify_block
from sales.commercial.context import extract
from sales.commercial.indexed_jobs import parse_indexed_job
from scripts.replay_commercial3b2 import replay,load,FIXTURE

class HistoricalIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.replays={c:replay(c) for c in (15,16,19)}
    def revision(self,c,host):return next(r for r in self.replays[c]['revisions'] if host in r['url'])
    def test_grandup_original_section_attribution(self):
        r=self.revision(19,'grandup');self.assertEqual(r['scope'],'original_html_qualification')
        a=r['after'];self.assertEqual(a['company'],'DeBlog Brothers');self.assertNotIn(a['state'],('VERIFIED','POTENTIAL'))
        self.assertEqual(a['compensation']['type'],'undisclosed');self.assertNotEqual(a['contract'],'founder')
        quotes='\n'.join(e['text'] for e in r['selected_evidence'])
        self.assertIn('nuovi sviluppatori',quotes);self.assertNotIn('Walden',quotes)
        self.assertNotIn('gestione forestale',quotes);self.assertTrue(r['bundle']['decisive_evidence_preserved'])
    def test_incomedia_industry_does_not_make_social_manager_web_request(self):
        items=[d for d in self.replays[19]['discovery'] if 'DY2PWFuDIPi' in d['url']]
        self.assertTrue(items);self.assertTrue(all(d['after']=='exclude' for d in items))
    def test_intest_index_does_not_prove_currentness(self):
        r=self.revision(19,'DbdZEKfxjaN');self.assertIsNone(r['after']['state'])
        self.assertEqual(r['scope'],'index_hint_only_no_currentness_verification')
    def test_wikipedia_removed_before_http(self):
        items=[d for d in self.replays[19]['discovery'] if 'wikipedia' in d['url']]
        self.assertTrue(items);self.assertTrue(all(d['after']=='exclude' for d in items))
    def test_bmb_partial_stays_partial(self):
        r=self.revision(19,'bmb');self.assertFalse(r['technical_context']['browser_completed'])
        self.assertFalse(r['browser']['remeasured']);self.assertIsNone(r['after']['state'])
        self.assertTrue(r['selected_evidence']);self.assertEqual(r['bundle']['boilerplate_ratio'],0)
    def test_sunnit_fullstack_hint_not_wrongly_discarded(self):
        d=next(d for d in self.replays[19]['discovery'] if 'sunnit' in d['url'].lower())
        self.assertEqual(d['after'],'admit')
    def test_kforge_remains_seller(self):
        r=self.revision(15,'kforge');self.assertEqual(r['after']['classification'],'seller');self.assertEqual(r['after']['state'],'REJECTED')
    def test_diegohelp_article_not_direct_demand(self):
        r=self.revision(15,'diegohelp');self.assertEqual(r['preflight'],'exclude')
    def test_hosted_project_never_merges_with_publisher_entity(self):
        import tempfile
        from sales.db import Store
        from sales.research_store import ResearchStore
        from sales.commercial.attribution import requesting_identity
        r=self.revision(19,'grandup')['after']
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.sqlite3');store.init();repo=ResearchStore(store)
            publisher={'name':'GrandUP!','website':'https://grandup.org','identity_status':'verified'}
            owner=repo.entity(publisher)
            project=requesting_identity(publisher,{'requesting_actor':r['company'],'actor_attribution':r['actor_attribution']},'https://grandup.org/projects')
            child=repo.entity(project)
            self.assertNotEqual(owner,child);self.assertIsNone(project['website']);self.assertFalse(project['contacts'])
            with store.connect() as c:
                self.assertEqual(c.execute('SELECT name FROM research_entities WHERE id=?',(owner,)).fetchone()[0],'GrandUP!')

    def test_euspert_not_tech_stack(self):
        data=load(FIXTURE/'campaign16.json.gz')
        b=next(r['body'] for r in data['commercial_revisions'] if 'euspert' in str(r).lower())
        h=parse_indexed_job(b['discovery']);self.assertNotEqual(h['company_candidate'],'Go python AWS Remote')
    def test_federlegno_portal_not_rebuild_company(self):
        ds=[d for d in self.replays[16]['discovery'] if 'federlegno' in d['url']]
        self.assertTrue(ds);self.assertTrue(all(d['after']=='exclude' for d in ds))

class SyntheticIntelligenceTests(unittest.TestCase):
    """Synthetic examples, not historical outcomes or market precision."""
    def test_late_request_beats_navigation_and_homepage(self):
        docs=[{'id':'home','url':'https://example.it/','text':'Home\nMenu\nCookie\n'*100},
              {'id':'jobs','url':'https://example.it/jobs','text':'Cerchiamo uno sviluppatore WordPress freelance per un progetto web completo.'}]
        e,m=select(1,docs,500);self.assertEqual(len(e),1);self.assertIn('Cerchiamo',e[0]['text']);self.assertEqual(m['boilerplate_ratio'],0)
    def test_whole_request_never_silently_cut(self):
        e,m=select(1,[{'url':'https://example.it','text':'Cerchiamo sviluppatori WordPress '+('dettagli '*1000)}],100)
        self.assertFalse(e);self.assertFalse(m['decisive_evidence_preserved']);self.assertEqual(m['status'],'EVIDENCE_INSUFFICIENT')
    def test_duplicate_and_counterevidence(self):
        t='Cerchiamo freelance WordPress.\nAnnuncio scaduto il 2025-01-01.'
        e,m=select(1,[{'url':'https://example.it','text':t},{'url':'https://copy.it','text':t}],1000)
        self.assertEqual(len(e),2);self.assertEqual(m['discard_reasons']['duplicate'],2);self.assertTrue(any('counterevidence' in x['roles'] for x in e))
    def test_publisher_and_project_not_interchangeable(self):
        e=evidence_bundle(1,[{'url':'https://host.it','text':'Beta cerca sviluppatori WordPress freelance. Host presenta Beta.'}])
        o=unknown_output({'candidate_id':'1'});o.update(actor='Host',commercial_intent='BUYER_INTENT',direction='BUYER',supporting_evidence=[{'id':e[0]['id'],'quote':e[0]['text']}])
        r={'actor_attribution':{'requesting_actor':'Beta'}}
        self.assertEqual(diagnose(o,1,e,r)['code'],'ACTOR_ATTRIBUTION_CONFLICT')
    def test_temporal_menu_quote_rejected_without_current_claim(self):
        e=evidence_bundle(1,[{'url':'https://example.it','text':'Alfa software house'}]);o=unknown_output({'candidate_id':'1'})
        o['temporal_evidence']=[{'id':e[0]['id'],'quote':e[0]['text']}]
        self.assertEqual(diagnose(o,1,e,{})['code'],'EVIDENCE_ROLE_MISMATCH')
    def test_invalid_output_diagnostics_never_retain_claim_or_credentials(self):
        o={'actor':'SECRET credential arbitrary private data'}
        d=diagnose(o,1,[],{});self.assertEqual(d['code'],'SCHEMA_INVALID');self.assertNotIn('SECRET',json.dumps(d))
    def test_indexed_request_cannot_be_current(self):
        e=evidence_bundle(1,[{'url':'https://instagram.com/p/x','text':'Alfa cerchiamo WordPress freelance','acquisition':'search_index'}])
        o=unknown_output({'candidate_id':'1'});o.update(source_type='social_indexed',commercial_intent='FREELANCE_OPPORTUNITY',direction='BUYER',relationship_type='CURRENT_OPEN_REQUEST',supporting_evidence=[{'id':e[0]['id'],'quote':e[0]['text']}])
        self.assertEqual(diagnose(o,1,e,{})['code'],'TEMPORAL_STATUS_UNVERIFIED')
    def test_agency_direction_and_non_digital_agency(self):
        r=assess({'url':'https://example.it/','title':'Agenzia per il lavoro','content':'Cerchiamo sviluppatori freelance'},'AGENCIES')
        self.assertEqual(r['reason'],'non_digital_agency')
        self.assertNotEqual(classify_block('Diventa partner. Affidaci lo sviluppo WordPress.')['commercial_role'],'PARTNERSHIP_BUYER')
    def test_family_feedback_requires_sample_and_never_disables(self):
        import sqlite3
        from sales.commercial.planner import family_history
        c=sqlite3.connect(':memory:');self.addCleanup(c.close);c.row_factory=sqlite3.Row
        c.executescript('CREATE TABLE research_tasks(campaign_id,strategy,kind,state,payload); CREATE TABLE commercial_discovery(campaign_id,engine,query,decision); CREATE TABLE commercial_revisions(id,opportunity_id,campaign_id,body);')
        for campaign in (1,2,3):
            c.execute('INSERT INTO research_tasks VALUES(?,?,?,?,?)',(campaign,'FREELANCE','search','done',json.dumps({'family':'poor','query':str(campaign)})))
            for _ in range(10):c.execute('INSERT INTO commercial_discovery VALUES(?,?,?,?)',(campaign,'FREELANCE',str(campaign),'exclude'))
        small=family_history(c,'FREELANCE',3)['poor'];large=family_history(c,'FREELANCE',4)['poor']
        self.assertFalse(small['sample_sufficient']);self.assertEqual(small['penalty'],0)
        self.assertTrue(large['sample_sufficient']);self.assertEqual(large['policy'],'demote_not_disable')
    def test_diagnostics_and_metrics_saved_without_invalid_reply(self):
        from test_commercial_ai3b import AI
        from sales.commercial import ai
        case=AI();case.setUp();self.addCleanup(case.doCleanups)
        def invalid(payload,config,check):
            response=case.response(payload,config,check);response['output']['actor']='Private unsupported actor';return response
        before=copy.deepcopy(case.result);b=case.call(provider=invalid)
        self.assertEqual(b['status'],'invalid');self.assertEqual(b['validation']['code'],'ACTOR_ALIAS_UNRESOLVED');self.assertIsNone(b['output'])
        self.assertNotIn('Private unsupported actor',json.dumps(ai.lookup(case.store,1,7)))
        self.assertEqual(case.result,before);self.assertEqual(ai.summary(case.store,1)['validation_categories']['ACTOR_ALIAS_UNRESOLVED'],1)

    def test_pdf_and_facebook_remain_excluded_all_engines(self):
        for engine in ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'):
            self.assertEqual(assess({'url':'https://example.it/a.pdf'},engine)['reason'],'excluded_pdf')
            self.assertEqual(assess({'url':'https://facebook.com/post/1'},engine)['reason'],'excluded_facebook')
    def test_named_project_siblings_never_share_requests(self):
        page={'url':'https://program.example/projects','status':200,'checked_at':'2026-10-17',
              'html':'<h1>I nostri progetti</h1><h2>Beta</h2><p>Startup Beta: cerchiamo sviluppatori WordPress freelance.</p><h2>Gamma</h2><p>Progetto Gamma: lavoriamo nelle foreste, senza compenso.</p>'}
        blocks=extract(page);self.assertEqual(len(blocks),1);self.assertEqual(blocks[0]['subject'],'Beta')
        self.assertNotIn('foreste',blocks[0]['text']);self.assertNotIn('senza compenso',blocks[0]['text'])
    def test_redirect_to_institution_does_not_launch_browser(self):
        import tempfile
        from sales.db import Store
        from sales.commercial.inspection import inspect
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.sqlite3');store.init()
            page={'url':'https://it.wikipedia.org/wiki/Azienda','status':200,'checked_at':'2026-10-17','html':'<title>Wikipedia</title><p>Pagina informativa.</p>'}
            with patch('sales.commercial.inspection.ResearchWeb.get',return_value=page) as read,patch('sales.commercial.browser.review',side_effect=AssertionError('no browser')):
                r=inspect(store,{'url':'https://example.it','commercial_engine':'WEBSITE_REBUILD'})
            self.assertEqual(read.call_count,1);self.assertEqual(r['result']['state'],'REJECTED')

    def test_third_party_direct_request_can_be_investigated(self):
        r=assess({'url':'https://example.it/news/progetto','title':'Beta cerca sviluppatori WordPress freelance','content':'Per costruire un sito web.'},'STARTUPS')
        self.assertEqual(r['decision'],'admit');self.assertFalse(r['preflight']['identity_verified'])

if __name__=='__main__':unittest.main()
