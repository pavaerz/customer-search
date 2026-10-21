"""9.2: recorded inputs, bounded counterexamples and isolated queue tests."""
import copy
import json
import unittest
from unittest.mock import patch
from scripts.replay_agent92 import load,replay,report
from sales.agent6 import identity_aliases,query_pipeline as qp,commercial_policy,learning,qualification,memory,scheduling,budget,schema
from sales.commercial import target_fit
from sales.commercial.entity_scope import owner_fact
from sales.agent6.website_audit import audit
from sales.agent6.worklist import listing
from sales.db import now
import test_agent6_campaign32 as support
from test_agent6 import source,output,identity


class Frozen41(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.fixture=load()

    def test_nhw_identity_requirements_and_honest_incomplete_worklist(self):
        case=self.fixture['cases'][0];before=copy.deepcopy(case)
        with patch('socket.create_connection',side_effect=AssertionError('offline')):
            b=replay(case,self.fixture['configuration']['regions'])
        self.assertEqual(case,before)
        self.assertEqual(b['entity_name'],'NHW Consulting')
        self.assertTrue(b['identity_verified']);self.assertIn('NHWCONSULTING',b['identity_aliases'])
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertTrue(b['completion_queue']['promising'])
        self.assertEqual(set(b['missing']),{'publication'})
        self.assertIn('budget',b['optional_unknowns']);self.assertEqual(b['budget']['kind'],'UNKNOWN')
        self.assertEqual(b['completion_queue']['active_assignment'],'UNKNOWN')
        self.assertEqual(b['completion_queue']['contract_acquired'],'UNKNOWN')
        self.assertFalse(any(f['field']=='technical' for f in b['facts']))
        self.assertNotIn('WordPress',b['hypothesis'])
        self.assertNotIn('ecommerce',b['hypothesis'])
        self.assertTrue(b['model_hypothesis'])
        self.assertEqual(commercial_policy.investigation(b)['goal'],'publication')
        self.assertIn('site:nhwconsulting.it',commercial_policy.verification_query(b,'technical'))

    def test_punto_infissi_does_not_inherit_supplier_size(self):
        case=self.fixture['cases'][1];b=replay(case,self.fixture['configuration']['regions'])
        self.assertTrue(b['commercial_fit']['audit_allowed'])
        self.assertNotEqual(b['commercial_fit']['source_role'],'large_group')
        self.assertEqual(b['commercial_fit']['size']['status'],'UNKNOWN')
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertIn('No saved browser',b['replay_limit'])
        self.assertTrue(learning.contradicted_negative(case['record']['body']))

    def test_saved_social_receipts_trigger_counterfactual_suspension(self):
        result=report();blocked=result['queries_rejected_counterfactually']
        self.assertTrue(any(r['flow']=='SOCIAL' for r in blocked))
        self.assertTrue(any('balance' in r['reason'] for r in blocked))
        self.assertEqual(result['new_verified_opportunities'],0)

    def test_correcting_automatic_attribution_does_not_erase_human_relevance(self):
        case=self.fixture['cases'][1];r=case['record'];b=r['body']
        events=[{'id':1,'campaign_id':41,'flow':r['flow'],'kind':'decision','body':{
            'record_id':r['id'],'query':b['query'],'strategy':b['strategy'],'state':'REJECTED','negative_feedback_reliable':True}}]
        automatic=learning.summarize(events,[],{r['id']:b})[0]
        self.assertEqual(automatic['verified_rejections'],0)
        corrected=learning.summarize(events,[],{r['id']:b},{b['request_key']:{'relevance':{'value':'irrelevant'}}})[0]
        self.assertEqual(corrected['manually_irrelevant'],1)


class AliasSafety(unittest.TestCase):
    def match(self,name='Montagna Studio',alias='MONTAGNASTUDIO',url='https://montagnastudio.example/careers',**extra):
        ident={'name':name,'identity_status':'verified','website':'https://montagnastudio.example/'}
        src={'url':url,'original':True,'text':alias+'\n© Montagna Studio',**extra}
        return identity_aliases.match(ident,alias,src)

    def test_graphic_unicode_alias_keeps_both_names(self):
        b=self.match(alias='ＭＯＮＴＡＧＮＡＳＴＵＤＩＯ');self.assertTrue(b['matched'])
        self.assertEqual(b['public_name'],'Montagna Studio');self.assertEqual(b['original_name'],'ＭＯＮＴＡＧＮＡＳＴＵＤＩＯ')
        self.assertTrue(self.match(alias='Montagna.Studio')['matched'])

    def test_cross_domain_alias_and_initials_never_link(self):
        self.assertFalse(self.match(url='https://other.example/')['matched'])
        self.assertFalse(self.match(alias='Montagna Studio',url='https://other.example/')['matched'])
        self.assertFalse(self.match(alias='MS')['matched'])
        self.assertFalse(self.match(alias='Montagna Studi')['matched'])
        self.assertFalse(self.match(editorial=True)['matched'])
        self.assertFalse(self.match(document_units=[{'id':'ad1'}])['matched'])

    def test_global_exact_name_comparator_not_weakened(self):
        from sales.commercial.indexed_jobs import same_company_name
        self.assertFalse(same_company_name('AB C','A BC'))
        self.assertFalse(same_company_name('NHW Consulting','NHWCONSULTING'))


class RequirementsAndSources(unittest.TestCase):
    def agency(self,extra='',kind='AGENCY_PARTNERSHIP'):
        src=source('Alfa Srl\nPosted 2 days ago\nCerchiamo freelance WordPress per un nuovo sito. Remote from Italy.\n'+extra)
        p,o=output(src,kind,{'entity':'Alfa Srl','request':'Cerchiamo freelance WordPress per un nuovo sito. Remote from Italy.',
            'technical':'WordPress','contract':'freelance','geography':'Remote from Italy.'})
        o['analyses'][0]['missing']=['budget','digital_gap','signal','existing_solution']
        return qualification.evaluate(src,o['analyses'][0],p['evidence'],'AGENCIES',identity())

    def test_optional_unknowns_do_not_block_explicit_or_partnership(self):
        for kind,state in [('AGENCY_PARTNERSHIP','POTENTIAL'),('BUYER_DEMAND','VERIFIED')]:
            b=self.agency(kind=kind);self.assertEqual(b['state'],state);self.assertEqual(b['budget']['kind'],'UNKNOWN')

    def test_actual_low_budget_and_closed_request_still_excluded(self):
        for text in ('Budget: €500 fixed price','Applications closed.'):
            self.assertEqual(self.agency(text)['state'],'REJECTED')

    def test_third_party_size_is_not_owner_size(self):
        for text in ('Siamo partner di Gamma, una multinazionale con 1000 dipendenti.',
                     'Il cliente Gamma è una multinazionale con 1000 dipendenti.',
                     'Il nostro investitore Gamma è una multinazionale con 1000 dipendenti.'):
            self.assertFalse(target_fit.group_evidence(text,'Alfa Srl'))
            self.assertFalse(owner_fact(text,'Alfa Srl'))
        for text in ('Siamo una multinazionale con 1000 dipendenti.',
                     'Alfa Srl è una multinazionale con 1000 dipendenti.'):
            self.assertTrue(target_fit.group_evidence(text,'Alfa Srl'))

    def test_archives_rejected_but_specific_editorial_article_survives(self):
        for url in ('https://press.example/tag/azienda/','https://press.example/category/economia/'):
            self.assertFalse(commercial_policy.preflight({'url':url,'title':'Alfa lancia nuovi prodotti web'})['allowed'])
        self.assertTrue(commercial_policy.preflight({'url':'https://press.example/alfa-lancia-linea','title':'Alfa lancia nuova linea prodotti'})['allowed'])
        self.assertEqual(schema.identity_role('Innovation developer - Torino'),'job_role')

    def test_crawler_failure_never_becomes_website_defect(self):
        pages=[{'url':'https://alfa.example/','status':200,'checked_at':now(),'html':'<title>Alfa</title><h1>Alfa</h1>'}]
        a=audit(pages,{'completed':False,'failure_codes':['rendering_timeout','robots'],
            'pages':[{'url':pages[0]['url'],'viewport':390,'scope':'rendered','complete':False}],
            'findings':[{'url':pages[0]['url'],'viewport':390,'code':'mobile_content','quote':'incomplete','severity':'major'}]})
        self.assertEqual(a['browser_status'],'PARTIAL')
        self.assertFalse(any(c['status']=='FAIL_OBSERVED' and c['level']==4 for c in a['controls']))
        self.assertTrue(any(c['code']=='http_status' and c['status']=='PASS' for c in a['controls']))
        self.assertEqual(a['website_opportunity'],'LIMITED_OR_UNPROVEN')


class QueryPolicy(unittest.TestCase):
    def test_superficial_social_variants_do_not_reset_empty_family(self):
        rows=[{'campaign_id':1,'query':q,'results':0} for q in (
            'site:linkedin.com/posts cerco sviluppatore freelance Veneto',
            'site:instagram.com/p cerchiamo freelance WordPress Piemonte',
            'site:linkedin.com/posts ricerchiamo frontend freelance Toscana')]
        new=support.query('site:linkedin.com/posts cerchiamo freelance web developer Lombardia')
        self.assertEqual(qp.prepare(new,'SOCIAL',['Lombardia'],rows)[1]['reason'],'query_family_saturated')
        self.assertIsNotNone(qp.prepare(new,'SOCIAL',['Lombardia'],[{**r,'technical_error':'timeout'} for r in rows])[0])
        self.assertIsNotNone(qp.prepare(new,'SOCIAL',['Lombardia'],rows[:2])[0])

    def test_common_policy_enforces_balance_for_all_origins(self):
        rows=[{'strategy':'official_company_sector_region','results':2,'query':f'produttore serramenti {r}'} for r in ('Veneto','Lombardia')]
        for origin in ('ai','saved_plan','memory','deterministic','empty_fallback'):
            p={**support.query('azienda serramenti Piemonte sito ufficiale'),'strategy':'official_company_sector_region','origin':origin}
            self.assertEqual(qp.prepare(p,'AZIENDE',['Piemonte'],rows)[1]['reason'],'company_strategy_balance_requires_explicit')
        self.assertIsNotNone(qp.prepare(support.query('azienda cerca sviluppatore freelance sito web Piemonte'),'AZIENDE',['Piemonte'],rows)[0])


class IsolatedPipeline(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp();self.addCleanup(self.base.tearDown)

    def test_reused_plan_balancing_avoids_new_model_call(self):
        b=self.base
        for n,region in enumerate(('Veneto','Lombardia')):
            memory.event(b.store,b.c,'AZIENDE','query',str(n),{'query':'produttore serramenti '+region,'strategy':'official_company_sector_region','results':2})
        proactive={**support.query('produttore serramenti Piemonte sito ufficiale'),'strategy':'official_company_sector_region'}
        explicit=support.query('azienda cerca sviluppatore freelance sito web Veneto')
        memory.event(b.store,b.c,'AZIENDE','plan','previous',{'queries':[proactive,explicit],'chosen':None})
        with patch.object(b.w,'model',side_effect=AssertionError('unnecessary replan')):
            b.w.planning({'id':9876,'strategy':'AZIENDE','payload':{'round':1}},lambda:None)
        with b.store.connect() as c:
            p=json.loads(c.execute("select payload from research_tasks where kind='search'").fetchone()[0])
            self.assertEqual(p['query'],explicit['query'])

    def test_saved_nhw_original_to_dossier_and_worklist(self):
        case=load()['cases'][0];b=self.base;p=copy.deepcopy(case['task']['payload'])
        calls=[]
        def recorded(*args,**kw):
            calls.append(args[2]['task']);return copy.deepcopy(case['ai_executions'][0]['response'])
        b.c['filters']['regions']=load()['configuration']['regions']
        # Existing original and AI response replay; follow-up may be queued but
        # its absent provider response is never fabricated or executed.
        with patch.object(b.w,'model',side_effect=recorded),patch('sales.agent6.coordinator.deep_review_slot'),\
             patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('saved original only')):
            b.w.reading({'id':9876,'strategy':'AGENCIES','payload':p},lambda:None)
        self.assertEqual(calls,[schema.READ])
        with b.store.connect() as c:
            rows=[json.loads(r[0]) for r in c.execute('select body from agent6_records')]
            self.assertTrue(any(r.get('completion_queue',{}).get('promising') for r in rows))
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions').fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
        result=listing(b.store,{'view':'promising'})
        self.assertTrue(result['items'])
        self.assertEqual(result['items'][0]['body']['state'],'NEEDS_REVIEW')

    def test_completion_reservations_hold_planning_and_screening(self):
        b=self.base
        for flow in ('AGENCIES','STARTUPS'):
            b.rs.enqueue(b.c['id'],'candidate',flow,{'url':'https://alfa.example/'+flow,'original_page':{'url':'https://alfa.example/'+flow}})
        b.rs.enqueue(b.c['id'],'agent_plan','AZIENDE',{'round':2})
        with b.store.connect() as c:
            self.assertEqual(budget.available(c,b.c,'AZIENDE',b.cfg,'replan',[]),0)
            _,decision=scheduling.choose(c,b.c,now())
            self.assertEqual(decision['pipeline_phase'],'ORIGINAL_VERIFICATION')
            self.assertGreater(decision['ai_capacity'],0)
        self.assertEqual(b.call('AGENCIES','page:one',support.output()[0])['status'],'completed')
        payload=copy.deepcopy(support.output()[0]);payload['flow']='STARTUPS'
        self.assertEqual(b.call('STARTUPS','page:two',payload)['status'],'completed')
