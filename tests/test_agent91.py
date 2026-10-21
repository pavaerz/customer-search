"""9.1 saved-campaign regressions and synthetic offline integration.

Only the eleven fixture records are acquired evidence. Synthetic fixtures and
provider doubles demonstrate behavior, not customers, cost savings or sales.
"""
import copy,json,unittest
from datetime import datetime,timezone
from unittest.mock import patch
from scripts.replay_agent91 import load,replay_case,report
from sales.agent6 import completion,schema,memory,scheduling,activity
from sales.agent6.worklist import listing
from sales.agent6.source_subjects import directory_subjects
from sales.research_analysis import identity_from
from sales.db import digest,encode,now
import test_agent6_campaign32 as support

CASES={c['record']['id']:c for c in load()['cases']}


class SavedCampaign39(unittest.TestCase):
    def test_first_read_keeps_invitation_legal_owner_and_contact_in_input(self):
        from sales.agent6.passages import bundle
        s=CASES[369]['record']['body']['documents'][0]
        ev=bundle([{'id':'r1',**s}]);text='\n'.join(e['text'] for e in ev)
        self.assertIn('Kondividi Srls',text);self.assertIn('consulenza@kondividi.it',text)
        self.assertIn('cerchiamo collaboratori',text);self.assertIn('partita IVA attiva',text)
        self.assertLessEqual(sum(len(e['text'].encode()) for e in ev),4500)
        short={'id':'r1','url':'https://alfa.example','original':True,'text':'Alfa Srl\nCerchiamo sviluppatori WordPress freelance.\ninfo@alfa.example'}
        self.assertIn('Cerchiamo sviluppatori','\n'.join(e['text'] for e in bundle([short])))

    def test_kondividi_first_actual_output_completes_facts_without_second_inference(self):
        b=replay_case(CASES[369])
        self.assertEqual(b['entity_name'],'Kondividi Srls')
        self.assertEqual(b['title'],CASES[369]['record']['body']['title'])
        self.assertTrue(b['identity_verified']);self.assertTrue(b['completion_queue']['promising'])
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertEqual(b['budget']['kind'],'UNKNOWN')
        self.assertEqual(b['completion_queue']['current_availability'],'UNKNOWN')
        self.assertIn('consulenza@kondividi.it',[c['value'] for c in b['contacts']])
        self.assertTrue({'entity','request','technical','contract','contact'} <= {f['field'] for f in b['facts']})
        text=CASES[369]['record']['body']['documents'][0]['text']
        for f in b['facts']:
            if f.get('document_start') is not None:self.assertEqual(f['quote'],text[f['document_start']:f['document_end']])
        self.assertEqual(b['replay']['new_ai_calls'],0)

    def test_customer_partner_is_not_external_recruitment(self):
        b=replay_case(CASES[420]);self.assertEqual(b['state'],'REJECTED')
        self.assertEqual(b['relationship_check']['status'],'CUSTOMER_PARTNERSHIP')

    def test_nontechnical_volunteering_is_not_paid_development(self):
        b=replay_case(CASES[485]);self.assertEqual(b['state'],'REJECTED');self.assertIsNone(b['entity_name'])
        self.assertEqual(b['relationship_check']['status'],'NONTECHNICAL_VOLUNTEERING')

    def test_diapason_unknown_contract_survives(self):
        b=replay_case(CASES[342]);self.assertEqual(b['state'],'DISCOVERED')
        self.assertNotEqual(b['kind'],'EMPLOYEE_JOB');self.assertIn('contract',b['missing'])
        from sales.agent6.commercial_policy import investigation
        self.assertTrue(investigation(b,initial=True)['allowed'])

    def test_blu_portal_management_is_not_invented_web_development(self):
        b=replay_case(CASES[449]);self.assertEqual(b['state'],'NEEDS_REVIEW')
        self.assertEqual(b['kind'],'UNKNOWN');self.assertIn('technical',b['missing'])

    def test_training_sources_stop_before_browser(self):
        for rid in (330,332):
            b=replay_case(CASES[rid]);self.assertFalse(b['commercial_fit']['audit_allowed'])
            self.assertEqual(b['commercial_fit']['source_role'],'training_provider')
            self.assertFalse(b['identity_verified'])

    def test_employee_training_does_not_turn_a_manufacturer_into_a_school(self):
        from sales.commercial.target_fit import source_role
        self.assertEqual(source_role('https://alfa.example/','Alfa Srl - serramenti',
            'Produciamo serramenti su misura. Investiamo nella formazione professionale dei nostri dipendenti.'),'company_candidate')

    def test_directory_publisher_is_not_client(self):
        b=replay_case(CASES[398]);self.assertFalse(b['identity_verified'])
        self.assertIsNone(b['official_domain']);self.assertFalse(b['commercial_fit']['audit_allowed'])

    def test_annatura_named_subject_not_seo_title_or_web_demand(self):
        b=replay_case(CASES[359]);self.assertEqual(b['entity_name'],'Annatura')
        self.assertFalse(b['identity_verified']);self.assertEqual(b['kind'],'COMPANY_SIGNAL')
        self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))

    def test_partial_browsers_retain_actual_measurements_without_new_defects(self):
        for rid in (334,395):
            b=replay_case(CASES[rid]);self.assertEqual(b['website_audit'],CASES[rid]['record']['body']['website_audit'])
            self.assertEqual(b['website_audit']['browser_status'],'PARTIAL')
            self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))

    def test_replay_has_no_network_or_database_access(self):
        with patch('socket.create_connection',side_effect=AssertionError('Offline')),patch('sqlite3.connect',side_effect=AssertionError('Frozen fixture only')):
            r=report()
        self.assertEqual(r['replay_91']['qualified'],0);self.assertEqual(r['replay_91']['promising'],1)
        self.assertEqual(r['replay_91']['reviewed_cases'],11)

    def test_legal_owner_not_provider_credit_or_ambiguous_owner(self):
        self.assertIsNone(completion.legal_identity('Realizzato da Alfa Srl'))
        self.assertIsNone(completion.legal_identity('proprietà di Alfa Srl; proprietà di Beta Srl'))
        self.assertEqual(completion.legal_identity('Copyright: proprietà di Alfa Srls')['name'],'Alfa Srls')

    def test_legal_publisher_does_not_replace_a_different_cited_subject(self):
        text='Acme Srl\nAnnuncia una nuova linea.\nCopyright di proprietà di Editore Srl'
        source={'url':'https://editore.example/','title':'Comunicati','text':text,'original':True}
        ev=schema.bundle([{'id':'r1',**source}]);e=ev[0];a={'result_id':'r1','kind':'COMPANY_SIGNAL','kind_ref':None,
            'facts':[{'field':'entity','ref':{'id':e['id'],'start':0,'end':8}}],'missing':[],'hypothesis':''}
        out,pool,identity,diag=completion.prepare(source,a,ev,{'name':'Editore Srl','identity_status':'verified','website':'https://editore.example/'})
        self.assertEqual(schema.quote(out['facts'][0]['ref'],pool)['quote'],'Acme Srl')
        self.assertEqual(diag['blocked_reason'],'cited_subject_differs_from_site_owner')

    def test_directory_retains_only_named_structured_external_subjects(self):
        graph={'@type':'ItemList','itemListElement':[{'@type':'ListItem','item':{'@type':'Organization','name':'Alfa Srl','url':'https://alfa.example/'}},
            {'@type':'Organization','name':'Publisher Srl','url':'https://directory.example/'},
            {'@type':'Organization','name':'Beta Srl','url':'https://beta.example/catalog.pdf'}]}
        page={'url':'https://directory.example/','html':'<script type="application/ld+json">'+json.dumps(graph)+'</script>'}
        result=directory_subjects(page);self.assertEqual(len(result),1)
        self.assertEqual(result[0]['name'],'Alfa Srl');self.assertIn('unverified',result[0]['basis'])


