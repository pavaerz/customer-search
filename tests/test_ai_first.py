"""Offline contracts and queue integration; doubles are NOT model accuracy."""
import copy
import json
import unittest
from unittest.mock import patch

from sales.agent6 import decision, evidence, schema, ai, memory, budget
from sales.agent6.grounding import attach, segments
from sales.agent6.coordinator import AgentCoordinator
from sales.agent6.alignment import dimensions
from sales.agent6.query_pipeline import prepare
from sales.agent6.scheduling import choose
from sales.db import digest, now, encode
from test_agent6_campaign32 import Campaign32Fix, query

DATE='2026-10-20T12:00:00+00:00'
TEXT='Alfa Srl\nCollaboriamo con professionisti freelance per progetti WordPress e frontend.\ninfo@alfa.example\nPadova Veneto'


def payload(text=TEXT):
    es=attach([{'id':'e1','result_id':'unit1','unit_id':'unit1','url':'https://alfa.example/collabora',
                'text':text,'hash':digest(text),'original':True,'document_id':'doc1','offset':0,'checked_at':DATE}])
    return {'task':decision.TASK,'flow':'AGENCIES','unit_id':'unit1','result_ids':['unit1'],'evidence':es,
            'identity':{'name':'Alfa Srl','verified':True,'domain':'alfa.example'},
            'observed_at':DATE,'dates':[],'links':[],'geography_allowed':True,'region':'Veneto',
            'policy_exclusion':False,'max_job_age_days':14}


def response(p):
    es=p['evidence']
    def ref(field,part):
        s=next(s for e in es for s in segments(e) if part in s['text'])
        return {'field':field,'segment_id':s['segment_id']}
    out={'decision':'INTERESTING','entity_name':'Alfa Srl','subject_role':'OWNER',
            'relationship':'OPEN_FREELANCE_COLLABORATION','service':'frontend',
            'reason':'Invito originale a collaboratori freelance per sviluppo frontend.',
            'fit':'Compatibile con le competenze di Diego; incarichi e compensi da confermare.',
            'facts':[ref('entity','Alfa Srl'),ref('request','Collaboriamo'),ref('contact','info@alfa.example')],
            'unknowns':['Budget e incarichi disponibili'],'confidence':'HIGH','priority':'high',
            'compensation':'UNKNOWN','feasibility':'UNKNOWN','currentness':'STANDING_INVITATION',
            'assessment':{'intent':'ACCEPTING_EXTERNAL',
                          'intent_facts':[1],
                          'scope':'COLLABORATION','scope_facts':[1],
                          'existing_solution':'NOT_CHECKED','solution_facts':[],
                          'interpretation':'Invito a collaboratori esterni, non offerta ai clienti.',
                          'objections':['Non dimostra una commessa già disponibile.']},
            'action':{'type':'REVIEW_OUTREACH','link_id':'','query':'','question':'Valutare una proposta di collaborazione.'}}
    if p.get('subject_scope_version')==1:
        remote=any('Remote from Italy' in e['text'] for e in es)
        out['facts'].append(ref('geography','Remote from Italy' if remote else 'Padova Veneto'))
        out['subject_geography']={'status':'REMOTE_ITALY' if remote else 'IN_TARGET','fact_indices':[len(out['facts'])-1],
                                  'region':'' if remote else 'Veneto','reason':'Geografia esplicita nella fixture originale.'}
    return out


