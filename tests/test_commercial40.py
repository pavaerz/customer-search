"""Commercial First acceptance: saved originals and labelled synthetic cases."""
import copy,gzip,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from sales.commercial.opportunity_view import build,novelty,request_key
from sales.commercial.entity_scope import owner_fact
from sales.commercial.admission import exclusion,listing_url
from sales.commercial.commercial_gate import sufficient
from sales.commercial.storage import Opportunities
from sales.commercial.resources import Budget,BudgetExceeded
from test_commercial_engines import CommercialTestCase,page

ROOT=Path(__file__).parent/'fixtures/commercial40'
def load():
    with gzip.open(ROOT/'campaign24.json.gz','rt') as f:return json.load(f)

class Historical40(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.x=load();cls.now=datetime.fromisoformat(cls.x['snapshot_at'])
    def b(self,n):return copy.deepcopy(next(r['body'] for r in self.x['commercial_revisions'] if r['id']==n))
    def view(self,n):return build(self.b(n),as_of=self.now)
    def test_apiceweb_undated_visible(self):
        v=self.view(936);self.assertEqual(v['status'],'WORTH_REVIEWING');self.assertEqual(v['official_state'],'NEEDS_REVIEW');self.assertIn('attuale',str(v['missing']))
    def test_parklab_partner_not_commission(self):
        v=self.view(937);self.assertEqual(v['opportunity_type'],'CONTINUING_PARTNERSHIP');self.assertEqual(v['status'],'READY_TO_CONTACT');self.assertIn('senza presumere una commessa',v['next_action'])
    def test_pacer_not_bebee(self):
        v=self.view(946);self.assertEqual(v['company'],'Pacer');self.assertEqual(v['status'],'RESEARCH_REQUIRED');self.assertIsNone(v['official_domain']);self.assertEqual(v['contacts'],[]);self.assertEqual(v['roles']['PUBLISHER'],'bebee.com')
    def test_pacer_original_inspection_retains_request(self):
        from sales.commercial.inspection import inspect
        from sales.db import Store
        import tempfile
        b=self.b(946);p=self.x['pages'][b['url']]
        with tempfile.TemporaryDirectory() as tmp:
            st=Store(Path(tmp)/'t.db');st.init()
            with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):out=inspect(st,{'url':p['url'],'commercial_engine':'STARTUPS'})
        self.assertEqual(out['identity']['name'],'Pacer');self.assertIsNone(out['identity']['website']);self.assertEqual(out['identity']['contacts'],[]);self.assertTrue(out['result']['evidence']);self.assertEqual(out['followups'],[])
    def test_pichler_low_priority(self):self.assertEqual(self.view(959)['status'],'NOT_ACTIONABLE')
    def test_genesi_third_party_workforce(self):
        self.assertFalse(owner_fact(".Suzhou BAOMA e’ il piu grande costruttore, 300 dipendenti.",'Genesi s.r.l.'))
        from sales.commercial.target_fit import evaluate
        b=self.b(962);docs={d['id']:d for d in self.x['documents']};pages=[self.x['pages'][docs[i]['url']] for i in b['document_ids']]
        f=evaluate(b['identity'],pages,b['geography']);self.assertNotIn('documented_large_company_lower_priority',f['reasons']);self.assertTrue(f['audit_allowed'])
    def test_olivi_partial_visible_no_defects(self):
        v=self.view(941);self.assertEqual(v['status'],'WORTH_REVIEWING');self.assertEqual(v['audit_state'],'PARTIAL');self.assertIn('nessun difetto',str(v['missing']))
    def test_boutique_revisions_not_new(self):
        rows=[r for r in self.x['commercial_revisions'] if r['id']==955];self.assertEqual(novelty(self.b(956),rows)['status'],'ALREADY_SEEN')
    def test_hfarm_training_not_request(self):
        b=self.b(960);self.assertEqual(build(b)['status'],'NOT_ACTIONABLE');self.assertEqual(exclusion({'url':b['url'],'title':b['title'],'content':'Bootcamp per studenti e pitching di MVP'},'STARTUPS'),'training_not_request')
    def test_microsoft_mvp_not_sport(self):self.assertNotEqual(exclusion({'url':'https://linkedin.com/in/example','title':'Designer app premiate Ex Microsoft MVP'},'STARTUPS'),'sports_mvp_not_software')
    def test_clickajobs_without_client(self):
        v=self.view(942);self.assertEqual(v['status'],'NOT_ACTIONABLE');self.assertEqual(v['contacts'],[])
    def test_vanzo_is_company_not_directory(self):
        from sales.commercial.target_fit import source_role
        p=self.x['pages']['https://vanzoserramenti.it/'];from sales.extract import parse_page
        d=parse_page(p);self.assertNotEqual(source_role(p['url'],d['title'],d['text']),'directory')
    def test_outbound_no_audit_visible(self):self.assertEqual(self.view(947)['status'],'WORTH_REVIEWING')
    def test_robots_no_invented_defects(self):
        v=self.view(948);self.assertNotEqual(v['status'],'READY_TO_CONTACT');self.assertEqual(v['audit_state'],'NOT_EXECUTED')
    def test_publisher_generic_followups_excluded(self):
        from sales.commercial.context import followups
        b=self.b(946);self.assertFalse(any(listing_url(l['url']) for l in followups(self.x['pages'][b['url']])))
    def test_original_objects_unchanged(self):
        b=self.b(936);old=copy.deepcopy(b);build(b);self.assertEqual(b,old)

