"""C49 stale operational advice regression, offline temporary databases only."""
import json
import unittest
from unittest.mock import patch
import test_ai_first as harness
from sales.agent6 import memory
from sales.agent6.query_pipeline import prepare


class CampaignAdvice(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath();self.base.setUp()
        self.addCleanup(self.base.tearDown)
        self.store=self.base.store;self.cid=self.base.c['id']

    def insert(self,cid,flow,kind,body,key):
        with self.store.connect() as c:
            c.execute('INSERT INTO agent6_memory(campaign_id,flow,kind,key,body,created_at) VALUES (?,?,?,?,?,?)',
                      (cid,flow,kind,key,json.dumps(body),'2026-10-20T12:00:00+00:00'))

    def test_old_budget_and_next_strategy_do_not_stop_new_social_plan(self):
        self.insert(self.cid-1,'SOCIAL','plan_feedback',{'reason':'capacity_reserved_for_pending_work'},'old')
        self.insert(self.cid-1,'SOCIAL','next_strategy',{'instruction':'stop because budget exhausted'},'old')
        self.insert(self.cid-1,'SOCIAL','query',{'query':'old social query','strategy':'public_request','results':0},'old')
        before=memory.history(self.store,'SOCIAL')
        self.assertTrue(before['plan_feedback'])  # Ledger remains available.
        self.assertEqual(memory.planning_feedback(self.store,self.cid,'SOCIAL'),
                         {'plan_feedback':[],'next_strategies':[]})
        with patch.object(self.base.w,'model',return_value={'status':'error','error':'offline'}) as model:
            self.base.w.planning({'id':900,'strategy':'SOCIAL','payload':{'round':0}},lambda:None)
        context=model.call_args.args[2]['memory']
        self.assertEqual(context['campaign_id'],self.cid)
        self.assertEqual(context['plan_feedback'],[])
        self.assertEqual(context['next_strategies'],[])
        self.assertEqual(context['recent_queries'][0]['query'],'old social query')
        self.assertNotIn('capacity_reserved_for_pending_work',json.dumps(context))
        with self.store.connect() as c:
            old=[json.loads(r[0]) for r in c.execute("SELECT body FROM agent6_memory WHERE campaign_id=? AND kind='plan_feedback'",(self.cid-1,))]
        self.assertEqual(old,before['plan_feedback'])

    def test_current_repairs_survive_resume_with_flow_and_campaign_provenance(self):
        self.insert(self.cid,'AGENCIES','plan_feedback',{'reason':'other_flow'},'other')
        self.insert(self.cid,'LINKEDIN','plan_feedback',{'reason':'bad_citation'},'legacy')
        self.insert(self.cid,'SOCIAL','next_strategy',{'instruction':'try other platform'},'next')
        advice=memory.planning_feedback(self.store,self.cid,'SOCIAL')
        self.assertEqual([r['reason'] for r in advice['plan_feedback']],['bad_citation'])
        self.assertEqual(advice['next_strategies'][0]['campaign_id'],self.cid)
        self.assertEqual(advice,memory.planning_feedback(self.store,self.cid,'SOCIAL'))
        self.assertTrue(advice['plan_feedback'][0]['at'])

    def test_procurement_queries_are_directions_not_declared_demand(self):
        for text in ('startup Veneto selezione fornitore sviluppo MVP web',
                     'Lombardia ricerca di un fornitore ecommerce',
                     'Piemonte richiesta preventivi sviluppo sito'):
            p,error=prepare(harness.query(text),'STARTUPS',['Veneto','Lombardia','Piemonte'],ai_first=True)
            self.assertIsNone(error,text)
            self.assertEqual(p['commercial_policy']['intents'],['request_or_invitation_to_verify'])
        for text in ('Veneto elenco fornitori web','Veneto servizi sviluppo MVP web',
                     'Veneto selezione fornitore macchinari'):
            self.assertIsNotNone(prepare(harness.query(text),'STARTUPS',['Veneto'],ai_first=True)[1],text)