class DecisionContracts(unittest.TestCase):
    def test_open_invitation_without_date_budget_or_stack_gate(self):
        p=payload();o,_=decision.validate(response(p),p)
        b=decision.materialize({'url':'https://alfa.example/collabora','title':'Collabora',
                               'checked_at':DATE,'original':True},o,p['evidence'],p,'AGENCIES')
        self.assertEqual(b['decision'],'INTERESTING')
        self.assertTrue(dimensions(b)['READY_FOR_OUTREACH'])
        self.assertEqual(b['open_paid_project'],'UNKNOWN')
        self.assertIsNone(b['budget']['amount'])
        from sales.agent6.commercial_view import enrich
        b['kind']='SUPPLIER_OFFER'  # A legacy label has no authority on this path.
        self.assertEqual(enrich(b)['decision'],'INTERESTING')
        self.assertEqual(enrich(b)['hypothesis'],o['fit'])
        from sales.agent6.semantics import decision_metadata
        b.update(decision='NOT_INTERESTING',state='REJECTED',semantic_issues=['legacy_label'])
        m=decision_metadata(b)
        self.assertEqual(m['decision_category'],'ai_validated')
        self.assertFalse(m['semantic_conflict'])
        self.assertTrue(m['negative_feedback_reliable'])

    def test_no_identity_no_promoted_interest(self):
        p=payload();p['identity']['verified']=False
        with self.assertRaisesRegex(ValueError,'identity_unverified'):
            decision.validate(response(p),p)

    def test_wrong_company_and_truncated_name_fail(self):
        p=payload()
        for name in ('Alfa','Unioncamere Piemon'):
            o=response(p);o['entity_name']=name
            with self.assertRaises(ValueError):decision.validate(o,p)

    def test_cross_unit_original_and_forged_segments_fail(self):
        for change in ('unit','hash','snippet'):
            p=payload();o=response(p)
            if change=='unit':p['evidence'][0]['unit_id']='different-employer'
            if change=='hash':p['evidence'][0]['text']+=' altered'
            if change=='snippet':p['evidence'][0]['original']=False
            with self.assertRaises(ValueError):decision.validate(o,p)

    def test_compensation_and_current_request_need_proof(self):
        p=payload();o=response(p);o['compensation']='PAID'
        with self.assertRaisesRegex(ValueError,'unproven_compensation'):decision.validate(o,p)
        o=response(p);o['relationship']='EXPLICIT_REQUEST';o['currentness']='RECENT_REQUEST'
        p['dates']=[{'role':'published_at','value':'2015-11-03'}]
        with self.assertRaisesRegex(ValueError,'unproven_request_currentness'):decision.validate(o,p)
        p['dates']=[{'role':'published_at','value':'2026-10-19'},{'role':'expires_at','value':'2026-10-19'}]
        with self.assertRaisesRegex(ValueError,'expired_request'):decision.validate(o,p)

    def test_next_action_only_an_observed_link(self):
        p=payload();o=response(p)
        o['action']={'type':'READ_LINK','link_id':'http://127.0.0.1/secret','query':'','question':'Contatto mancante'}
        with self.assertRaisesRegex(ValueError,'unbounded_research_action'):decision.validate(o,p)

    def test_subject_search_and_webapp_scope_are_bounded(self):
        p=payload();o=response(p)
        o['action']={'type':'SEARCH_SUBJECT','link_id':'','query':'Alfa Srl contatti','question':'Quale canale ufficiale è disponibile?'}
        self.assertEqual(decision.validate(o,p)[0]['action']['type'],'SEARCH_SUBJECT')
        o['action']['query']='aziende siti web Italia'
        with self.assertRaisesRegex(ValueError,'unbounded_subject_search'):decision.validate(o,p)
        o=response(p);o['service']='webapp'
        with self.assertRaisesRegex(ValueError,'webapp_feasibility_unverified'):decision.validate(o,p)

    def test_policy_unknown_region_and_negative_decision_separated(self):
        p=payload();p['geography_allowed']=False
        with self.assertRaisesRegex(ValueError,'geography_unverified'):decision.validate(response(p),p)
        o=response(p);o['decision']='NOT_INTERESTING';o['reason']='La professione richiesta non è compatibile.'
        self.assertEqual(decision.validate(o,p)[0]['decision'],'NOT_INTERESTING')

    def test_dates_all_positions_and_roles(self):
        claims=evidence.dates('intro '*1000+'\nPostato il: 03/11/2015\nScadenza: 30/12/2027')
        self.assertEqual([(d['role'],d['value']) for d in claims],[('published_at','2015-11-03'),('expires_at','2027-12-30')])
        self.assertEqual(evidence.dates('Copyright 2026'),[])
        self.assertIsNone(evidence.date_value('31/02/2026'))

    def test_numeric_cards_never_share_employer_dates(self):
        page={'url':'https://board.example/lavoro','html':'<p>Organizzazione: Uno Srl</p><p>Postato il: 03/11/2015</p><p>Organizzazione: Due Srl</p><p>Postato il: 19/10/2026</p>',
              'checked_at':DATE,'status':200}
        from sales.extract import Document
        doc={'id':'d1','text':Document(page['html']).text}
        pack=evidence.packet(page,doc)
        self.assertEqual(len(pack['units']),2)
        self.assertNotIn('Due',pack['units'][0]['text'])
        self.assertEqual(pack['units'][0]['dates'][0]['value'],'2015-11-03')
        self.assertEqual(pack['units'][1]['dates'][0]['value'],'2026-10-19')
        for unit in pack['units']:
            for e in evidence.passages(pack,unit):
                self.assertEqual(e['text'],doc['text'][e['offset']:e['offset']+len(e['text'])])

    def test_structured_job_quotes_have_their_own_document(self):
        job={'@type':'JobPosting','title':'Frontend freelance','hiringOrganization':{'name':'Alfa Srl'},
             'datePosted':'2026-10-19','description':'Progetto WordPress'}
        page={'url':'https://alfa.example/jobs','html':'<script type="application/ld+json">'+json.dumps(job)+'</script>',
              'checked_at':DATE,'status':200}
        pack=evidence.packet(page,{'id':'html-doc','text':''})
        unit=pack['units'][0]
        e=evidence.passages(pack,unit)[0]
        self.assertNotEqual(e['document_id'],'html-doc')
        self.assertEqual(e['document_id'],unit['document_id'])
        self.assertEqual(e['text'],unit['text'][e['offset']:e['offset']+len(e['text'])])

    def test_query_new_hypothesis_not_old_keywords_and_saturation(self):
        q=query('agenzia candidature portfolio Veneto')
        self.assertIsNotNone(prepare(q,'AGENCIES',['Veneto'],ai_first=True)[0])
        bad={**q,'hypothesis':''}
        self.assertIsNone(prepare(bad,'AGENCIES',['Veneto'],ai_first=True)[0])
        receipts=[{'campaign_id':n,'query':q['query'],'results':0} for n in range(3)]
        self.assertIsNone(prepare(q,'AGENCIES',['Veneto'],receipts,ai_first=True)[0])


