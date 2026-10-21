"""C46 saved evidence and isolated queue replay. No commercial outcomes simulated."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_ai_first as harness
import test_objective_campaign45 as capacity
from sales.agent6 import budget, memory, semantics
from sales.agent6.owner_policy import apply_user_scope
from sales.agent6.query_pipeline import prepare

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign46/policy.json').read_text())

class SubjectPolicy(unittest.TestCase):
    def test_four_real_excluded_subjects_stop_without_rewriting_raw_model_or_identity(self):
        for row in SAVED['records']:
            before=copy.deepcopy(row['body']);body=apply_user_scope(before)
            self.assertEqual(body['decision'],'NOT_INTERESTING',row['id'])
            self.assertEqual(body['research_action']['type'],'STOP')
            self.assertEqual(body['ai_decision'],before['ai_decision'])
            self.assertEqual(body['identity'],before['identity'])
            self.assertFalse(body['identity']['verified'])
            self.assertEqual(body['budget'],before['budget'])
            self.assertEqual(before,row['body'])
            self.assertTrue(all(p['actor']==body['entity_name'] for p in body['commercial_exclusions']))
            self.assertFalse(semantics.decision_metadata(body)['negative_feedback_reliable'])
            self.assertEqual(semantics.decision_metadata(body)['decision_category'],'user_exclusion')

    def subject(self,name,quote):
        b=copy.deepcopy(SAVED['records'][0]['body'])
        b.update(entity_name=name,commercial_exclusions=[],facts=[{'field':'entity','original':True,
                         'url':'https://example.org','quote':quote}])
        b['ai_decision']['subject_role']='MENTIONED'
        return b

    def test_other_company_publisher_and_wellness_forms_do_not_transfer(self):
        for name,quote in [('Alfa Srl','Alfa Srl collabora con Beta S.p.A.'),
                           ('Alfa Spa','Alfa Spa benessere e relax, partita IVA 12345'),
                           ('Alfa Spa','Alfa Spa. Beta Spa Società con socio unico Gamma S.p.A.')]:
            b=self.subject(name,quote)
            self.assertEqual(apply_user_scope(b),b)
        for change in ('indexed','invalid','publisher','wrong_quote'):
            b=self.subject('Alfa S.p.A.','Alfa S.p.A. cerca collaboratori.')
            if change=='indexed':b['original']=False
            elif change=='invalid':b['validation_status']='MODEL_INVALID'
            elif change=='publisher':b['ai_decision']['subject_role']='PUBLISHER'
            else:b['facts'][0]['quote']='Beta S.p.A. cerca collaboratori.'
            self.assertEqual(apply_user_scope(b),b,change)

    def test_selected_third_party_is_excluded_without_blacklisting_source(self):
        b=self.subject('Alfa S.p.A.','Alfa S.p.A. cerca collaboratori.')
        out=apply_user_scope(b)
        self.assertEqual(out['decision_authority'],'explicit_user_exclusion')
        self.assertNotIn('blacklist',out)
        self.assertEqual(apply_user_scope(self.subject('Beta Srl','Beta Srl cerca collaboratori.'))['decision'],'NEEDS_RESEARCH')

class QueryPolicy(unittest.TestCase):
    def test_real_opening_query_can_be_investigated_without_declared_demand(self):
        q=harness.query('Veneto calzaturificio apre primo spaccio aziendale 2026')
        result,error=prepare(q,'NEWS',['Veneto'],ai_first=True)
        self.assertIsNone(error)
        self.assertIn('company_event_not_declared_demand',str(result))

    def test_general_opening_hours_and_howto_still_rejected(self):
        for text in ('Veneto orari apertura negozio','come aprire uno spaccio Veneto',
                     'Veneto agenzia portfolio progetti realizzati',
                     'Veneto (calzaturificio apre spaccio OR come aprire negozio)'):
            _,error=prepare(harness.query(text),'NEWS',['Veneto'],ai_first=True)
            self.assertIsNotNone(error,text)

class RecoveryAndStop(unittest.TestCase):
    def setUp(self):
        self.base=capacity.FirstCycleReplay();self.base.setUp();self.addCleanup(self.base.tearDown)
        self.store,self.c,self.cfg=self.base.store,self.base.c,self.base.cfg

    def rejected_plan(self,flow):
        saved=next(p['body'] for p in SAVED['plans'] if p['flow']=='NEWS')
        memory.event(self.store,self.c,flow,'plan','rejected',copy.deepcopy(saved))

    def test_first_plan_repair_survives_other_flows_replan_and_pending_originals(self):
        self.base.reserve('AGENCIES','plan:1','replan')
        self.base.add('candidate','AZIENDE',{'url':'https://original.example/'},'pending')
        self.rejected_plan('NEWS')
        self.assertGreater(budget.remaining(self.store,self.c,'NEWS',self.cfg,'replan'),0)
        self.base.reserve('NEWS','plan:1','replan')
        self.assertEqual(budget.remaining(self.store,self.c,'NEWS',self.cfg,'replan'),0)

    def test_repair_exception_does_not_apply_after_a_search_or_without_rejected_plan(self):
        self.base.reserve('AGENCIES','plan:1','replan')
        self.assertEqual(budget.remaining(self.store,self.c,'NEWS',self.cfg,'replan'),0)
        self.rejected_plan('NEWS')
        memory.event(self.store,self.c,'NEWS','query','sent',{'results':1})
        self.assertEqual(budget.remaining(self.store,self.c,'NEWS',self.cfg,'replan'),0)

    def test_all_five_initial_plans_can_be_repaired_within_shared_caps(self):
        for flow in self.c['filters']['commercial_engines']:
            self.rejected_plan(flow)
            self.base.reserve(flow,'plan:1','replan')
        with self.store.connect() as db:
            rows=db.execute('SELECT reserved_cost FROM commercial_ai_executions WHERE attempt=1').fetchall()
        self.assertEqual(len(rows),10)
        self.assertLessEqual(sum(r[0] for r in rows),1.65)
        for flow in self.c['filters']['commercial_engines']:
            self.assertGreater(budget.remaining(self.store,self.c,flow,self.cfg,'verify'),0)
        low={**self.cfg,'max_calls_per_campaign':10}
        self.assertEqual(budget.remaining(self.store,self.c,'NEWS',low,'replan'),0)

    def test_hard_budget_takes_priority_over_future_http_retry(self):
        from sales.agent6.coordinator import AgentCoordinator
        from sales.commercial.coordinator import run_campaign
        # All five actual reservations already exist. A five-call maximum is
        # used only in this isolated test database to reach the hard boundary.
        self.c['filters']['commercial']['ai']['max_calls_per_campaign']=5
        tid=self.base.add('candidate','NEWS',{'url':'https://later.example/'},'future')
        with self.store.connect() as db:
            db.execute("UPDATE research_tasks SET available_at='2099-01-01T00:00:00+00:00' WHERE id=?",(tid,))
        with patch.object(AgentCoordinator,'initialize'),patch.object(AgentCoordinator,'tick'),patch.object(
                self.base.rs.__class__,'claim',return_value=None):
            run_campaign(self.store,self.c,lambda:None,lambda x:None)
        result=self.base.rs.campaign(self.c['id'])
        self.assertEqual(result['status'],'exhausted')
        self.assertIn('massimo di chiamate AI',result['message'])
        self.assertNotIn('Riprendi dopo',result['message'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT state FROM research_tasks WHERE id=?',(tid,)).fetchone()[0],'pending')
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_cost_reservation_and_actual_spend_are_not_confused(self):
        cfg={**self.cfg,'max_estimated_cost':.09}
        rows=[{'reserved_cost':.08192,'reported_cost':.001}]
        reasons=budget.global_limit_reasons(cfg,rows)
        self.assertEqual([r['code'] for r in reasons],['ai_cost_capacity'])
        self.assertEqual(reasons[0]['reserved_or_spent_usd'],.08192)
        self.assertFalse(budget.global_limit_reasons(self.cfg,rows))

class PipelinePolicy(unittest.TestCase):
    def test_cited_excluded_subject_cannot_schedule_requested_followup(self):
        from test_objective_reading46 import output
        base=harness.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        page={'url':'https://alfa.example/','status':200,'checked_at':harness.DATE,
              'html':'<title>Aptica Studio S.p.A.</title><h1>Aptica Studio S.p.A.</h1>'
                     '<p>Produciamo apparecchiature industriali.</p><a href="/contatti">Contatti</a>'}
        base.w.enqueue('candidate','AGENCIES',{'url':page['url'],'original_page':page},'policy46')
        with base.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='policy46'").fetchone()
        task={**dict(row),'payload':json.loads(row['payload'])}
        def infer(p,cfg,check):
            link=next(l for l in p['links'] if l['url'].endswith('/contatti'))
            out=output(p,{'type':'READ_LINK','link_id':link['id'],'query':'','question':'Verificare il contatto aziendale.'})
            out['entity_name']='Aptica Studio S.p.A.'
            return {'output':out,'usage':{'input_tokens':100,'output_tokens':100}}
        with patch('sales.agent6.ai.infer',side_effect=infer):
            base.w.execute(task,lambda:None)
        with base.store.connect() as db:
            body=json.loads(db.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(body['validation_status'],'ACCEPTED',body.get('technical_error'))
            self.assertEqual(body['decision'],'NOT_INTERESTING')
            self.assertEqual(body['ai_decision']['decision'],'NEEDS_RESEARCH')
            self.assertEqual(db.execute('SELECT count(*) FROM research_tasks').fetchone()[0],1)
