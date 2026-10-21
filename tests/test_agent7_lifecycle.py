"""Offline lifecycle and scarce-capacity regression tests, disposable databases."""
import json
import unittest
import test_agent6_campaign32 as support
from sales.agent6 import budget


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.rs,self.w,self.c=self.base.store,self.base.rs,self.base.w,self.base.c
    def tearDown(self):self.base.tearDown()

    def test_resume_preserves_failed_attempts_payload_and_consumption(self):
        self.w.enqueue('candidate','AZIENDE',{'url':'https://alfa.example/request','original_page':{'html':'saved public proof'},'verification_repair':{'code':'unknown_segment'}},'durable-test')
        t=self.rs.claim(self.c['id'],self.c['generation'])
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        with self.store.connect() as c:
            c.execute("UPDATE research_tasks SET state='failed',attempts=3 WHERE id=?",(t['id'],))
            before=dict(c.execute('SELECT * FROM research_tasks WHERE id=?',(t['id'],)).fetchone())
        resumed=self.rs.resume(self.c['id'])
        with self.store.connect() as c:after=dict(c.execute('SELECT * FROM research_tasks WHERE id=?',(t['id'],)).fetchone())
        self.assertEqual(after['attempts'],3);self.assertEqual(after['payload'],before['payload'])
        self.assertEqual(after['state'],'pending')
        claimed=self.rs.claim(self.c['id'],resumed['generation'])
        self.assertEqual(claimed['id'],t['id']);self.assertEqual(claimed['attempts'],4)
        self.assertEqual(self.rs.campaign(self.c['id'])['filters'],self.c['filters'])

    def test_runtime_marker_is_for_new_campaigns_not_historical_relabeling(self):
        self.assertEqual(self.c['filters']['runtime_version'],'9.2.2')
        # Emulate a historical saved campaign, then resume it on the new code.
        from sales.db import encode
        filters={k:v for k,v in self.c['filters'].items() if k!='runtime_version'}
        with self.store.connect() as c:c.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(filters),self.c['id']))
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        resumed=self.rs.resume(self.c['id'])
        self.assertNotIn('runtime_version',resumed['filters'])
        from sales.agent6.api import intelligence
        self.assertEqual(intelligence(self.store)['campaign_comparison'][0]['version'],'6.0')

    def test_scarce_capacity_never_deadlocks_all_pending_originals(self):
        flows=self.c['filters']['commercial_engines'];cfg=self.c['filters']['commercial']['ai']
        for f in flows:self.w.enqueue('candidate',f,{'url':'https://'+f.lower()+'.example/request'},'candidate-'+f)
        # Synthetic ledger input: 18 of the saved 20 calls consumed, six/flow.
        rows=[{'engine':f,'reserved_cost':0,'reported_cost':None} for f in flows for _ in range(6)]
        with self.store.connect() as c:
            slots={f:budget.available(c,self.c,f,cfg,'verify',rows) for f in flows}
        self.assertEqual(sum(slots.values()),2)
        self.assertEqual(sum(v>0 for v in slots.values()),2)

    def test_technical_plan_failure_is_not_source_or_budget_exhaustion(self):
        self.w.mark('AZIENDE','blocked','Pianificazione non recuperata: invalid_plan_envelope')
        state,message=self.w.terminal_state()
        self.assertEqual(state,'blocked')
        self.assertIn('controlli non completati',message)
        with self.store.connect() as c:
            event=json.loads(c.execute("SELECT details FROM research_events WHERE campaign_id=? AND kind='agent_termination' ORDER BY id DESC LIMIT 1",(self.c['id'],)).fetchone()[0])
        self.assertEqual(event['reason_codes'][0]['code'],'unfinished_checks')
        self.assertTrue(any('invalid_plan_envelope' in (r['error'] or '') for r in event['flows']))

    def test_query_limit_is_named_without_claiming_serper_empty(self):
        self.w.mark('AZIENDE','budget_reached','Query autorizzate esaurite')
        state,message=self.w.terminal_state()
        self.assertEqual(state,'exhausted')
        self.assertIn('AZIENDE',message);self.assertIn('Query autorizzate',message)
        self.assertIn('saldo dei provider non è stato interrogato',message)

    def test_no_strategy_is_distinct_from_failed_verification(self):
        for f in self.c['filters']['commercial_engines']:self.w.mark(f,'exhausted','No additional admissible strategy')
        state,message=self.w.terminal_state()
        self.assertEqual(state,'exhausted');self.assertIn('nessuna nuova strategia',message)
        self.assertNotIn('budget',message)