class IntegratedPath(unittest.TestCase):
    def setUp(self):
        Campaign32Fix.setUp(self)
        self.c['filters']['decision_engine']=decision.ENGINE
        self.c['filters']['commercial']['ai']['max_input_tokens']=8192
        with self.store.connect() as c:
            c.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.c['filters']),self.c['id']))
        self.w=AgentCoordinator(self.store,self.c);self.w.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_flows_can_plan_and_search_has_capacity_without_screen(self):
        from sales.agent6 import FLOWS
        self.c['filters']['commercial_engines']=list(FLOWS)
        with patch('sales.agent6.ai.infer',side_effect=lambda p,c,g:{'output':{'decision':'search','reason':'Offline','queries':[query()]},'usage':{'input_tokens':20,'output_tokens':20}}):
            for flow in FLOWS:
                result=ai.call(self.store,self.c,flow,'plan:0',{'task':schema.PLAN,'flow':flow,'round':0,'memory':{}},lambda:None)
                self.assertEqual(result['status'],'completed',result)
        self.w.enqueue('search','AGENCIES',query(),'search1')
        with self.store.connect() as c:
            task,reason=choose(c,self.c,now())
            self.assertIsNotNone(task,reason)
        self.assertEqual(budget.remaining(self.store,self.c,'AGENCIES',self.cfg,'screen'),0)

    def test_read_save_and_resume_without_duplicate_inference(self):
        page={'url':'https://alfa.example/collabora','html':'<html><title>Alfa Srl</title><body>'+''.join('<p>'+t+'</p>' for t in TEXT.splitlines())+'</body></html>',
              'status':200,'checked_at':DATE,'content_type':'text/html'}
        identity={'identity_status':'verified','name':'Alfa Srl','website':page['url'],'contacts':[]}
        self.w.enqueue('candidate','AGENCIES',{'url':page['url'],'title':'Alfa','query':'agenzia freelance Veneto','strategy':'standing','depth':0},'read1')
        with self.store.connect() as c:
            r=c.execute("SELECT * FROM research_tasks WHERE fingerprint='read1'").fetchone()
            task={**dict(r),'payload':json.loads(r['payload'])}
        def provider(p,cfg,check):
            check()
            return {'output':response(p),'usage':{'input_tokens':100,'output_tokens':100}}
        patches=[patch('sales.agent6.research.CompanyWeb.get',return_value=page),
                 patch('sales.agent6.research.identity_from',return_value=identity),
                 patch('sales.agent6.research.locate',return_value={'eligible':True,'regions':['Veneto'],'remote_italy':False}),
                 patch('sales.agent6.ai.infer',side_effect=provider)]
        with patches[0] as fetch,patches[1],patches[2],patches[3] as model,patch(
                'sales.agent6.qualification.evaluate',side_effect=AssertionError('Legacy decision must not run')):
            self.w.execute(task,lambda:None)
            with self.store.connect() as c:
                row=c.execute('SELECT body FROM agent6_records').fetchone()
                b=json.loads(row[0])
                self.assertEqual(b['decision'],'INTERESTING',b.get('technical_error'))
                task['payload']=json.loads(c.execute('SELECT payload FROM research_tasks WHERE id=?',(task['id'],)).fetchone()[0])
            self.w.execute(task,lambda:None)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(model.call_count,1)
            with self.store.connect() as c:
                self.assertEqual(c.execute("SELECT used FROM commercial_resources WHERE resource='candidates'").fetchone()[0],1)
        from sales.agent6.worklist import listing
        from datetime import datetime
        listing_result=listing(self.store,{'view':'ready'},at=datetime.fromisoformat(DATE))
        self.assertEqual(listing_result['total'],1)
        # An unfinished replay of the same original retains the last valid
        # decision, but changed evidence must go through verification anew.
        pending={**b,'decision':None,'state':'NEEDS_REVIEW','validation_status':'MODEL_INVALID',
                 'technical_error':'offline_failure'}
        memory.save_record(self.store,self.c,'AGENCIES',pending)
        with self.store.connect() as c:
            saved=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(saved['decision'],'INTERESTING')
            self.assertEqual(saved['latest_research_attempt']['technical_error'],'offline_failure')
        changed={**pending,'evidence_packet':{**pending['evidence_packet'],'document_id':'new-snapshot'}}
        memory.save_record(self.store,self.c,'AGENCIES',changed)
        with self.store.connect() as c:
            self.assertIsNone(json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])['decision'])
        self.rs.stop(self.c['id'])
        with self.assertRaises(InterruptedError):
            memory.save_record(self.store,self.c,'AGENCIES',b)

    def test_discovery_pdf_and_no_snippet_ai(self):
        self.w.enqueue('search','AGENCIES',query(),'query1')
        with self.store.connect() as c:
            r=c.execute("SELECT * FROM research_tasks WHERE fingerprint='query1'").fetchone()
            t={**dict(r),'payload':json.loads(r['payload'])}
        items=[{'url':'https://alfa.example/careers','title':'Alfa','snippet':'candidature'},
               {'url':'https://alfa.example/jobs.pdf','title':'PDF'}]
        receipts=[(i,{'url':i['url'],'query':query()['query']}) for i in items]
        with patch('sales.agent6.research.acquire',return_value=items),patch.object(self.w,'receipts',return_value=receipts),patch.object(self.w,'model') as model:
            from sales.agent6.research import search
            search(self.w,t,lambda:None)
            model.assert_not_called()
        with self.store.connect() as c:
            urls=[json.loads(r[0])['url'] for r in c.execute("SELECT payload FROM research_tasks WHERE kind='candidate'")]
            self.assertEqual(urls,['https://alfa.example/careers'])
            self.assertEqual(c.execute('SELECT count(*) FROM agent6_records').fetchone()[0],1)
