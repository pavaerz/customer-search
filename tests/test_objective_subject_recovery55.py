"""Saved Serper/AI replay and offline queue, budget and cancellation contracts."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as h
from sales.agent6 import decision,evidence,subject_lookup
from sales.agent6.query_pipeline import prepare
from sales.agent6.research import search
from sales.commercial.inspection import document
from sales.db import digest
from test_objective_source53 import PAGES

SAVED=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/recovery55/receipts.json.gz').read_bytes()))


def actual():
    p=SAVED['input']['payload'];out,_=decision.validate(SAVED['output'],p)
    page=PAGES[0];packet=evidence.packet(page,document(page))
    body=decision.materialize({'url':page['url'],'checked_at':page['checked_at'],'original':True},out,p['evidence'],p,'AGENCIES')
    parent={'url':page['url'],'title':packet['title'],'unit':packet['units'][0],
            'packet':{k:packet[k] for k in ('document_id','final_url','observed_at')},
            'entity_name':body['entity_name'],'lookup_domain':'sinfonialab.it','provenance':'verified_owner_subject_lookup'}
    action=body['research_action']
    proposal={'query':action['query'],'strategy':'targeted_subject_verification',
        'objective':action['question'],'missing':action['question'],'hypothesis':body['reason'],
        'expected_entity':body['entity_name'],'expected_source':'Original public company evidence',
        'success':'Resolve uncertainty with original evidence','stop_condition':'Depth and budget',
        'selection':'verification','depth':1,'research_parent':parent,
        'subject_lookup_context':subject_lookup.context(body)}
    return body,proposal


class RecoveryScope(unittest.TestCase):
    def test_real_original_justifies_the_same_query_that_found_official_careers(self):
        body,p=actual()
        self.assertEqual(body['decision'],'NEEDS_RESEARCH')
        self.assertEqual(body['freshness']['status'],'STALE')
        self.assertEqual(SAVED['empty_query']['results'],[])
        recovered=subject_lookup.recovery(p)
        expected=SAVED['official_query']['query']['q'].removesuffix(' -filetype:pdf')
        self.assertEqual(recovered['query'],expected)
        self.assertEqual(recovered['depth'],p['depth'])
        self.assertEqual(recovered['research_parent'],p['research_parent'])
        ready,issue=prepare(recovered,'AGENCIES',['Veneto'],[],ai_first=True)
        self.assertIsNone(issue)
        self.assertEqual(ready['expected_entity'],'Sinfonia sc')
        self.assertFalse(ready['official_lookup_recovery']['qualifies_opportunity'])

    def test_no_fallback_for_supplier_snippet_closed_or_incompatible_records(self):
        body,_=actual()
        for field,value in [('original',False),('identity_verified',False),('decision','NOT_INTERESTING'),
                            ('relationship','PROACTIVE_OUTREACH'),('validation_status','MODEL_INVALID'),
                            ('compensation','EQUITY_ONLY'),('commercial_exclusions',['public_administration'])]:
            self.assertIsNone(subject_lookup.context({**body,field:value}),field)
        self.assertIsNone(subject_lookup.context({**body,'facts':body['facts']+[{'field':'closed'}]}))
        self.assertIsNone(subject_lookup.context({**body,'facts':[f for f in body['facts'] if f['field']!='contract']}))

    def test_no_mixed_owner_missing_scope_repeat_or_arbitrary_role(self):
        _,p=actual()
        for field,value in [('selection','discovery'),('page',2),('subject_lookup_context',None),
                            ('official_lookup_recovery',{'domain':'sinfonialab.it'}),
                            ('query','Sinfonia sc accounting freelance')]:
            self.assertIsNone(subject_lookup.recovery({**p,field:value}),field)
        for field,value in [('lookup_domain','other.example'),('entity_name','Other Srl'),
                            ('provenance','unverified'),('url','https://publisher.example/job')]:
            self.assertIsNone(subject_lookup.recovery({**p,'research_parent':{**p['research_parent'],field:value}}),field)
        altered=copy.deepcopy(p)
        for f in altered['subject_lookup_context']['facts']:f['url']='https://publisher.example/job'
        self.assertIsNone(subject_lookup.recovery(altered))


class QueueRecovery(unittest.TestCase):
    def setUp(self):
        self.base=h.IntegratedPath();self.base.setUp()
        self.w=self.base.w;self.store=self.base.store
        _,self.p=actual()

    def tearDown(self):self.base.tearDown()

    def task(self,key='original'):
        with self.store.connect() as db:
            r=db.execute('SELECT * FROM research_tasks WHERE fingerprint=?',(key,)).fetchone()
        return {**dict(r),'payload':json.loads(r['payload'])}

    def searches(self):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM research_tasks WHERE kind='search'")]

    def test_empty_saved_search_schedules_one_recovery_and_reads_only_owner_results(self):
        self.w.enqueue('search','AGENCIES',self.p,'original')
        with patch('sales.agent6.research.acquire',return_value=[]) as acquire:
            search(self.w,self.task(),lambda:None)
            search(self.w,self.task(),lambda:None) # Resume/replay cannot insert another recovery.
        self.assertEqual(len(self.searches()),2)
        key='official-subject-recovery:'+digest('sinfonialab.it')
        task=self.task(key)
        results=[{'url':r['link'],'title':r.get('title',''),'content':r.get('snippet','')}
                 for r in SAVED['official_query']['results']]
        results += [{'url':'https://other.example/freelance','title':'Unrelated'},
                    {'url':'https://www.sinfonialab.it/file.pdf','title':'PDF'}]
        with patch('sales.agent6.research.acquire',return_value=results):
            search(self.w,task,lambda:None)
        with self.store.connect() as db:
            candidates=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='candidate'")]
            decisions=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
        self.assertTrue(any('/contatti/unisciti-al-team/' in c['url'] for c in candidates))
        self.assertTrue(candidates[0]['url'].endswith('/contatti/unisciti-al-team/'))
        self.assertEqual(candidates[0]['discovery_priority']['value'],3)
        self.assertFalse(any('other.example' in c['url'] or c['url'].endswith('.pdf') for c in candidates))
        self.assertTrue(all(c['research_parent']==self.p['research_parent'] for c in candidates))
        self.assertTrue(all(d['decision'] is None for d in decisions))
        # Even a second empty response cannot recurse.
        with patch('sales.agent6.research.acquire',return_value=[]):search(self.w,task,lambda:None)
        self.assertEqual(len(self.searches()),2)

    def test_actual_careers_order_is_not_a_commercial_decision(self):
        results=[{'url':r['link'],'title':r['title']} for r in SAVED['official_query']['results']]
        ordered=sorted(results,key=lambda r:-subject_lookup.reading_priority(r)['value'])
        self.assertTrue(ordered[0]['url'].endswith('/contatti/unisciti-al-team/'))
        self.assertTrue(all('reading_order_only' in subject_lookup.reading_priority(r)['effect'] for r in ordered))

    def test_provider_error_or_nonempty_result_never_triggers_recovery(self):
        self.w.enqueue('search','AGENCIES',self.p,'original')
        with patch('sales.agent6.research.acquire',side_effect=TimeoutError('offline')):
            with self.assertRaises(TimeoutError):search(self.w,self.task(),lambda:None)
        self.assertEqual(len(self.searches()),1)
        with patch('sales.agent6.research.acquire',return_value=[{'url':'https://sinfonialab.it/','title':'Agenzia'}]):
            search(self.w,self.task(),lambda:None)
        self.assertEqual(len(self.searches()),1)

    def test_query_ceiling_prevents_recovery_without_losing_original_receipt(self):
        self.w.budget['max_queries_per_engine']=1
        self.w.enqueue('search','AGENCIES',self.p,'original')
        with patch('sales.agent6.research.acquire',return_value=[]):search(self.w,self.task(),lambda:None)
        self.assertEqual(len(self.searches()),1)
        from sales.agent6 import memory
        self.assertEqual(memory.query_receipts(self.store,self.base.c['id'],'AGENCIES')[0]['results'],0)

    def test_stop_before_enqueue_and_ai_reservation_both_prevent_spend(self):
        self.w.enqueue('search','AGENCIES',self.p,'original')
        def stopped():raise InterruptedError('Stopped offline')
        with patch('sales.agent6.research.acquire',return_value=[]):
            with self.assertRaises(InterruptedError):search(self.w,self.task(),stopped)
        self.assertEqual(len(self.searches()),1)
        with patch('sales.agent6.research.budget.remaining',return_value=False),patch('sales.agent6.research.acquire') as acquire:
            self.assertEqual(search(self.w,self.task(),lambda:None),{'deferred_resource':'ai_verify'})
            acquire.assert_not_called()

    def test_excluded_owner_is_not_searched_again(self):
        self.w.enqueue('search','AGENCIES',self.p,'original')
        with patch('sales.agent6.research.acquire',return_value=[]),patch.object(self.w.rs,'suppressed',return_value=True):
            search(self.w,self.task(),lambda:None)
        self.assertEqual(len(self.searches()),1)


if __name__=='__main__':unittest.main()
