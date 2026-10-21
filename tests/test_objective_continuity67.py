"""Actual saved invitation follow-ups; all execution/network is offline."""
import copy,json,unittest
from unittest.mock import patch
from sales.db import encode,now
from sales.agent6 import memory,evidence
from sales.agent6.coordinator import AgentCoordinator
from sales.agent6 import continuations as sut
from sales.commercial.inspection import document
from test_objective_recovery66 import SAVED
import test_ai_first as h


class Continuity(unittest.TestCase):
    def setUp(self):
        self.base=h.IntegratedPath();self.base.setUp();self.addCleanup(self.base.tearDown)
        self.store=self.base.store;self.rs=self.base.rs;self.old=self.base.c
        self.old['filters']['regions']=['Veneto','Lombardia']
        with self.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.old['filters']),self.old['id']))
        self.records=[]
        for rid in (1909,1912):
            saved=SAVED[rid];page=copy.deepcopy(saved['page']);body=copy.deepcopy(saved['record'])
            doc=document(page);unit=body['evidence_packet']['units'][0]
            docs=[doc,evidence.metadata_document(page,doc,unit),evidence.owner_address_document(page,doc,unit,True)]
            from sales.research_analysis import identity_from
            from sales.agent6.response_channels import collect,documents
            ident=identity_from([page]);controls=collect(page,unit,ident,True)
            channel_docs,_,_=documents(page,doc['id'],unit['id'],controls);docs+=channel_docs
            memory.save_record(self.store,self.old,'AGENCIES',body,[d for d in docs if d])
            self.base.w.enqueue('candidate','AGENCIES',{'url':page['url'],'original_page':page,'depth':0},'source:'+str(rid))
        with self.store.connect() as db:
            self.records=[{**dict(r),'body':json.loads(r['body'])} for r in db.execute('SELECT * FROM agent6_records')]
            db.execute("UPDATE research_tasks SET state='done'")
            db.execute("UPDATE campaigns SET status='exhausted' WHERE id=?",(self.old['id'],))
        # Isolated new campaign; configuration copied unchanged apart from opt-in.
        f=copy.deepcopy(self.base.filters)
        f.update(decision_engine='ai_first_1',continuation_version=1,regions=['Veneto','Lombardia'])
        from sales.agent6.api import preview
        f['deep_plan_token']=preview(self.store,f)['approval_token']
        self.new=self.rs.create(f);self.w=AgentCoordinator(self.store,self.new)
        self.clock=patch.object(sut,'now',return_value='2026-10-21T05:00:00+00:00')
        self.clock.start();self.addCleanup(self.clock.stop)
        self.http=patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No network'))
        self.http.start();self.addCleanup(self.http.stop)
        self.ai=patch('sales.agent6.ai.infer',side_effect=AssertionError('No inference'))
        self.ai.start();self.addCleanup(self.ai.stop)

    def tasks(self):
        with self.store.connect() as db:
            return [{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute(
                'SELECT * FROM research_tasks WHERE campaign_id=?',(self.new['id'],))]

    def update(self,row,change):
        b=copy.deepcopy(row['body']);change(b)
        with self.store.connect() as db:db.execute('UPDATE agent6_records SET body=? WHERE id=?',(encode(b),row['id']))

    def test_two_real_followups_recovered_once_with_unchanged_history_and_budgets(self):
        with self.store.connect() as db:before=list(map(tuple,db.execute('SELECT * FROM agent6_records')))
        self.w.initialize();self.w.initialize()
        tasks=self.tasks();self.assertEqual(len(tasks),2)
        self.assertTrue(all(t['payload']['depth']==1 for t in tasks))
        self.assertTrue(all(t['payload']['continuation']['campaign_id']==self.old['id'] for t in tasks))
        self.assertTrue(all(not t['payload'].get('original_page') for t in tasks))
        self.assertEqual({t['payload']['url'] for t in tasks},{
            'https://fluidofactory.com/lavora-su-progetti-digitali-da-remoto/',
            'https://www.castaldosolutions.it/partner-program/'})
        with self.store.connect() as db:
            self.assertEqual(before,list(map(tuple,db.execute('SELECT * FROM agent6_records'))))
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.old['filters']['commercial']['ai'],self.new['filters']['commercial']['ai'])

    def test_historical_resume_without_opt_in_changes_nothing(self):
        self.new['filters'].pop('continuation_version');self.w.initialize();self.assertEqual(self.tasks(),[])

    def test_changed_regions_or_disabled_flow_do_not_recover(self):
        self.new['filters']['regions']=['Toscana'];self.w.initialize();self.assertEqual(self.tasks(),[])
        self.new['filters']['regions']=['Veneto','Lombardia'];self.w.engines=['AZIENDE']
        self.w.initialize();self.assertEqual(self.tasks(),[])

    def test_explicit_feedback_prevents_carryover_and_contact_after_queue_prevents_fetch(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO agent6_feedback(record_id,kind,note,created_at) VALUES (?,?,?,?)',
                       (self.records[0]['id'],'not_interesting','{}',now()))
        self.w.initialize();self.assertEqual(len(self.tasks()),1)
        task=self.tasks()[0];rid=task['payload']['continuation']['record_id']
        with self.store.connect() as db:
            db.execute('INSERT INTO agent6_feedback(record_id,kind,note,created_at) VALUES (?,?,?,?)',
                       (rid,'contacted','{}',now()))
        self.assertFalse(sut.check_current(self.w,task['payload']))
        self.w.execute(task,lambda:None)

    def test_invalid_proofs_links_stale_context_and_terminal_decisions_do_not_recover(self):
        for mutate in (lambda b:b.update(decision='NOT_INTERESTING'),
                       lambda b:b.update(validation_status='MODEL_INVALID'),
                       lambda b:b['facts'][0].update(quote='invented company'),
                       lambda b:b['evidence_packet']['links'][0].update(url='https://unknown.example/fake'),
                       lambda b:b['evidence_packet'].update(observed_at='2020-01-01T00:00:00+00:00'),
                       lambda b:b.update(verification_hold=True)):
            with self.subTest(mutate=mutate):
                row=copy.deepcopy(self.records[0]);mutate(row['body'])
                self.assertIsNone(sut.proposal(self.store,row,self.new,self.w.settings if hasattr(self.w,'settings') else {'max_verification_depth':2}))

    def test_prior_attempt_or_completed_destination_is_not_retried(self):
        row=self.records[0];destination='https://fluidofactory.com/lavora-su-progetti-digitali-da-remoto/'
        with self.store.connect() as db:
            db.execute("INSERT INTO research_tasks(campaign_id,kind,strategy,payload,fingerprint,state,available_at,created_at,updated_at) VALUES (?,?,?,?,?,'failed',?,?,?)",
                (self.old['id'],'candidate','AGENCIES',encode({'url':destination}),'failed-followup',now(),now(),now()))
        self.w.initialize();self.assertEqual(len(self.tasks()),1)
        self.assertNotEqual(self.tasks()[0]['payload']['url'],destination)

    def test_depth_and_followup_budget_not_reset(self):
        with self.store.connect() as db:
            for t in db.execute('SELECT id,payload FROM research_tasks').fetchall():
                p=json.loads(t['payload']);p['depth']=999
                db.execute('UPDATE research_tasks SET payload=? WHERE id=?',(encode(p),t['id']))
        self.w.initialize();self.assertEqual(self.tasks(),[])

    def test_pending_budget_deferral_can_move_but_hard_current_limits_hold(self):
        from sales.commercial.resources import BudgetExceeded
        with patch.object(self.w,'enqueue',side_effect=BudgetExceeded('followups')):
            self.w.initialize()
        self.assertEqual(self.tasks(),[])
        self.w.initialize();self.assertEqual(len(self.tasks()),2)

    def test_later_terminal_decision_and_manual_irrelevance_block_recovery(self):
        row=self.records[0]
        with self.store.connect() as db:
            b={**row['body'],'decision':'NOT_INTERESTING'}
            db.execute('INSERT INTO agent6_records(campaign_id,flow,request_key,entity_key,state,body,updated_at) VALUES (?,?,?,?,?,?,?)',
                (self.new['id'],'AGENCIES',row['request_key'],None,'REJECTED',encode(b),now()))
            db.execute('INSERT INTO agent8_annotations(record_id,changes,note,created_at) VALUES (?,?,?,?)',
                (self.records[1]['id'],encode({'relevance':'irrelevant'}),'Offline test',now()))
        self.w.initialize();self.assertEqual(self.tasks(),[])

    def test_stale_context_after_resume_prevents_work(self):
        self.w.initialize();task=self.tasks()[0]
        with patch.object(sut,'now',return_value='2027-01-01T00:00:00+00:00'):
            self.assertFalse(sut.check_current(self.w,task['payload']))
            self.w.execute(task,lambda:None)

    def test_stop_blocks_initialization(self):
        self.rs.stop(self.new['id'])
        with self.assertRaises(InterruptedError):self.w.initialize()
        self.assertEqual(self.tasks(),[])

    def test_other_flows_still_get_initial_plans(self):
        self.w.initialize();self.w.tick()
        tasks=self.tasks()
        self.assertEqual({t['strategy'] for t in tasks if t['kind']=='agent_plan'},set(self.w.engines)-{'AGENCIES'})
        self.assertTrue(any(t['kind']=='candidate' and t['strategy']=='AGENCIES' for t in tasks))

    def test_corrupt_one_candidate_does_not_lose_other(self):
        self.update(self.records[0],lambda b:b['facts'][0].update(document_start=-1))
        self.w.initialize();self.assertEqual(len(self.tasks()),1)
        self.assertEqual(self.tasks()[0]['payload']['continuation']['record_id'],self.records[1]['id'])


if __name__=='__main__':unittest.main()