class Integration(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp();self.addCleanup(self.base.tearDown)
        self.store=self.base.store;self.c=self.base.c;self.rs=self.base.rs

    def test_literal_direct_invitation_skips_screen_and_queues_original(self):
        item={'url':'https://alfa.example/collabora','title':'Alfa Web Agency',
            'content':'Cerchiamo freelance WordPress per realizzare siti completi.'}
        q=support.query('agenzia cerca freelance WordPress Italia')
        with patch('sales.agent6.coordinator.acquire',return_value=[item]),patch.object(self.base.w,'model',side_effect=AssertionError('Unnecessary screen')):
            self.base.w._execute({'id':991,'kind':'search','strategy':'AGENCIES','payload':q},lambda:None)
        with self.store.connect() as c:
            tasks=c.execute('select kind,state from research_tasks').fetchall()
            self.assertEqual([(r['kind'],r['state']) for r in tasks],[('candidate','pending')])
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions').fetchone()[0],0)

    def test_saved_training_pages_never_reach_browser_or_model(self):
        for rid in (330,332):
            case=CASES[rid];pages={p['url']:p for p in case['pages']}
            url=case['record']['body']['url']
            self.rs.enqueue(self.c['id'],'candidate','AZIENDE',{'url':url,'query':'produttori alimentari','proactive':True},'training:'+str(rid))
            with patch('sales.agent6.proactive.CompanyWeb.get',side_effect=lambda u:pages[u]) as reads,patch('sales.commercial.browser.review',side_effect=AssertionError('Wrong audit subject')),patch.object(self.base.w,'model',side_effect=AssertionError('Wrong AI subject')):
                task=self.rs.claim(self.c['id'],self.c['generation']);self.base.w.execute(task,lambda:None);self.rs.task_done(task['id'])
            self.assertLessEqual(reads.call_count,2)
        with self.store.connect() as c:
            for r in c.execute('select body from agent6_records'):
                b=json.loads(r[0]);self.assertFalse(b['identity_verified']);self.assertFalse(b['commercial_fit']['audit_allowed'])

    def test_deep_audit_only_after_major_measurement_with_remaining_resources(self):
        from sales.agent6.audit_depth import plan,merge
        b={'completed':True,'elapsed_ms':30000,'resource_requests':40,'resources_closed':True,
            'pages':[{'url':'https://alfa.example/','viewport':390,'complete':True,'scope':'rendered'},
                     {'url':'https://alfa.example/','viewport':1366,'complete':True,'scope':'rendered'}],
            'findings':[{'url':'https://alfa.example/','code':'mobile_content','severity':'major'}]}
        pages=[{'url':'https://alfa.example/prodotti','status':200,'purpose':'offering'}]
        p=plan(b,pages,{'max_browser_pages':3,'browser_max_resources':60,'browser_total_seconds':120})
        self.assertEqual(p['resources'],20);self.assertEqual(p['seconds'],90)
        self.assertIsNone(plan({**b,'completed':False},pages,{}))
        self.assertIsNone(plan({**b,'findings':[]},pages,{}))
        self.assertIsNone(plan({**b,'resource_requests':60},pages,{}))
        partial=merge(b,{'completed':False,'resources_closed':True,'elapsed_ms':1000,'resource_requests':2,'pages':[],'failure_codes':['robots']})
        self.assertFalse(partial['completed']);self.assertEqual(partial['resource_requests'],42)
        self.assertEqual(len(partial['pages']),2)

    def test_original_worker_saved_output_to_promising_worklist_and_crossflow_dedup(self):
        case=CASES[369];page=case['pages'][0]
        result=next(a['response'] for a in case['ai_executions'] if a['response'].get('task')==schema.READ)
        calls=[]
        def saved(*args,**kwargs):calls.append(args);return copy.deepcopy(result)
        self.base.w.campaign['filters']['regions']=['Emilia-Romagna']
        with patch.object(self.base.w,'model',side_effect=saved),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('No fetch')),patch('socket.create_connection',side_effect=AssertionError('Offline')):
            for flow in ('AGENCIES','STARTUPS'):
                self.rs.enqueue(self.c['id'],'candidate',flow,{'url':page['url'],'original_page':page,'query':'saved campaign 39','depth':3},'saved:'+flow)
                task=self.rs.claim(self.c['id'],self.c['generation']);self.base.w.execute(task,lambda:None);self.rs.task_done(task['id'])
        # Duplicate original can reuse the dossier, never create a second lead.
        found=listing(self.store,{'view':'promising','group':'company'},datetime(2026,10,19,22,tzinfo=timezone.utc))
        self.assertEqual(found['total'],1);b=found['items'][0]['body']
        self.assertEqual(b['entity_name'],'Kondividi Srls');self.assertTrue(b['completion_queue']['missing_checks'])
        self.assertEqual(found['counts']['ready'],0)
        with self.store.connect() as c:
            self.assertEqual(c.execute('select count(*) from agent6_records').fetchone()[0],1)
            self.assertEqual(c.execute("select count(*) from research_tasks where fingerprint like 'agent-verify-repair:%'").fetchone()[0],0)
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')
        self.assertLessEqual(len(calls),2)  # saved doubles, not provider spend
        rid=found['items'][0]['id'];memory.feedback(self.store,rid,'interesting','Invito verificato, disponibilità da chiedere')
        self.assertEqual(listing(self.store,{'view':'promising'})['total'],1)
        memory.feedback(self.store,rid,'not_interesting','Non contattare')
        self.assertEqual(listing(self.store,{'view':'promising'})['total'],0)
        self.assertEqual(listing(self.store,{'view':'excluded'})['total'],1)

    def test_scheduler_prefers_saved_original_then_guarantees_fair_turn(self):
        self.rs.enqueue(self.c['id'],'candidate','AZIENDE',{'url':'https://a.example','prior':{'facts':[]}},'new')
        self.rs.enqueue(self.c['id'],'candidate','AGENCIES',{'url':'https://b.example','original_page':{'url':'https://b.example'},'prior':{'completion_queue':{'promising':True},'missing':['publication']}},'finish')
        with self.store.connect() as c:
            task,why=scheduling.choose(c,self.c,now());self.assertEqual(why['flow'],'AGENCIES');self.assertTrue(why['original_saved'])
            c.execute("update research_tasks set attempts=8 where strategy='AGENCIES'")
            task,why=scheduling.choose(c,self.c,now());self.assertEqual(why['flow'],'AZIENDE');self.assertTrue(why['fairness_turn'])

    def test_stop_resume_keeps_original_and_completion_dependencies(self):
        self.rs.enqueue(self.c['id'],'candidate','AGENCIES',{'url':'https://a.example','original_page':{'url':'https://a.example','html':'saved'},'prior':{'missing':['contact']}},'resume')
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.assertIsNone(self.rs.claim(self.c['id'],self.c['generation']))
        resumed=self.rs.resume(self.c['id']);task=self.rs.claim(resumed['id'],resumed['generation'])
        self.assertEqual(task['payload']['original_page']['html'],'saved');self.assertEqual(task['payload']['prior']['missing'],['contact'])

    def test_unknown_kind_keeps_valid_facts_without_source_validation_relaxation(self):
        text='Alfa Srl\nCerchiamo collaboratori.\nInformazioni generali.'
        src={'id':'r1','url':'https://alfa.example','text':text,'original':False}
        ev=schema.bundle([src]);e=ev[0]
        ref=lambda q:{'id':e['id'],'start':e['text'].index(q),'end':e['text'].index(q)+len(q)}
        a={'result_id':'r1','kind':'AGENCY_PARTNERSHIP','kind_ref':None,'facts':[{'field':'entity','ref':ref('Alfa Srl')}],'missing':[],'hypothesis':''}
        output,errors=schema.validate_fields(a,{'task':schema.SCREEN,'result_ids':['r1'],'evidence':ev})
        self.assertEqual(output['analyses'][0]['kind'],'UNKNOWN');self.assertEqual(len(output['analyses'][0]['facts']),1)
        self.assertTrue(errors)
        broken=copy.deepcopy(ev);broken[0]['hash']='wrong'
        invalid,issues=schema.validate_fields(a,{'task':schema.SCREEN,'result_ids':['r1'],'evidence':broken})
        self.assertEqual(invalid['analyses'][0]['facts'],[])
        self.assertTrue(any(e['code']=='wrong_source' for e in issues))

    def test_no_field_repair_for_unknown_identity_without_new_proof(self):
        b={'state':'NEEDS_REVIEW','original':True,'facts':[],'commercial_signals':[]}
        self.assertEqual(completion.repair_fields({'field_errors':[{'field':'entity','code':'unsupported_actor'}]},b),[])
        self.assertEqual(completion.repair_fields({'field_errors':[{'field':'contact'}]},replay_case(CASES[369])),[])

    def test_useful_metrics_do_not_call_urls_customers(self):
        b=replay_case(CASES[369]);b['request_key']='k';row={'id':1,'campaign_id':1,'request_key':'k','body':b,'state':b['state']}
        m=activity.measures([row]);self.assertEqual(m['promising_dossiers'],1)
        self.assertEqual(m['qualified_companies'],0);self.assertEqual(m['companies_with_public_contact'],1)
        self.assertIsNone(m['sales_conversion'])


if __name__=='__main__':unittest.main()
