"""Offline operational learning. Every commercial outcome here is synthetic."""
import json
import unittest
from unittest.mock import patch

import test_agent6 as original
import test_agent6_campaign32 as support
from sales.agent6 import memory, learning, api
from sales.agent6.coordinator import AgentCoordinator


class Learning(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.c,self.rs=self.base.store,self.base.c,self.base.rs

    def tearDown(self):self.base.tearDown()

    def next_campaign(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create(self.base.filters)
        return self.c

    def observations(self,n=3,technical=False):
        for i in range(n):
            query=f'agenzia "cerchiamo freelance" WooCommerce regione{i}'
            memory.event(self.store,self.c,'AGENCIES','query',str(i),
                {'query':query,'strategy':f'Changing AI label {i}','results':1})
            body={**original.evaluated(),'url':f'https://agency{i}.example/jobs',
                'query':query,'strategy':f'Changing AI label {i}',
                'state':'UNVERIFIABLE' if technical else 'REJECTED',
                'technical_error':'timeout' if technical else None,
                'counterevidence':[] if technical else ['closed_request'],
                'original':True,'reason':'Synthetic test observation'}
            memory.save_record(self.store,self.c,'AGENCIES',body)
            if i<n-1:self.next_campaign()

    def test_names_regions_and_keyword_order_do_not_fragment_family(self):
        first=learning.strategy_id('agenzia "cerchiamo freelance" WooCommerce Veneto','AGENCIES')
        second=learning.strategy_id('WooCommerce "cerchiamo freelance" agenzia Toscana -filetype:pdf','AGENCIES')
        self.assertEqual(first,second)
        self.assertNotEqual(first,learning.strategy_id('agenzia "cerchiamo freelance" WordPress Veneto','AGENCIES'))
        self.assertNotEqual(first,learning.strategy_id('agenzia "cerchiamo freelance" WooCommerce Veneto','STARTUPS'))

    def test_enough_observations_change_actual_next_planning_task(self):
        self.observations();self.next_campaign()
        # Exercise feedback in the current live context allocation. Tiny-input
        # trimming and hard limits are covered by objective_memory49 separately.
        self.c['filters']['commercial']['ai']['max_input_tokens']=20480
        with self.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',
                       (json.dumps(self.c['filters']),self.c['id']))
        worker=AgentCoordinator(self.store,self.c);worker.initialize();worker.tick()
        with self.store.connect() as c:
            task=dict(c.execute("SELECT * FROM research_tasks WHERE campaign_id=? AND strategy='AGENCIES' AND kind='agent_plan'",(self.c['id'],)).fetchone())
        task['payload']=json.loads(task['payload'])
        noisy={**support.query('agenzia "cerchiamo freelance" WooCommerce Liguria'),'strategy':'New name for an old strategy'}
        fresh={**support.query('agenzia "cerchiamo freelance" WordPress Liguria'),'strategy':'A different technical specialization'}
        seen=[]
        def model(payload,cfg,check):
            seen.append(payload)
            return {'output':{'decision':'search','reason':'Synthetic alternate hypotheses','queries':[noisy,fresh]},'usage':{'input_tokens':20,'output_tokens':50}}
        with patch('sales.agent6.ai.infer',side_effect=model):worker.execute(task,lambda:None)
        with self.store.connect() as c:
            searches=[json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE campaign_id=? AND kind='search'",(self.c['id'],))]
        self.assertEqual(len(searches),1);self.assertEqual(searches[0]['query'],fresh['query'])
        group=next(s for s in seen[0]['memory']['strategies'] if s['queries']==3)
        self.assertEqual(len(group['labels']),3);self.assertLess(group['priority_adjustment'],0)
        self.assertEqual(group['verified_rejections'],3)
        self.assertEqual(searches[0]['ranking_basis'],'stable_strategy_family_observed_outcomes')

    def test_one_bad_experiment_is_not_a_ban_or_automatic_penalty(self):
        self.observations(1)
        history=memory.history(self.store,'AGENCIES');group=history['strategy_groups'][0]
        self.assertFalse(group['sample_sufficient']);self.assertEqual(group['priority_adjustment'],0)
        self.assertFalse(memory.seen_query(self.store,'AGENCIES','agenzia cerchiamo freelance WooCommerce Piemonte nuova collaborazione'))

    def test_technical_failure_counts_original_read_but_never_bad_market(self):
        self.observations(3,technical=True)
        group=memory.history(self.store,'AGENCIES')['strategy_groups'][0]
        self.assertEqual(group['technical_errors'],3)
        self.assertEqual(group['original_pages_read'],3)
        self.assertEqual(group['verified_rejections'],0);self.assertEqual(group['priority_adjustment'],0)

    def test_exploration_schedule_persists_across_campaigns(self):
        self.observations(3)
        for i in range(3):memory.event(self.store,self.c,'AGENCIES','plan',str(i),{'chosen':{'query':'old'+str(i)}})
        self.next_campaign();hist=memory.history(self.store,'AGENCIES')
        self.assertEqual(hist['selection_count'],3)
        queries=[support.query('agenzia "cerchiamo freelance" WooCommerce Toscana'),support.query('agenzia "cerchiamo freelance" frontend Toscana')]
        chosen=memory.choose(queries,hist,0,25)
        self.assertEqual(chosen['selection'],'exploration');self.assertEqual(chosen['query'],queries[1]['query'])
        self.assertEqual(chosen['selection_index'],3)

    def test_crm_outcome_changes_priority_once_without_claiming_precision(self):
        body={**original.evaluated(),'query':'agenzia cerchiamo freelance WordPress Italia','strategy':'job'}
        rid=memory.save_record(self.store,self.c,'AGENCIES',body)
        pid=api.save_contact(self.store,rid)['prospect_id']
        memory.feedback(self.store,rid,'interesting')
        with self.store.connect() as c:c.execute("UPDATE prospects SET stage='won',updated_at='2099-01-01T00:00:00+00:00' WHERE id=?",(pid,))
        group=memory.history(self.store,'AGENCIES')['strategy_groups'][0]
        self.assertEqual(group['outcomes'],{'won':1});self.assertEqual(group['human_reviews'],1)
        self.assertGreater(group['priority_adjustment'],0);self.assertLessEqual(group['priority_adjustment'],2)
        self.assertIsNone(group['precision']);self.assertIsNone(group['false_positives'])

    def test_deleted_proposal_is_a_preference_not_proven_false_positive(self):
        rid=memory.save_record(self.store,self.c,'AGENCIES',{**original.evaluated(),'query':'cerchiamo freelance WordPress'})
        memory.feedback(self.store,rid,'not_interesting')
        group=memory.history(self.store,'AGENCIES')['strategy_groups'][0]
        self.assertEqual(group['rejected_by_user'],1);self.assertIsNone(group['false_positives'])

    def test_weak_duplicate_cannot_erase_original_entity_index(self):
        body=original.evaluated();rid=memory.save_record(self.store,self.c,'AZIENDE',body)
        memory.save_record(self.store,self.c,'AGENCIES',{**body,'original':False,'entity_key':None,'identity_verified':False,'state':'DISCOVERED'})
        dossier=api.dossier(self.store,rid)
        self.assertEqual(dossier['entity_key'],body['entity_key'])
        self.assertTrue(dossier['body']['original']);self.assertTrue(dossier['body']['identity_verified'])

    def test_provider_cache_and_denied_reservations_do_not_count_as_calls(self):
        for i,status in enumerate(('completed','cache_hit','budget_exhausted','invalid')):
            memory.event(self.store,self.c,'AGENCIES','model',str(i),{'execution_id':i+1,'query':'cerchiamo freelance WordPress','status':status,'estimated_cost':0.01 if status in ('completed','invalid') else 0})
        group=memory.history(self.store,'AGENCIES')['strategy_groups'][0]
        self.assertEqual(group['ai_calls'],2);self.assertEqual(group['estimated_ai_cost'],.02)


if __name__=='__main__':unittest.main()
