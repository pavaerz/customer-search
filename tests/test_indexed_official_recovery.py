"""Real indexed hint, synthetic originals: routing only, no paid/live assertions."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as harness
from sales.agent6.indexed_recovery import proposal,candidate_issue

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign48/indexed-request.json').read_text())

class IndexedHints(unittest.TestCase):
    def test_real_primary_role_and_requester_generate_only_verification_question(self):
        q=proposal(SAVED)
        self.assertEqual(q['expected_entity'],'Quinck')
        self.assertEqual(q['query'],'"Quinck" Frontend careers -site:it.trabajo.org')
        self.assertEqual(q['selection'],'verification')
        self.assertFalse(q['indexed_origin']['identity_verified'])
        self.assertFalse(q['indexed_origin']['original_request_verified'])
        self.assertNotIn('budget',q)
        from sales.agent6.query_pipeline import prepare
        self.assertIsNone(prepare(q,'STARTUPS',['Veneto'],ai_first=True)[1])

    def test_indices_generic_advice_employee_and_mixed_employers_have_no_lookup(self):
        variants=[{'url':'https://it.trabajo.org/jobs-frontend'},
            {'title':'Offerte di lavoro sviluppatori'},
            {'content':'Lavorare come freelance è una possibilità per gli sviluppatori.'},
            {'content':SAVED['content']+' Contratto a tempo indeterminato.'},
            {'content':SAVED['content']+' Altri annunci: Beta cerca un developer.'},
            {'content':'Quinck cerca un developer. Beta cerca un frontend developer.'},
            {'title':'Freelance Frontend Developer at Beta','content':SAVED['content']},
            {'url':'https://seller.example/offerta/123456/'}]
        for change in variants:self.assertIsNone(proposal({**SAVED,**change}),change)

    def test_republished_and_unidentified_destinations_are_not_official_candidates(self):
        origin=proposal(SAVED)['indexed_origin']
        self.assertIsNotNone(candidate_issue({'url':SAVED['url'],'title':'Quinck hiring'},origin))
        self.assertIsNotNone(candidate_issue({'url':'https://other.example','title':'Beta careers','content':'Quinck'},origin))
        self.assertIsNone(candidate_issue({'url':'https://company.example/careers','title':'Quinck Careers'},origin))

class Queue(unittest.TestCase):
    def setUp(self):
        self.b=harness.IntegratedPath();self.b.setUp();self.addCleanup(self.b.tearDown)

    def search(self,items,payload=None):
        with patch('sales.agent6.research.acquire',return_value=items),patch(
            'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No blocked read')),patch(
            'sales.agent6.ai.infer',side_effect=AssertionError('No snippet inference')):
            self.b.w.execute({'id':1,'kind':'search','strategy':'STARTUPS','payload':payload or harness.query('startup Veneto cerca sviluppatore freelance frontend')},lambda:None)

    def tasks(self,kind):
        with self.b.store.connect() as c:
            return [{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM research_tasks WHERE kind=?',(kind,))]

    def test_blocked_hint_enqueues_once_on_replay_without_contact_or_qualification(self):
        self.search([SAVED]);self.search([SAVED])
        tasks=self.tasks('search');self.assertEqual(len(tasks),1)
        self.assertEqual(tasks[0]['payload']['indexed_origin']['company_hint'],'Quinck')
        with self.b.store.connect() as c:
            body=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        self.assertEqual(body['validation_status'],'ACCESS_BLOCKED')
        self.assertIsNone(body['decision'])

    def test_only_one_lookup_per_batch_and_budget_is_preserved(self):
        other={**SAVED,'url':SAVED['url']+'different','content':'Beta cerca un frontend developer freelance.'}
        self.search([SAVED,other])
        self.assertEqual(len(self.tasks('search')),1)
        self.assertEqual(self.tasks('search')[0]['payload']['depth'],1)

    def test_recovery_does_not_chase_other_aggregators_and_keeps_hint(self):
        q=proposal(SAVED)
        self.search([SAVED,{'url':'https://company.example/jobs','title':'Quinck careers'},
                     {'url':'https://other.example','title':'Beta hiring','content':'Quinck'}],q)
        tasks=self.tasks('candidate');self.assertEqual(len(tasks),1)
        self.assertEqual(tasks[0]['payload']['indexed_origin'],q['indexed_origin'])
        self.assertEqual(len(self.tasks('search')),0)

    def test_unrelated_original_does_not_use_indexed_company_as_identity_or_call_ai(self):
        q=proposal(SAVED);url='https://other.example/jobs'
        self.b.w.enqueue('candidate','STARTUPS',{'url':url,'indexed_origin':q['indexed_origin']},'read')
        page={'url':url,'html':'<title>Beta Srl</title><p>Beta Srl cerca collaboratori.</p>',
              'status':200,'checked_at':harness.DATE,'content_type':'text/html'}
        with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch(
            'sales.agent6.ai.infer',side_effect=AssertionError('Wrong owner cannot use AI')):
            self.b.w.execute(self.tasks('candidate')[0],lambda:None)
        with self.b.store.connect() as c:b=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
        self.assertEqual(b['validation_status'],'SOURCE_ATTRIBUTION_UNVERIFIED')
        self.assertIsNone(b['decision'])
        self.assertFalse(b['indexed_origin']['original_request_verified'])

    def test_stop_prevents_new_lookup(self):
        self.b.rs.stop(self.b.c['id'])
        with self.assertRaises(InterruptedError):self.search([SAVED])
        self.assertEqual(self.tasks('search'),[])

    def test_matching_original_is_evaluated_without_citing_the_indexed_hint(self):
        origin={**proposal(SAVED)['indexed_origin'],'company_hint':'Alfa Srl',
                'snippet':'SNIPPET_ONLY_NOT_PROOF; paid work claimed by publisher'}
        url='https://alfa.example/collabora'
        self.b.w.enqueue('candidate','STARTUPS',{'url':url,'indexed_origin':origin},'read-owner')
        page={'url':url,'html':'<title>Alfa Srl</title>'+''.join('<p>'+t+'</p>' for t in harness.TEXT.splitlines()),
              'status':200,'checked_at':harness.DATE,'content_type':'text/html'}
        identity={'identity_status':'verified','name':'Alfa Srl','website':url,'contacts':[]}
        seen=[]
        def provider(p,cfg,check):
            seen.append(p)
            self.assertNotIn('SNIPPET_ONLY_NOT_PROOF',json.dumps(p['evidence']))
            return {'output':harness.response(p),'usage':{}}
        with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch(
            'sales.agent6.research.identity_from',return_value=identity),patch(
            'sales.agent6.research.locate',return_value={'eligible':True,'regions':['Veneto']}),patch(
            'sales.agent6.ai.infer',side_effect=provider):
            self.b.w.execute(self.tasks('candidate')[0],lambda:None)
        self.assertEqual(len(seen),1)
        with self.b.store.connect() as c:b=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
        self.assertEqual(b['decision'],'INTERESTING')
        self.assertEqual(b['compensation'],'UNKNOWN')
        self.assertFalse(b['indexed_origin']['original_request_verified'])
        self.assertTrue(all(f['url']==url for f in b['facts']))
