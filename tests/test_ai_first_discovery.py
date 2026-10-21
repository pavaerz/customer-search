"""Query/source admission; no result is qualified by these checks."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6.query_pipeline import prepare
from sales.agent6.discovery_intent import source_issue


class QueryAdmission(unittest.TestCase):
    def test_two_observed_campaign44_noise_queries_are_returned_to_planner(self):
        for flow,text in (
            ('AGENCIES','site:.it Lombardia studio digitale ("collaboriamo" OR "partner tecnici") (ecommerce OR web app)'),
            ('STARTUPS','site:.it startup Piemonte ecommerce sviluppo sito'),
        ):
            prepared,error=prepare(harness.query(text),flow,['Lombardia','Piemonte'],ai_first=True)
            self.assertIsNone(prepared)
            self.assertEqual(error['reason'],'query_commercial_direction_missing')
            self.assertIn('instruction',error)

    def test_spontaneous_external_requests_events_and_proactive_search_still_allowed(self):
        for flow,text,strategy in (
            ('AGENCIES','agenzia candidature portfolio Veneto','spontaneous_collaboration'),
            ('AGENCIES','agency accept applications freelance frontend Italy','external_collaboration'),
            ('AGENCIES','agenzia accettiamo collaboratori esterni Veneto','external_collaboration'),
            ('AZIENDE','azienda cerca fornitore sito completo Veneto','explicit'),
            ('STARTUPS','startup cerchiamo socio tecnico frontend Toscana','technical_cofounder'),
            ('NEWS','azienda inaugura nuovo showroom Veneto','new_showroom'),
            ('AZIENDE','produttori arredamento catalogo Veneto','official_company_sector_region'),
            ('STARTUPS','startup aziende logistica servizi Lombardia','official_company_sector_region'),
        ):
            with self.subTest(query=text):
                q={**harness.query(text),'strategy':strategy}
                prepared,error=prepare(q,flow,['Veneto','Toscana','Lombardia'],ai_first=True)
                self.assertIsNone(error)
                self.assertTrue(prepared['commercial_policy']['allowed'])
                self.assertNotIn('qualified',prepared['commercial_policy'])

    def test_every_or_branch_and_exclusions_cannot_fake_demand(self):
        for text in (
            'agenzia WordPress Veneto -cerchiamo',
            'startup ("cerchiamo freelance" OR "sviluppo sito") Veneto',
            'agenzia "progetti realizzati" WordPress Veneto',
            'developer "tempo indeterminato" Veneto',
            'agenzia "richiedi preventivo" ecommerce Veneto',
        ):
            self.assertIsNone(prepare(harness.query(text),'STARTUPS',['Veneto'],ai_first=True)[0],text)

    def test_source_collections_not_companies_and_original_articles_remain_allowed(self):
        for url in ('https://company.example/tag/wordpress/','https://www.ansa.it/',
                    'https://linkedin.com/company/alfa/'):
            self.assertIsNotNone(source_issue({'url':url}),url)
        for url in ('https://alfa.example/','https://alfa.example/lavora-con-noi/',
                    'https://www.ansa.it/veneto/notizie/2026/10/20/azienda-nuovo-prodotto.html'):
            self.assertIsNone(source_issue({'url':url}),url)

    def test_replay_all_saved_campaign44_queries_without_provider(self):
        path=Path('CUSTOMERSEARCH-AI-FIRST-LIVE-01-METRICS.json')
        if not path.exists():self.skipTest('Optional local campaign report absent')
        saved=json.loads(path.read_text())
        results=[]
        for task in saved['research_tasks']:
            if task['kind']!='search':continue
            q=task['payload'];q=json.loads(q) if isinstance(q,str) else q
            p,error=prepare(q,task['strategy'],saved['campaign']['filters']['regions'],ai_first=True)
            results.append((task['strategy'],bool(p),error))
        self.assertEqual(len(results),8)
        self.assertEqual(sum(ok for _,ok,_ in results),6)
        self.assertEqual([flow for flow,ok,_ in results if not ok],['AGENCIES','STARTUPS'])

    def test_indexed_post_hint_can_only_justify_a_reference_lookup(self):
        from sales.agent6.social_seeds import lookup_worthwhile
        base={'url':'https://instagram.com/p/example/'}
        for text in ('Cerchiamo sviluppatore frontend freelance per il nuovo sito.',
                     'Accettiamo collaboratori esterni WordPress.'):
            self.assertTrue(lookup_worthwhile({**base,'content':text}))
        for text in ('Cerchi un sito? Offriamo sviluppo WordPress.',
                     'CERCO SUGGERIMENTI e offro visibilità per un contenuto video.',
                     'Corso per sviluppatori WordPress e frontend.'):
            self.assertFalse(lookup_worthwhile({**base,'content':text}))


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath();self.base.setUp()

    def tearDown(self):
        self.base.tearDown()

    def test_bad_query_never_reaches_serper_and_records_feedback(self):
        b=self.base
        q=harness.query('startup Piemonte ecommerce sviluppo sito')
        task={'id':999,'kind':'search','strategy':'STARTUPS','payload':q}
        with patch('sales.agent6.research.acquire',side_effect=AssertionError('No paid query')):
            b.w.execute(task,lambda:None)
        with b.store.connect() as db:
            value=json.loads(db.execute("SELECT body FROM agent6_memory WHERE kind='query_policy' ORDER BY id DESC").fetchone()[0])
        self.assertEqual(value['reason'],'query_commercial_direction_missing')

    def test_bad_plan_recovers_with_existing_budget_and_feedback(self):
        b=self.base;calls=[]
        bad=harness.query('studio digitale partner tecnici ecommerce Veneto')
        good=harness.query('agenzia "collabora con noi" frontend Veneto')
        def model(payload,cfg,check):
            calls.append(payload)
            return {'output':{'decision':'search','reason':'Offline planning test',
                              'queries':[bad if len(calls)==1 else good]},'usage':{}}
        before=json.dumps(b.w.budget,sort_keys=True)
        with patch('sales.agent6.ai.infer',side_effect=model),patch(
                'sales.agent6.research.acquire',side_effect=AssertionError('No search during planning')):
            for n in range(2):
                b.w.planning({'id':700+n,'strategy':'AGENCIES','payload':{'round':n}},lambda:None)
        self.assertEqual(len(calls),2)
        self.assertIn('query_commercial_direction_missing',json.dumps(calls[1]['memory']))
        self.assertEqual(json.dumps(b.w.budget,sort_keys=True),before)
        with b.store.connect() as db:
            tasks=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='search'")]
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],2)
        self.assertEqual(len(tasks),1)
        self.assertEqual(tasks[0]['query'],good['query'])

    def test_collection_not_counted_as_examined_or_negative_company(self):
        b=self.base;q=harness.query()
        items=[{'url':'https://www.ansa.it/','title':'Notizie'},
               {'url':'https://alfa.example/tag/wordpress/','title':'Archivio WordPress'},
               {'url':'https://alfa.example/collabora/','title':'Alfa Srl cerca freelance'}]
        b.w.enqueue('search','AGENCIES',q,'source-test')
        with b.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='source-test'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        with patch('sales.agent6.research.acquire',return_value=items):
            b.w.execute(task,lambda:None)
        with b.store.connect() as db:
            bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            receipt=json.loads(db.execute("SELECT body FROM agent6_memory WHERE kind='query' ORDER BY id DESC").fetchone()[0])
        self.assertEqual(len(bodies),1)
        self.assertEqual(bodies[0]['state'],'DISCOVERED')
        self.assertEqual(receipt['new_urls'],1)
        self.assertEqual(len(receipt['policy_rejections']),2)
        from sales.agent6 import memory
        history=memory.history(b.store,'AGENCIES')
        self.assertEqual(len(history['sources']),2)
        self.assertTrue(all(s['rejected']==1 for s in history['sources']))

    def test_historical_url_only_exclusion_receipt_does_not_break_next_plan(self):
        from sales.agent6 import memory
        b=self.base
        memory.event(b.store,b.c,'AGENCIES','query','old-query',
                     {'query':'old query','strategy':'old','results':2,
                      'policy_rejections':[{'url':'https://alfa.example/file.pdf','reason':'excluded_pdf'},
                                           {'reason':'missing_url'}]})
        with b.store.connect() as db:
            before=db.execute('SELECT body FROM agent6_memory WHERE key=?',('old-query',)).fetchone()
        history=memory.history(b.store,'AGENCIES')
        self.assertTrue(any(s['domain']=='alfa.example' and s['rejected']==1 for s in history['sources']))
        with b.store.connect() as db:
            after=db.execute('SELECT body FROM agent6_memory WHERE key=?',('old-query',)).fetchone()
        self.assertEqual(before,after)

    def test_indexed_invitation_queues_one_bounded_recovery_without_qualifying_snippet(self):
        b=self.base;q=harness.query('site:instagram.com/p "cerchiamo" "frontend freelance" Italia')
        item={'url':'https://www.instagram.com/p/ExampleRequest/',
              'title':'Alfa Srl','content':'Cerchiamo freelance frontend per il nostro nuovo sito.'}
        b.w.enqueue('search','AGENCIES',q,'social-index')
        with b.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='social-index'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        with patch('sales.agent6.research.acquire',return_value=[item]),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No snippet judgment')):
            b.w.execute(task,lambda:None)
            b.w.execute(task,lambda:None)
        with b.store.connect() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            followups=[json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM research_tasks WHERE fingerprint LIKE 'social-reference:%'")]
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['state'],'UNVERIFIABLE')
        self.assertIsNone(records[0]['decision'])
        self.assertFalse(records[0]['social_source']['original_read'])
        self.assertEqual(len(followups),1)
        self.assertIn('"ExampleRequest"',followups[0]['query'])
        self.assertEqual(followups[0]['social_origin']['url'],item['url'])
        self.assertFalse(followups[0]['social_origin']['original_read'])