class Synthetic40(unittest.TestCase):
    def active(self):
        b=copy.deepcopy(next(r['body'] for r in load()['commercial_revisions'] if r['id']==936))
        b['checked_at']=datetime.now(timezone.utc).isoformat();b['geography']['eligible']=True
        b['verification'].update(currently_open=True,availability_verified=True,currentness='active');return b
    def test_unknown_date_never_ready(self):
        b=self.active();b['verification'].update(currently_open=False,availability_verified=False,currentness='unknown');self.assertEqual(build(b)['status'],'WORTH_REVIEWING')
    def test_active_verified_contact_ready(self):self.assertEqual(build(self.active())['status'],'READY_TO_CONTACT')
    def test_email_only_not_promotion(self):
        b=self.active();b['identity']['contacts']=[{'type':'email','value':'info@example.test'}];self.assertNotEqual(build(b)['status'],'READY_TO_CONTACT')
    def test_syndication_key_independent_of_url(self):
        a=self.active();b=copy.deepcopy(a);b['url']='https://other.example/jobs/1';self.assertEqual(request_key(a),request_key(b))
    def test_distinct_dated_request_not_merged(self):
        a=self.active();a['published_at']='2026-09-01';b=copy.deepcopy(a);b['published_at']='2026-10-01';b['commercial_intent']['request_clause']='Cerchiamo frontend freelance per un portale B2B.'
        self.assertNotEqual(request_key(a),request_key(b));self.assertEqual(novelty(b,[{'id':1,'body':a}])['status'],'NEW')
    def test_ai_without_subject_skips(self):self.assertFalse(sufficient('FREELANCE',{},[{'id':'1','url':'https://a.example','text':'Cerchiamo sviluppatore WordPress freelance.'}])['allowed'])
    def test_ai_cannot_promote(self):
        b=self.active();b['verification']['currently_open']=False;b['verification']['availability_verified']=False;b['ai_assessment']={'status':'completed','output':{'confidence':1,'state':'VERIFIED'}};self.assertEqual(build(b)['status'],'WORTH_REVIEWING')
    def test_crm_suppression_overrides_advice(self):
        self.assertEqual(build(self.active(),manual={'do_not_contact':True})['status'],'NOT_ACTIONABLE')
    def test_evidence_weaker_does_not_erase_previous(self):
        a=self.active();b=copy.deepcopy(a);b['evidence']=[];b['published_at']=None
        self.assertEqual(novelty(b,[{'id':1,'body':a}])['status'],'ALREADY_SEEN')
    def test_expired_partner_not_ready(self):
        b=self.active();b['classification']='ongoing';b['checked_at']='2020-01-01';self.assertNotEqual(build(b)['status'],'READY_TO_CONTACT')

