"""3A.1 orchestration: saved campaign evidence + explicitly simulated alternatives."""
import gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.catalog import ENGINES,plan,options
from sales.commercial.coordinator import Coordinator
from sales.commercial.planner import choose,coverage
from sales.commercial.resources import Budget,BudgetExceeded,availability
from sales.commercial.social import inspect_social,official_hints
from sales.content_policy import note_pdf

with gzip.open(Path(__file__).parent/'fixtures/commercial31/campaign13.json.gz','rt') as f:SAVED=json.load(f)
POST='https://www.instagram.com/p/DW3VAcqAi2U/'

class Optimization31Tests(CommercialTestCase):
    def worker(self,budgets=None,mode='pilot'):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create({'commercial_engines':list(ENGINES),'mode':mode,'regions':['Veneto','Lombardia'],'work_budget':budgets or {}})
        w=Coordinator(self.store,self.c);w.initialize();return w
    def execute_plan(self,w,engine,n):
        out=[]
        for i in range(n):
            p=choose(self.store,self.c['id'],engine,[p for p in plan(engine) if p['region'] in ['Veneto','Lombardia']])
            out.append(p);w.enqueue('search',engine,p,engine+str(i))
            # Simulate high preliminary reward from the first strategy.
            w.trace(engine,{'url':'https://alfa.example/'+str(i),'canonical_url':'https://alfa.example/'+str(i),'query':p['query'],'decision':'admit','priority':85})
        return out
    def test_pilot_guarantees_distinct_families_and_channels(self):
        w=self.worker()
        for engine in ENGINES:
            p=self.execute_plan(w,engine,3)
            self.assertEqual(len({x['family'] for x in p}),3)
            self.assertEqual({x['region'] for x in p},{'Veneto','Lombardia'})  # 3B explores territories inside the same Pilot quota.
            # 3B.4 Pilot prioritizes distinct commercial intents; social remains an exploration family.
            self.assertTrue(all(x['strategy_version']==('4.5' if engine=='FREELANCE' else '4.3') for x in p))
            self.assertTrue(all(x.get('source_preference') for x in p))
        cov=coverage(self.store,self.c['id'],list(ENGINES),['Veneto','Lombardia'])
        self.assertTrue(all(r['tried_families']==3 and r['remaining_families'] for r in cov))
    def test_planner_persistent_deterministic_no_regional_repetition(self):
        w=self.worker();first=self.execute_plan(w,'FREELANCE',1)[0]
        expected=choose(self.store,self.c['id'],'FREELANCE',plan('FREELANCE'))
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);resumed=self.rs.resume(self.c['id'])
        self.assertEqual(expected,choose(self.store,self.c['id'],'FREELANCE',plan('FREELANCE')))
        self.assertNotEqual(first['family'],expected['family'])
        self.assertEqual(Budget(self.store,resumed,'FREELANCE',w.budget).used('queries'),1)
    def test_after_exploration_fairness_and_single_failure_not_penalized(self):
        w=self.worker({'max_queries_per_engine':100},mode='standard')
        plans=[{'query':f'{f} {r}','family':f,'region':r} for r in range(12) for f in ('one','two','three')]
        used=[]
        with patch('sales.commercial.planner.metrics',side_effect=lambda st,c,e,q:{'seen':10,'relevant':8 if q.startswith('one') else 0,'verifiable':0,'qualified':0,'inaccessible':1 if q.startswith('one') else 0}):
            for i in range(15):
                p=choose(self.store,self.c['id'],'FREELANCE',plans);used.append(p)
                w.enqueue('search','FREELANCE',p,'fair'+str(i))
        self.assertEqual([p['family'] for p in used[:3]],['one','two','three'])
        self.assertEqual(used[3]['family'],'one')
        self.assertGreater(sum(p['family']=='two' for p in used),1)
        self.assertGreater(sum(p['family']=='three' for p in used),1)
    def test_excluded_families_not_forced(self):
        self.worker()
        p=choose(self.store,self.c['id'],'FREELANCE',[{'query':'no','family':'no','eligible':False},{'query':'yes','family':'yes'}])
        self.assertEqual(p['query'],'yes')
    def task(self,w):
        w.enqueue('search','FREELANCE',{'query':'test','page':1},'one-search')
        return self.rs.claim(self.c['id'],self.c['generation'])
    def test_every_received_appearance_traced_budget_duplicates_pdf(self):
        w=self.worker({'max_candidates_per_engine':1});task=self.task(w)
        # Historical campaigns keep the pre-5.1 admission quota after resume.
        self.c['filters'].pop('demand_version',None)
        with self.store.connect() as c:c.execute('UPDATE campaigns SET filters=? WHERE id=?',(json.dumps(self.c['filters']),self.c['id']))
        items=[{'url':'https://agency.example/jobs','title':'Cerchiamo sviluppatore WordPress freelance'}, {'url':'https://agency.example/jobs','title':'Cerchiamo sviluppatore WordPress freelance'}, {'url':'https://other.example/jobs','title':'Cerchiamo sviluppatore WordPress freelance'}, {'url':'https://agency.example/a.pdf','title':'PDF'}]
        self.assertEqual(w.receive(task,items,lambda:None),1)
        with self.store.connect() as c:
            rows=c.execute('SELECT decision,body FROM commercial_discovery WHERE campaign_id=? ORDER BY id',(self.c['id'],)).fetchall()
        self.assertEqual([r['decision'] for r in rows],['admit','duplicate','budget','exclude'])
        self.assertEqual(json.loads(rows[-1]['body'])['reason'],'excluded_pdf')
        # Re-receiving an acquisition does not duplicate its receipt records.
        w.receipts(task,items)
        self.assertEqual(self.rs.campaign(self.c['id'])['trace_counts']['received'],4)
    def test_stop_mid_batch_accounts_unprocessed_without_promotions(self):
        w=self.worker();task=self.task(w);n=0
        def check():
            nonlocal n
            n+=1
            if n==2:self.rs.stop(self.c['id']);raise InterruptedError()
        items=[{'url':f'https://agency.example/jobs/{i}','title':'Cerchiamo sviluppatore WordPress freelance'} for i in range(3)]
        with self.assertRaises(InterruptedError):w.receive(task,items,check)
        counts=self.rs.campaign(self.c['id'])['trace_counts']
        self.assertEqual((counts['received'],counts['admitted'],counts['not_processed']),(3,1,2))
        self.assertEqual(self.repo.listing()['total'],0)
    def test_actual_provider_receipt_survives_stop_after_transport(self):
        from sales.serper_provider import search
        w=self.worker();task=self.task(w);self.store.configure({'provider':'serper'})
        budget=Budget(self.store,self.c,'FREELANCE',w.budget);budget.on_results=lambda items:w.receipts(task,items)
        def transport(*args):self.rs.stop(self.c['id']);return {'organic':[{'link':'https://a.example/jobs','title':'Cerchiamo sviluppatore freelance'}]}
        def check():
            if not self.rs.active(self.c['id'],self.c['generation']):raise InterruptedError()
        with patch('sales.serper_provider.api_key',return_value='test'),patch('sales.serper_provider.transport',side_effect=transport),budget.task(check):
            with self.assertRaises(InterruptedError):search(self.store,'test',check=check)
        self.assertEqual(self.rs.campaign(self.c['id'])['trace_counts']['not_processed'],1)
    def test_pdf_aggregation_by_task_without_rewriting_older_events(self):
        w=self.worker();self.rs.event(self.c['id'],'excluded_pdf','excluded_pdf','https://a.example/a.pdf',{})
        b=Budget(self.store,self.c,'FREELANCE',w.budget)
        for task_id in [1,2]:
            b.task_id=task_id
            with b.task(lambda:None):
                for i in range(3):note_pdf('https://a.example/a.pdf')
        with self.store.connect() as c:rows=c.execute("SELECT details FROM research_events WHERE kind='excluded_pdf' ORDER BY id").fetchall()
        self.assertEqual(len(rows),3);self.assertEqual(json.loads(rows[0][0]),{})
        self.assertEqual([json.loads(r[0])['occurrences'] for r in rows[1:]],[3,3])
    def test_resume_denied_when_all_work_exhausted_preserves_counters(self):
        w=self.worker({'max_queries_per_engine':1})
        for engine in ENGINES:
            Budget(self.store,self.c,engine,w.budget).reserve('queries')
            with self.store.connect() as c:c.execute("UPDATE commercial_engine_runs SET state='budget_reached',error='Budget operativo esaurito: queries' WHERE campaign_id=? AND engine=?",(self.c['id'],engine))
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        with self.assertRaisesRegex(ValueError,'quote attuali'):self.rs.resume(self.c['id'])
        self.assertEqual(Budget(self.store,self.c,'FREELANCE',w.budget).used('queries'),1)
    def test_linkedin_resolution_does_not_displace_three_discovery_families(self):
        w=self.worker();self.execute_plan(w,'FREELANCE',3)
        item={'url':'https://www.linkedin.com/jobs/view/123','title':'Alfa Srl sta assumendo Frontend developer freelance in Italia'}
        self.assertTrue(w.offer('FREELANCE',item,{'query':'indexed'}))
        with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE kind='resolve'").fetchone()[0],1)
        b=Budget(self.store,self.c,'FREELANCE',w.budget)
        self.assertEqual(b.used('queries'),3);self.assertEqual(b.used('followups'),1)
        for i in range(w.budget['max_provider_requests']):b.paid()
        with self.assertRaises(BudgetExceeded):b.paid()
    def test_new_generation_preserves_previous_receipt_even_attempt_counter_resets(self):
        w=self.worker();task=self.task(w);items=[{'url':'https://a.example/jobs','title':'Cerchiamo sviluppatore WordPress freelance'}]
        w.receive(task,items,lambda:None)
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id'])
        fresh=Coordinator(self.store,self.c);fresh.receive(task,items,lambda:None)
        with self.store.connect() as c:rows=c.execute('SELECT decision FROM commercial_discovery ORDER BY id').fetchall()
        self.assertEqual([r[0] for r in rows],['admit','duplicate'])
    def test_official_careers_redirect_cannot_inherit_company_identity(self):
        home=page('Informazioni aziendali.',url='https://verdurazon.it/',extra='<a href="'+POST+'">Post ufficiale</a><a href="/jobs">Lavora con noi</a>')
        job=page('Cerchiamo sviluppatore WordPress freelance.',url='https://unrelated.example/jobs')
        r=self.social(home,job)
        self.assertEqual(r['result']['state'],'UNVERIFIABLE')
        self.assertEqual(r['result']['evidence'],[])
        self.assertFalse(r['documents'][-1]['official'])
        self.assertEqual(r['result']['social']['official_checks'][-1]['status'],'identity_unverified')
    def test_candidates_limit_explicit_reason(self):
        w=self.worker({'max_candidates_per_engine':1})
        # Historical campaigns keep the pre-5.1 admission quota after resume.
        self.c['filters'].pop('demand_version',None)
        with self.store.connect() as c:c.execute('UPDATE campaigns SET filters=? WHERE id=?',(json.dumps(self.c['filters']),self.c['id']))
        w.offer('FREELANCE',{'url':'https://alfa.example/jobs','title':'Cerchiamo sviluppatore freelance WordPress'},{})
        w.tick()
        run=next(r for r in self.rs.campaign(self.c['id'])['engine_runs'] if r['engine']=='FREELANCE')
        self.assertEqual(run['exhausted_resource'],'candidates');self.assertIn('candidati',run['budget_reason'])
    def payload(self):
        d=next(r['body']['discovery'] for r in SAVED['revisions'] if r['id']==691)
        return {**d,'discovery':d,'social':'instagram','commercial_engine':'FREELANCE','allowed_regions':['Veneto']}
    def social(self,home,job=None,payload=None):
        def read(url):
            if url=='https://verdurazon.it/':return home
            if job:return job
            raise ValueError('Fonte assente nella fixture')
        with patch('sales.commercial.social.PublicSocialWeb.get',side_effect=ValueError('robots divieto esplicito')),patch('sales.commercial.social.CompanyWeb.get',side_effect=read):
            return inspect_social(self.store,payload or self.payload())
    def test_saved_verdurazon_blocked_no_identity_from_snippet(self):
        home=page('Cerchiamo sviluppatore web freelance.',url='https://verdurazon.it/')
        r=self.social(home)
        self.assertEqual(r['result']['state'],'UNVERIFIABLE');self.assertEqual(r['identity']['identity_status'],'unknown')
        self.assertEqual(r['result']['social']['subject_hint'],'verdurazon.it')
        self.assertIsNone(r['result']['published_at'])
    def test_verdurazon_official_source_synthetic_confirmed_separate_evidence(self):
        home=page('Informazioni aziendali.',url='https://verdurazon.it/',extra='<a href="'+POST+'">Post ufficiale</a><a href="/jobs">Lavora con noi</a>')
        job=page('Cerchiamo sviluppatore web WordPress freelance per un nuovo progetto.',url='https://verdurazon.it/jobs')
        r=self.social(home,job)
        self.assertEqual(r['result']['state'],'VERIFIED',r['result']['reason'])
        self.assertEqual(r['result']['social']['review_state'],'official_confirmed')
        self.assertTrue(all(p['url']=='https://verdurazon.it/jobs' for p in r['result']['evidence']))
        self.repo.save(self.c,r['identity'],r['documents'],r['result'])
    def test_official_missing_no_invented_recency_or_identity(self):
        with patch('sales.commercial.social.PublicSocialWeb.get',side_effect=ValueError('robots')),patch('sales.commercial.social.CompanyWeb.get',side_effect=ValueError('403')):
            r=inspect_social(self.store,self.payload())
        self.assertEqual(r['result']['state'],'UNVERIFIABLE');self.assertEqual(r['result']['social']['official_checks'][0]['status'],'unavailable')
    def test_ambiguous_snippet_not_used_as_company_and_unknown_date_stays_unknown(self):
        payload=self.payload();payload['title']='Ricerca sviluppatore';payload['discovery']={};payload['content']='Verdurazon.it e Cyclopes.it cercano personale'
        self.assertEqual(official_hints(payload),[])
        home=page('Informazioni aziendali.',url='https://verdurazon.it/',extra='<a href="'+POST+'">Post ufficiale</a><a href="/jobs">Lavora con noi</a>')
        job=page('Cerchiamo sviluppatore web WordPress freelance per un progetto.',url='https://verdurazon.it/jobs',date=False)
        r=self.social(home,job);self.assertNotEqual(r['result']['state'],'VERIFIED');self.assertIsNone(r['result']['published_at'])

if __name__=='__main__':unittest.main()
