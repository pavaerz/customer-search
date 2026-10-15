"""Offline acceptance cases for the search foundation; every database is temporary."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.discovery_planner import Planner
from sales.research_discovery import search


class PlannerFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.store.init()
        self.store.configure({'provider':'serper'})
        self.rs=ResearchStore(self.store);self.c=self.rs.create({'regions':['Veneto']})
        self.planner=Planner(self.rs);self.f=Funnel(self.rs)
        self.variants=patch('sales.discovery_planner.variants',return_value=iter([]))
        with self.store.connect() as c:
            c.execute("INSERT INTO discovery_branches(campaign_id,strategy,region) VALUES (?,'companies','Veneto')",(self.c['id'],))
    def tearDown(self):self.tmp.cleanup()
    def tick(self):
        with patch('sales.discovery_planner.variants',return_value=iter(['produttori Veneto','aziende Lombardia'])):
            return self.planner.tick(self.c)
    def latest(self):
        with self.store.connect() as c:
            r=c.execute("SELECT * FROM discovery_frontier WHERE kind='search' ORDER BY id DESC LIMIT 1").fetchone()
        return {**dict(r),'payload':json.loads(r['payload'])}
    def test_nine_seen_one_unreachable_continues_next_query(self):
        self.tick();task=self.latest()
        urls=[f'https://company{i}.example/' for i in range(10)]
        with self.store.connect() as c:
            for url in urls[:9]:c.execute('INSERT INTO research_visited VALUES (?,?,?)',(url,now(),now()))
        with patch('sales.serper_provider.search',return_value=({'results':[{'url':u,'title':'Produzione componenti'} for u in urls]},False)):
            result=search(self.rs,self.c,task,lambda:None)
        self.assertEqual(result['urls'],urls[9:])
        self.f.transition(self.c,{'url':urls[9],'strategy':'companies'},'unverifiable','Connessione non disponibile')
        with self.store.connect() as c:c.execute("UPDATE discovery_frontier SET state='done' WHERE kind='candidate'")
        self.assertEqual(self.tick(),1)
        self.assertNotEqual(task['payload']['query'],self.latest()['payload']['query'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT state,dry_streak FROM discovery_branches').fetchone()[:],('active',0))
    def test_empty_and_duplicates_advance_then_exhaust_without_restart(self):
        self.tick();self.planner.observed(self.c,self.latest(),[],0)
        self.assertEqual(self.tick(),1)
        self.planner.observed(self.c,self.latest(),[],0)
        self.assertEqual(self.tick(),0)
        self.assertEqual(self.tick(),0)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM discovery_branches').fetchone()[0],'exhausted')
            self.assertEqual(c.execute('SELECT count(*) FROM discovery_queries').fetchone()[0],2)
    def test_provider_pause_is_separate_and_recovers(self):
        from sales.discovery_control import record_health
        record_health(self.store,'serper','Temporary outage')
        self.assertEqual(self.tick(),0)
        record_health(self.store,'serper')
        self.assertEqual(self.tick(),1)
    def test_resume_old_local_pause_and_keep_completed_queries(self):
        self.tick();task=self.latest();self.planner.observed(self.c,task,[],0)
        with self.store.connect() as c:
            c.execute("UPDATE discovery_branches SET state='paused',reason='Fonti non verificabili: ramo sospeso, nessuna conclusione sul mercato.'")
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id'])
        self.planner.adopt(self.c)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM discovery_branches WHERE strategy='companies'").fetchone()[0],'active')
            c.execute("UPDATE discovery_branches SET state='retired' WHERE strategy<>'companies'")
        self.assertEqual(self.tick(),1)
        self.assertNotEqual(self.latest()['payload']['query'],task['payload']['query'])
    def test_stop_prevents_enqueue_and_late_results(self):
        self.tick();old=self.c
        self.rs.stop(old['id'])
        self.assertEqual(self.tick(),0)
        self.assertFalse(self.f.transition(old,{'url':'https://late.example/'},'promising','Late result'))

    def test_only_known_urls_are_not_an_empty_market(self):
        self.tick();task=self.latest();url='https://alfa.example/'
        with self.store.connect() as c:c.execute('INSERT INTO research_visited VALUES (?,?,?)',(url,now(),now()))
        with patch('sales.serper_provider.search',return_value=({'results':[{'url':url,'title':'Produzione componenti'}]},True)):
            self.assertEqual(search(self.rs,self.c,task,lambda:None)['new_urls'],0)
        self.assertEqual(self.tick(),1)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT decision FROM discovery_queries ORDER BY rowid LIMIT 1').fetchone()[0],'known_results')
            self.assertEqual(c.execute('SELECT dry_streak FROM discovery_branches').fetchone()[0],0)

    def test_missing_credentials_block_worker_once_without_network(self):
        from sales.research_worker import run
        self.rs.event(self.c['id'],'frontier_initialized','Fixture')
        with patch('sales.discovery_planner.variants',return_value=iter(['aziende Veneto'])),patch('sales.serper_provider.api_key',return_value=''),patch('sales.serper_provider.transport') as transport:
            run(self.store.path,self.c['id'],self.c['generation'])
        transport.assert_not_called()
        self.assertEqual(self.rs.campaign(self.c['id'])['status'],'blocked')
        with self.store.connect() as c:
            rows=c.execute('SELECT details FROM discovery_operations').fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(json.loads(rows[0][0])['scope'],'provider')
        self.assertEqual(json.loads(rows[0][0])['outcome'],'not_executed')

class OrganizationFoundationTests(unittest.TestCase):
    def page(self,title,text=''):
        return {'url':'https://alfa.example/','status':200,'checked_at':now(),'html':f'<title>{title}</title><h1>{title}</h1><p>{text}</p>'}
    def test_public_hospital_is_not_private(self):
        from sales.organization import classify
        c=classify([self.page('Homepage ULSS1 Dolomiti','Servizi sanitari e prenotazioni')],{'identity_status':'verified'})
        self.assertEqual(c['category'],'public_body');self.assertTrue(c['evidence'])
        self.assertEqual(c['commercial_opportunity'],'not_established')
    def test_directory_and_agency(self):
        from sales.organization import classify
        self.assertEqual(classify([self.page('Directory delle aziende italiane')])['category'],'directory')
        self.assertEqual(classify([self.page('Alfa web agency','Realizziamo siti web e applicazioni.')])['category'],'digital_agency')
    def test_manufacturer_without_request_and_incidental_public_client(self):
        from sales.organization import classify
        c=classify([self.page('Alfa Srl','Produciamo componenti per ULSS1 Dolomiti.')],{'identity_status':'verified'})
        self.assertEqual(c['category'],'private_company')
        self.assertEqual(c['commercial_opportunity'],'not_established')
    def test_generic_services_and_unverified_startup_remain_unknown(self):
        from sales.organization import classify
        self.assertEqual(classify([self.page('Servizi per tutti')])['category'],'unidentified')
        self.assertEqual(classify([self.page('Startup innovativa Alfa')])['category'],'unidentified')
    def test_public_body_never_reaches_local_model(self):
        from sales.research_analysis import inspect_candidate,ResearchWeb,LocalResearcher
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite3');store.init()
            with patch.object(ResearchWeb,'get',return_value=self.page('ULSS1 Dolomiti','Servizi')),patch.object(LocalResearcher,'analyze') as model:
                result=inspect_candidate(store,{'url':'https://alfa.example/'},lambda:None)
            model.assert_not_called();self.assertEqual(result['assessment']['status'],'rejected')

class ReviewBudgetTests(unittest.TestCase):
    setUp=PlannerFoundationTests.setUp
    tearDown=PlannerFoundationTests.tearDown
    def test_unchanged_failed_review_not_requeued_but_new_evidence_is(self):
        payload={'url':'https://alfa.example/','company_host':'alfa.example','company_key':'legal1','official_link':True,'source_documents':[{'id':'d','text':'Produzione attuale'}]}
        self.assertTrue(self.f.offer(self.c['id'],'verify','companies',payload,'one'))
        self.f.fill(self.c);task=self.rs.claim(self.c['id'],self.c['generation']);self.rs.task_done(task['id'],'Permanent missing evidence')
        self.assertFalse(self.f.offer(self.c['id'],'verify','companies',payload,'different-key'))
        self.assertTrue(self.f.offer(self.c['id'],'verify','companies',{**payload,'source_documents':[{'id':'new','text':'Nuovo portale B2B richiesto'}]},'new-proof'))
        with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM discovery_frontier WHERE kind='verify'").fetchone()[0],2)

    def test_budget_is_bounded_and_changed_policy_allows_targeted_review(self):
        from sales.evaluation_policy import RULES
        payload={'url':'https://alfa.example/','company_host':'alfa.example','company_key':'legal1','official_link':True}
        for index in range(8):
            p={**payload,'source_documents':[{'text':f'Prova distinta {index}'}]}
            self.assertTrue(self.f.offer(self.c['id'],'verify','companies',p,str(index)))
            self.f.fill(self.c);task=self.rs.claim(self.c['id'],self.c['generation']);self.rs.task_done(task['id'])
        self.assertFalse(self.f.offer(self.c['id'],'verify','companies',{**payload,'source_documents':[{'text':'Nona prova'}]},'nine'))
        with patch.dict(RULES,{'context':2}):
            self.assertTrue(self.f.offer(self.c['id'],'verify','companies',p,'new-policy'))

class DocumentRequirementTests(unittest.TestCase):
    def inspect(self,path,contact=True,original=False):
        from sales.research_analysis import inspect_candidate,ResearchWeb,LocalResearcher
        legal='<title>Alfa Srl</title><p>Via Roma 1, 35100 Padova (PD)</p><p>P.IVA 12345678901</p>'
        if contact:legal+='<a href="mailto:info@alfa.example">info@alfa.example</a>'
        html=legal+'<p>Produzione di componenti e servizi industriali</p><a href="/'+path+'">'+path+'</a>'
        def read(web,url):
            if url.endswith('/'+path):raise ValueError('Accesso escluso da robots.txt')
            return {'url':url,'html':html,'status':200,'checked_at':now()}
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite3');store.init()
            with patch.object(ResearchWeb,'get',read),patch.object(LocalResearcher,'analyze',return_value=([],{},{},[])) as model:
                result=inspect_candidate(store,{'url':'https://alfa.example/'+(path if original else ''),'strategy':'companies'},lambda:None)
        return result['assessment'],model.call_count
    def test_privacy_failure_is_recorded_but_independent_analysis_continues(self):
        a,calls=self.inspect('privacy')
        self.assertEqual(calls,1);self.assertFalse(a['page_failures'][0]['blocking'])
        self.assertFalse(a['coverage']['solutions'])  # attempted privacy is not a reviewed solution
        self.assertTrue(a['coverage']['identity']);self.assertNotEqual(a['status'],'qualified')
    def test_contact_failure_without_alternative_is_blocking(self):
        a,_=self.inspect('contatti',contact=False)
        self.assertTrue(a['page_failures'][0]['blocking']);self.assertFalse(a['coverage']['contact'])
        self.assertNotEqual(a['status'],'qualified')
    def test_contact_alternative_on_homepage_resolves_only_contact_requirement(self):
        a,calls=self.inspect('contatti')
        self.assertEqual(calls,1);self.assertFalse(a['page_failures'][0]['blocking'])
    def test_original_source_failure_never_becomes_optional(self):
        with self.assertRaises(ValueError):self.inspect('privacy',original=True)
    def test_required_counterproof_cannot_be_replaced_by_contact(self):
        a,_=self.inspect('shop')
        self.assertTrue(a['page_failures'][0]['blocking']);self.assertFalse(a['coverage']['solutions'])

    def test_multiple_available_pages_replace_optional_legal_page(self):
        from sales.research_analysis import inspect_candidate,ResearchWeb,LocalResearcher
        legal='<title>Alfa Srl</title><p>P.IVA 12345678901</p><p>Via Roma 1, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">Contatto</a>'
        def read(web,url):
            if url.endswith('/privacy'):raise TimeoutError('Privacy temporaneamente non disponibile')
            body=legal+('<a href="/prodotti">Prodotti</a><a href="/contatti">Contatti</a><a href="/privacy">Privacy</a>' if url.endswith('/') else '<p>Prodotti industriali e servizi tecnici.</p>')
            return {'url':url,'html':body,'status':200,'checked_at':now()}
        captured=[]
        def analyze(owner,identity,docs,coverage):
            captured.extend(d['url'] for d in docs)
            return [],{},{},[]
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite3');store.init()
            with patch.object(ResearchWeb,'get',read),patch.object(LocalResearcher,'analyze',analyze):
                result=inspect_candidate(store,{'url':'https://alfa.example/'},lambda:None)
        self.assertIn('https://alfa.example/prodotti',captured)
        self.assertIn('https://alfa.example/contatti',captured)
        self.assertTrue(result['assessment']['coverage']['identity'])
        self.assertTrue(result['assessment']['coverage']['solutions'])
        self.assertFalse(result['assessment']['page_failures'][0]['blocking'])
        self.assertNotEqual(result['assessment']['status'],'qualified')

class ContextFoundationTests(unittest.TestCase):
    def signals(self):
        return [{'id':str(i),'document_id':str(i),'kind':'request' if i==0 else 'counterevidence',
                 'quote':f'Citazione originale distinta numero {i}', 'url':f'https://alfa.example/{i}','official':True} for i in range(25)]
    def researcher(self,contrary=False,invalid=False,unavailable=False):
        from types import SimpleNamespace
        calls=[]
        def call(task,data,schema):
            calls.append(data)
            if unavailable:raise TimeoutError('Modello temporaneamente indisponibile')
            if invalid:return {'invented':'answer'}
            ids=[s['id'] for s in data['signals']]
            if 'project' in schema['properties']:
                return {'project':'website','why':'Richiesta','why_now':'Attuale','proposal':'Progetto completo','scope':'full_project','feasibility':'bounded','support_ids':['0'],'critical_unknowns':[],'objections':[],'budget_signal_id':''}
            return {'status':'contradicted' if contrary and '24' in ids else 'supported','support_ids':['0'],
                    'existing_solution_checked':True,'small_fix_sufficient':False,'reason':'Valutazione delle prove originali'}
        return SimpleNamespace(call=call,check=lambda:None),calls
    def test_25_duplicates_deduplicate_without_mutating_dossier(self):
        from sales.correlation_context import select
        signals=[self.signals()[0]]*25
        selected,note,limits=select(signals)
        self.assertEqual(len(selected),1);self.assertEqual(len(signals),25)
        self.assertEqual(note['duplicates_collapsed'],24);self.assertEqual(limits,[])
    def test_25_distinct_citations_all_reviewed(self):
        from sales.correlation_context import review_batches
        r,calls=self.researcher();signals=self.signals()
        proposal,review,limits=review_batches(r,{},signals,{'solutions':True})
        self.assertEqual(limits,[]);self.assertEqual(review['status'],'supported')
        self.assertEqual(set(review['context_selection']['reviewed_ids']),{s['id'] for s in signals})
        originals={s['id']:s['quote'] for s in signals}
        self.assertTrue(all(s['quote']==originals[s['id']] for c in calls for s in c['signals']))
        self.assertGreater(review['context_selection']['review_groups'],1)
    def test_last_group_counterproof_vetoes_the_whole_proposal(self):
        from sales.correlation_context import review_batches
        r,_=self.researcher(contrary=True)
        _,review,limits=review_batches(r,{},self.signals(),{})
        self.assertEqual(review['status'],'contradicted');self.assertEqual(limits,[])
    def test_invalid_output_and_unavailable_model_never_complete(self):
        from sales.correlation_context import review_batches
        for settings in ({'invalid':True},{'unavailable':True}):
            r,_=self.researcher(**settings)
            proposal,review,limits=review_batches(r,{},self.signals(),{})
            self.assertEqual(proposal,{});self.assertEqual(review['status'],'insufficient');self.assertTrue(limits)
    def test_fabricated_reference_fails_schema(self):
        from sales.correlation_context import review_batches
        r,_=self.researcher();original=r.call
        def bad(task,data,schema):
            result=original(task,data,schema);result['support_ids']=['invented'];return result
        r.call=bad
        _,review,limits=review_batches(r,{},self.signals(),{})
        self.assertTrue(limits);self.assertEqual(review['status'],'insufficient')
    def test_stop_interrupts_batch_and_does_not_become_model_error(self):
        from sales.correlation_context import review_batches
        r,_=self.researcher()
        def stop():raise InterruptedError('Stop')
        r.check=stop
        with self.assertRaises(InterruptedError):review_batches(r,{},self.signals(),{})

    def test_actual_analyzer_extracts_and_reviews_25_documents(self):
        from sales.research_analysis import LocalResearcher
        from test_research import sample
        identity,docs,_,_,_=sample()
        docs=docs[:1]+[{**docs[1],'id':str(i),'url':f'https://alfa.example/soluzione-{i}',
                       'text':f'Soluzione operativa {i}: catalogo{i} portale{i} clienti{i} attività{i} funzionalità{i}.'} for i in range(1,25)]
        calls=[]
        def call(task,data,schema):
            calls.append(data)
            if 'claims' in schema['properties']:
                return {'claims':[{'unit_id':data['units'][0]['id'],'kind':'request' if data['url']==docs[0]['url'] else 'counterevidence'}]}
            support=[s['id'] for s in data['signals'] if s['kind']=='request']
            if 'project' in schema['properties']:
                return {'project':'website','why':'Richiesta documentata','why_now':'Richiesta attuale','proposal':'Sito aziendale completo','scope':'full_project','feasibility':'bounded','support_ids':support,'critical_unknowns':[],'objections':[],'budget_signal_id':''}
            return {'status':'contradicted' if any(s['url'].endswith('soluzione-24') for s in data['signals']) else 'supported','support_ids':support,'existing_solution_checked':True,'small_fix_sufficient':False,'reason':'Controprova esaminata'}
        researcher=LocalResearcher(None)
        with patch.object(researcher,'call',side_effect=call),patch('sales.solution_evidence.eligible_units',return_value=[]):
            signals,proposal,review,limits=researcher.analyze(identity,docs,dict.fromkeys(('identity','contact','offer','solutions'),True))
        self.assertEqual(len(signals),25);self.assertEqual(limits,[])
        self.assertEqual(review['status'],'contradicted')
        self.assertEqual(set(review['context_selection']['reviewed_ids']),{s['id'] for s in signals})
        self.assertTrue(all(s['quote'] in next(d['text'] for d in docs if d['id']==s['document_id']) for s in signals))
        from sales.research_rules import qualify
        result=qualify(identity,docs,signals,proposal,review)
        self.assertEqual(result['status'],'rejected');self.assertIsNone(result['budget'])

    def test_oversized_work_is_explicitly_incomplete_without_truncation(self):
        from sales.correlation_context import review_batches
        r,calls=self.researcher()
        signals=[{**self.signals()[0],'id':str(i)} for i in range(300)]
        _,review,limits=review_batches(r,{},signals,{})
        self.assertTrue(limits);self.assertEqual(review['status'],'insufficient')
        self.assertEqual(calls,[]);self.assertEqual(len(signals),300)

class VersionedMemoryTests(unittest.TestCase):
    setUp=PlannerFoundationTests.setUp
    tearDown=PlannerFoundationTests.tearDown
    url='https://agency.example/careers/'
    def previous(self,version=None,reason='Fornitore di servizi digitali: non è un committente per questa ricerca.'):
        details={}
        ident=self.f.transition(self.c,{'url':self.url,'strategy':'partner'},'rejected',reason,details)
        with self.store.connect() as c:
            d=json.loads(c.execute('SELECT details FROM discovery_candidates WHERE id=?',(ident,)).fetchone()[0])
            if version is None:d.pop('evaluation_policy',None)
            else:d['evaluation_policy']['rules']['collaboration']=version
            c.execute('UPDATE discovery_candidates SET details=? WHERE id=?',(json.dumps(d),ident))
            c.execute('INSERT OR REPLACE INTO research_visited VALUES (?,?,?)',(self.url,now(),now()))
        return ident
    def search(self):
        task={'strategy':'partner','payload':{'query':'freelance wordpress Veneto','page':1,'period':''}}
        with patch('sales.serper_provider.search',return_value=({'results':[{'url':self.url,'title':'Lavora con noi WordPress freelance'}]},True)):
            return search(self.rs,self.c,task,lambda:None)
    def test_old_rule_reconsidered_once_without_duplicate_or_historical_rewrite(self):
        ident=self.previous(0)
        self.assertEqual(self.search()['new_urls'],1);self.assertEqual(self.search()['new_urls'],0)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM discovery_candidates WHERE id=?',(ident,)).fetchone()[0],'rejected')
            self.assertEqual(c.execute("SELECT count(*) FROM discovery_frontier WHERE kind='candidate'").fetchone()[0],1)
    def test_legacy_version_missing_is_targeted_not_global(self):
        from sales.evaluation_policy import reconsideration
        self.previous()
        self.assertIsNotNone(reconsideration(self.store,self.url,self.c['filters']))
        with self.store.connect() as c:c.execute("UPDATE discovery_candidates SET reason='Richiesta chiaramente non pertinente.'")
        self.assertIsNone(reconsideration(self.store,self.url,self.c['filters']))
    def test_same_rules_and_irrelevant_rule_change_do_not_repeat(self):
        from sales.evaluation_policy import reconsideration,RULES
        self.previous(1)
        self.assertEqual(self.search()['new_urls'],0)
        with patch.dict(RULES,{'context':99}):self.assertIsNone(reconsideration(self.store,self.url,self.c['filters']))
        with patch.dict(RULES,{'collaboration':2}):self.assertIsNotNone(reconsideration(self.store,self.url,self.c['filters']))
    def test_manual_rejection_and_do_not_contact_override_policy_change(self):
        from sales.evaluation_policy import reconsideration
        ident=self.previous(0)
        self.f.outcome('not_relevant',candidate_id=ident)
        self.assertIsNone(reconsideration(self.store,self.url,self.c['filters']))
        self.assertEqual(self.search()['new_urls'],0)
    def test_manually_deleted_domain_is_not_reconsidered(self):
        self.previous(0)
        with self.store.connect() as c:c.execute('INSERT INTO dismissed_companies VALUES (?,?)',('agency.example',now()))
        self.assertEqual(self.search()['new_urls'],0)

    def test_do_not_contact_and_previous_contact_are_preserved(self):
        self.previous(0)
        company=self.store.company(self.url,'Agency')
        for column in ('do_not_contact','prior_contacted'):
            with self.store.connect() as c:c.execute('UPDATE companies SET do_not_contact=0,prior_contacted=0,'+column+'=1 WHERE id=?',(company,))
            self.assertEqual(self.search()['new_urls'],0)
    def test_current_assessment_has_policy_legacy_rows_unchanged(self):
        from sales.research_rules import qualify
        from sales.evaluation_policy import stamp
        identity={'name':'Alfa','website':self.url,'identity_status':'unknown','contacts':[]}
        assessment=qualify(identity,[],[],{},{})
        aid=self.rs.save(self.c['id'],self.c['generation'],None,identity,[],assessment)
        self.assertEqual(self.rs.opportunity(aid)['assessment']['evaluation_policy'],stamp(self.c['filters']))

class ObservabilityFoundationTests(unittest.TestCase):
    setUp=PlannerFoundationTests.setUp
    tearDown=PlannerFoundationTests.tearDown
    def test_bad_query_does_not_mark_provider_unavailable(self):
        from sales.serper_provider import search as acquire
        from sales.search_trial import SerperHTTPError
        from sales.discovery_control import QueryError,health,available
        from sales.operation_outcomes import error_outcome
        with patch('sales.serper_provider.api_key',return_value='test-only'),patch('sales.serper_provider.transport',side_effect=SerperHTTPError(400,'Query non valida')):
            with self.assertRaises(QueryError) as raised:acquire(self.store,'invalid query')
        self.assertEqual(error_outcome(raised.exception,'search')['scope'],'query')
        self.assertTrue(available(self.store));self.assertEqual(health(self.store)['failures'],0)
        self.assertEqual(self.store.usage()['today']['serper'],1)

    def test_transport_success_is_not_a_qualified_opportunity(self):
        from sales.discovery_control import measure
        task={'kind':'candidate','strategy':'companies','payload':{'url':'https://alfa.example/'}}
        with measure(self.rs,self.c,task):
            self.f.transition(self.c,task['payload'],'unverifiable','Identità non verificabile')
        with self.store.connect() as c:row=c.execute('SELECT status,details FROM discovery_operations').fetchone()
        self.assertEqual(row['status'],'ok')
        detail=json.loads(row['details']);self.assertEqual(detail['outcome'],'unverifiable');self.assertFalse(detail['qualified'])
    def test_interrupted_temporary_permanent_and_not_executed_are_distinct(self):
        from sales.operation_outcomes import error_outcome
        from sales.discovery_control import ProviderDeferred
        from sales.access_status import AccessIssue
        cases=[(InterruptedError(),'interrupted'),(TimeoutError(),'temporary_error'),
               (AccessIssue('robots_denied','Denied'),'permanent_error'),(ProviderDeferred(),'not_executed')]
        for error,expected in cases:self.assertEqual(error_outcome(error,'candidate')['outcome'],expected)
    def test_error_logs_remove_credentials_and_personal_email(self):
        from sales.operation_outcomes import safe_error
        text=safe_error('URL https://user:secret@example.org/path?token=abcd api_key=xyz info@person.example')
        for secret in ('secret','abcd','xyz','info@person.example'):self.assertNotIn(secret,text)
    def test_query_outcomes_account_for_every_normalized_result(self):
        from sales.discovery_control import measure
        task={'kind':'search','strategy':'companies','payload':{'query':'produttori Veneto','page':1,'period':''}}
        response={'results':[None,{'url':'bad'}, {'url':'https://youtube.com/watch'}, {'url':'https://alfa.example/','title':'Produzione componenti'}]}
        with patch('sales.serper_provider.search',return_value=(response,True)),measure(self.rs,self.c,task):search(self.rs,self.c,task,lambda:None)
        with self.store.connect() as c:detail=json.loads(c.execute('SELECT details FROM discovery_operations').fetchone()[0])
        self.assertEqual(sum(detail['acquisition_outcomes'].values()),4)
        self.assertEqual(detail['acquisition_outcomes']['candidate'],1)
        self.assertFalse(detail['qualified'])