class Persistence40(CommercialTestCase):
    def test_stop_resume_one_slot_two_bounded_attempts(self):
        import json
        from sales.commercial.catalog import options
        limits=options({'commercial_engines':['WEBSITE_REBUILD']})[1]
        with self.store.connect() as c:
            c.execute("INSERT INTO research_tasks(campaign_id,kind,strategy,fingerprint,state,payload,available_at,created_at,updated_at) VALUES (?,'candidate','WEBSITE_REBUILD','audit40','working','{}','now','now','now')",(self.c['id'],));tid=c.execute('select last_insert_rowid()').fetchone()[0]
        b=Budget(self.store,self.c,'WEBSITE_REBUILD',limits);b.task_id=tid;b.browser_slot();b.reserve('http_reads');b.browser_finished(True)
        self.assertTrue(b.browser_continuation());b.browser_slot();self.assertEqual(b.used('browser_runs'),1);self.assertEqual(b.used('http_reads'),1);b.browser_finished(True)
        self.assertFalse(b.browser_continuation())
        with self.assertRaises(BudgetExceeded):b.browser_slot()
    def test_api_view_filter_keeps_official_history(self):
        from sales.commercial.inspection import inspect
        p=page('Cerchiamo sviluppatore WordPress freelance per un nuovo sito.',date=False)
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):out=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})
        repo=Opportunities(self.store);oid=repo.save(self.c,out['identity'],out['documents'],out['result']);before=repo.get(oid)['revisions']
        got=repo.listing({'campaign':self.c['id'],'commercial_status':'WORTH_REVIEWING'})
        self.assertEqual(got['total'],1);self.assertEqual(got['items'][0]['state'],'NEEDS_REVIEW');self.assertEqual(repo.get(oid)['revisions'],before)

    def test_failed_revision_keeps_prior_request_visible_without_ready(self):
        from sales.commercial.inspection import inspect
        p=page('Cerchiamo sviluppatore WordPress freelance per un nuovo sito.',date=False)
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):out=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})
        repo=Opportunities(self.store);oid=repo.save(self.c,out['identity'],out['documents'],out['result'])
        failed=copy.deepcopy(out['result']);failed.update(state='UNVERIFIABLE',classification='access_incomplete',evidence=[],reason='Timeout della lettura successiva.',commercial_intent={},request_blocks=[])
        self.assertEqual(repo.save(self.c,out['identity'],[],failed),oid)
        item=repo.get(oid);self.assertEqual(item['state'],'UNVERIFIABLE');self.assertEqual(item['commercial_view']['status'],'WORTH_REVIEWING');self.assertIn('retained_revision',item['commercial_view'])
    def test_no_future_revision_in_historical_dossier(self):
        from sales.commercial.inspection import inspect
        p=page('Cerchiamo sviluppatore WordPress freelance.',date=False)
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):out=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})
        repo=Opportunities(self.store);oid=repo.save(self.c,out['identity'],out['documents'],out['result'])
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);new=self.rs.create();repo.save(new,out['identity'],out['documents'],out['result'])
        item=repo.listing({'campaign':self.c['id']})['items'][0]
        self.assertEqual(item['evidence_history']['latest_decision']['campaign_id'],self.c['id'])
    def test_different_verified_request_dates_have_distinct_ids(self):
        from sales.commercial.inspection import inspect
        p=page('Cerchiamo sviluppatore WordPress freelance per un nuovo progetto.')
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):out=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})
        repo=Opportunities(self.store);a=repo.save(self.c,out['identity'],out['documents'],out['result'])
        b=copy.deepcopy(out['result']);b['published_at']='2026-01-01';b['verification']['checks']['temporal_basis']=True
        other=repo.save(self.c,out['identity'],out['documents'],b);self.assertNotEqual(a,other)
