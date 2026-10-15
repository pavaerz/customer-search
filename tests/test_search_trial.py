import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
from sales.db import Store, now, encode
from sales.search_trial import migrate, state, save_key, api_key, key_path, serper_search, TrialManager, NoRedirect, metrics, review
from sales.search_trial_worker import sample, run


class TrialTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();migrate(self.store)
        self.env=patch.dict(os.environ,{'SERPER_API_KEY':'fixture-private-key'});self.env.start();self.addCleanup(self.env.stop)
        self.token='token';self.report={'queries':[],'candidates':[],'limits':[]}
        with self.store.connect() as c:
            self.rid=c.execute("INSERT INTO search_trials(state,generation,message,report,created_at,updated_at) VALUES ('running',?,'Test',?,?,?)",(self.token,encode(self.report),now(),now())).lastrowid
    def check(self):pass
    def test_requires_explicit_free_confirmation(self):
        with self.assertRaisesRegex(ValueError,'crediti gratuiti'):TrialManager(self.store).start()
    def test_stored_key_private_and_never_returned(self):
        TrialManager(self.store).stop();save_key(self.store,'different-private-key-123')
        self.assertEqual(api_key(self.store),'different-private-key-123')
        self.assertEqual(key_path(self.store).stat().st_mode&0o777,0o600)
        self.assertNotIn('different-private',json.dumps(state(self.store)))
        self.assertEqual(self.store.settings()['provider'],'searxng')
    def test_redirect_never_forwards_key(self):
        with self.assertRaises(ValueError):NoRedirect().redirect_request(Request('https://google.serper.dev/search',headers={'X-API-KEY':'secret'}),None,302,'',{},'https://evil.example')
    def test_request_and_normalization(self):
        with patch('sales.search_trial.transport',return_value={'organic':[{'link':'https://example.org','title':'Example'}]}) as transport:
            result=serper_search(self.store,self.rid,self.token,'azienda Veneto',self.check)
        self.assertEqual(result[0]['url'],'https://example.org')
        self.assertEqual(transport.call_args.args[1],{'q':'azienda Veneto','gl':'it','hl':'it','num':10,'page':1})
        self.assertEqual(state(self.store)['used'],1)
    def test_failure_counts_without_retry(self):
        with patch('sales.search_trial.transport',side_effect=ValueError('Unavailable')) as transport:
            with self.assertRaises(ValueError):serper_search(self.store,self.rid,self.token,'query',self.check)
        self.assertEqual(transport.call_count,1);self.assertEqual(state(self.store)['used'],1)
    def test_malformed_result_is_not_success(self):
        with patch('sales.search_trial.transport',return_value={'error':'bad'}):
            with self.assertRaises(ValueError):serper_search(self.store,self.rid,self.token,'query',self.check)
    def test_atomic_limit_between_workers(self):
        with self.store.connect() as c:
            c.executemany("INSERT INTO search_trial_requests(run_id,fingerprint,state,created_at) VALUES (?,'old','reserved',?)",[(self.rid,now())]*99)
        def request():
            try:serper_search(self.store,self.rid,self.token,'query',self.check);return True
            except ValueError:return False
        with patch('sales.search_trial.transport',return_value={'organic':[]}),ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:request(),range(3)))
        self.assertEqual(sum(results),1);self.assertEqual(state(self.store)['used'],100)
    def test_stop_prevents_requests_and_late_results(self):
        TrialManager(self.store).stop()
        with patch('sales.search_trial.transport') as transport:
            with self.assertRaises(InterruptedError):serper_search(self.store,self.rid,self.token,'query',self.check)
        transport.assert_not_called();self.assertEqual(state(self.store)['used'],0)
    def test_stop_during_transport(self):
        def check():
            if not state(self.store)['running']:raise InterruptedError()
        def response(*a):TrialManager(self.store).stop();return {'organic':[]}
        with patch('sales.search_trial.transport',side_effect=response):
            with self.assertRaises(InterruptedError):serper_search(self.store,self.rid,self.token,'query',check)
        self.assertEqual(state(self.store)['used'],1)
    def test_balanced_shared_sample(self):
        queries=[{'provider':p,'strategy':'change','query':q,'results':[{'url':'https://'+url} for url in urls]} for p,q,urls in [('serper','q1',['a.it','b.it']),('serper','q2',['c.it','d.it']),('searxng','q1',['a.it','e.it'])]]
        result=sample(queries,2)
        self.assertEqual([x['url'] for x in result],['https://a.it','https://c.it','https://e.it'])
        self.assertEqual(result[0]['providers'],['serper','searxng'])
    def test_metrics_do_not_call_pages_qualified(self):
        report={'queries':[],'candidates':[{'url':'https://a.it/one','providers':['serper'],'triage':{'state':'promising'},'identity':{'identity_status':'verified'}},{'url':'https://a.it/two','providers':['serper'],'triage':{'state':'rejected'},'identity':{'identity_status':'verified'}}]}
        m=metrics(report,{})[0];self.assertEqual(m['verified_companies'],1);self.assertEqual(m['qualified'],0);self.assertEqual(m['reviewed'],0)
    def test_worker_isolated_and_no_false_qualification(self):
        responses=[{'url':'https://example.org/','title':'Test'}]
        with patch('sales.search_trial_worker.serper_search',return_value=responses),patch('sales.search_trial_worker.searxng_search',return_value=(responses,[])),patch('sales.search_trial_worker.time.sleep'),patch('sales.search_trial_worker.triage',return_value={'state':'rejected','reason':'Evento privo di bisogno digitale','details':{}}):
            run(str(self.store.path),self.rid,self.token)
        value=state(self.store);self.assertEqual(value['run']['state'],'completed')
        self.assertEqual(value['run']['metrics'][0]['qualified'],0)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM companies').fetchone()[0],0)
    def test_review_rejects_false_confirmation(self):
        self.report['candidates']=[{'url':'https://example.org','providers':['serper'],'triage':{'state':'rejected'}}]
        with self.store.connect() as c:c.execute("UPDATE search_trials SET state='completed',report=? WHERE id=?",(encode(self.report),self.rid))
        with self.assertRaises(ValueError):review(self.store,{'url':'https://example.org','verdict':'confirmed','reason':'Una nota sufficiente'})
        result=review(self.store,{'url':'https://example.org','verdict':'correct_rejection','reason':'Nessun progetto completo documentato'})
        self.assertEqual(result['run']['metrics'][0]['confirmed'],0)

    def test_publisher_identity_search_reaches_company_without_crm_promotion(self):
        source='https://editore.example/notizia';company='https://alfa.example/'
        def results(*args):
            query=args[-2] if len(args)==5 else args[-2]
            return [{'url':company if 'ufficiale' in query else source,'title':'Alfa'}]
        def preliminary(store,payload,check):
            return {'state':'needs_review' if payload['url']==source else 'promising','resolve':payload['url']==source,'reason':'Prova','details':{'publisher':payload['url']==source}}
        def inspect(store,payload,check,progress):
            if payload['url']==source:
                return {'publisher':True,'discovered':[],'resolve_queries':[{'query':'Alfa sito ufficiale','subject':'Alfa','source_documents':[],'strategy':'change'}]}
            self.assertEqual(payload['subject'],'Alfa');self.assertEqual(payload['parent_url'],source)
            return {'identity':{'name':'Alfa','identity_status':'unknown'},'documents':[],'assessment':{'status':'unverifiable','why':'Identità incompleta'}}
        with patch('sales.search_trial_worker.serper_search',side_effect=results),patch('sales.search_trial_worker.searxng_search',side_effect=lambda *args:(results(*args),[])),patch('sales.search_trial_worker.time.sleep'),patch('sales.search_trial_worker.triage',side_effect=preliminary),patch('sales.search_trial_worker.inspect_candidate',side_effect=inspect) as deep:
            run(str(self.store.path),self.rid,self.token)
        report=state(self.store)['run']['report']
        self.assertEqual(deep.call_count,2)
        child=next(c for c in report['candidates'] if c['url']==company)
        self.assertEqual(child['assessment']['status'],'unverifiable')
        self.assertEqual(len([q for q in report['queries'] if q.get('purpose')=='identity']),2)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM companies').fetchone()[0],0)


if __name__=='__main__':unittest.main()
