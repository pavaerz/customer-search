"""Real Campaign 61 originals, isolated scope and unchanged accounting caps."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as h
from scripts.run_objective_validation_sol import SOL_CONFIG
from sales.agent6.reading_coverage import expand
from sales.commercial.token_count import estimate
from sales.db import digest

SAVED=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/reading68/continuations.json.gz').read_bytes()))


def capture(source_id):
    base=h.IntegratedPath();base.setUp()
    try:
        base.c['filters']['commercial']['ai'].update(SOL_CONFIG)
        task=next(t for t in SAVED['tasks'] if t['payload']['continuation']['record_id']==source_id)
        p=copy.deepcopy(task['payload']);p.pop('continuation')
        base.w.enqueue('candidate',task['strategy'],p,'saved61')
        with base.store.connect() as db:
            t=db.execute("SELECT * FROM research_tasks WHERE fingerprint='saved61'").fetchone()
            task={**dict(t),'payload':json.loads(t['payload'])}
        seen=[]
        def model(flow,key,payload,check,**kwargs):
            seen.append(copy.deepcopy(payload));return {'status':'invalid','error':'offline_capture','evidence':payload['evidence']}
        with patch.object(base.w,'model',side_effect=model),patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Offline only')):
            base.w.execute(task,lambda:None)
        return seen[0],p['original_page']
    finally:base.tearDown()


class FullSource(unittest.TestCase):
    def test_actual_fluido_roles_conditions_and_remote_reach_model_with_same_cap(self):
        p,page=capture(1909);text='\n'.join(e['text'] for e in p['evidence'])
        for phrase in ('Web designer','html, css','Developer','tecniche di sviluppo front-end','compenso orario','Lavori dove vuoi'):
            self.assertIn(phrase,text)
        self.assertIn(p['source_coverage']['scope'],('isolated_original_unit_not_entire_site','isolated_original_excerpts'))
        self.assertLessEqual(estimate(p,SOL_CONFIG)['tokens'],SOL_CONFIG['max_input_tokens'])
        from sales.agent6.grounding import provider_payload
        wire=json.dumps(provider_payload(p),ensure_ascii=False)
        self.assertIn('tecniche di sviluppo front-end',wire)
        from sales.commercial.inspection import document
        doc=document(page)
        for e in p['evidence']:
            if e['document_id']==doc['id']:
                self.assertEqual(doc['text'][e['offset']:e['offset']+len(e['text'])],e['text'])

    def test_limits_and_scope_never_expand_to_other_units(self):
        text=('PRIVATE OTHER AUTHOR. '*1000)+'Remote work from Italy.'+' OTHER JOB'
        start=text.index('Remote work');end=start+len('Remote work from Italy.')
        p=h.payload(text);p['evidence'][0].update(document_id='doc',url='https://example.org/post')
        unit={'id':'unit1','text':text,'origin':'page','allowed_ranges':[[start,end]]}
        packet={'document_id':'doc','final_url':'https://example.org/post','observed_at':'2026-10-21'}
        source=expand(p,packet,unit,SOL_CONFIG)
        self.assertTrue(source['source_coverage']['complete_selected_unit'])
        shown=' '.join(e['text'] for e in source['evidence'])
        self.assertNotIn('PRIVATE',shown);self.assertNotIn('OTHER JOB',shown)
        low=expand({**p,'evidence':[]},packet,unit,{**SOL_CONFIG,'max_input_tokens':10})
        self.assertEqual(low['evidence'],[])



if __name__=='__main__':unittest.main()

class ActualInferenceBoundary(unittest.TestCase):
    def test_provider_receives_required_original_sections_and_replay_is_free(self):
        from sales.agent6.ai import call
        p,_=capture(1909)
        b=h.IntegratedPath();b.setUp();self.addCleanup(b.tearDown)
        b.c['filters']['commercial']['ai'].update(SOL_CONFIG)
        seen=[]
        def provider(payload,cfg,check):
            check();seen.append(copy.deepcopy(payload));return {'output':{},'usage':{'input_tokens':2000,'output_tokens':1}}
        r=call(b.store,b.c,'AGENCIES','saved-original',p,lambda:None,provider=provider)
        self.assertEqual(len(seen),1)
        actual='\n'.join(e['text'] for e in seen[0]['evidence'])
        for phrase in ('Web designer','html, css','Developer','tecniche di sviluppo front-end','compenso orario','Lavori dove vuoi'):
            self.assertIn(phrase,actual)
        self.assertLessEqual(r['input_estimate']['tokens'],SOL_CONFIG['max_input_tokens'])
        self.assertTrue(call(b.store,b.c,'AGENCIES','saved-original',p,lambda:None,provider=provider)['replayed'])
        self.assertEqual(len(seen),1)

    def test_wire_groups_only_same_source_and_unit_and_keeps_resolvable_ids(self):
        from sales.agent6.grounding import provider_payload,resolve,segments
        p=h.payload();p['reading_coverage_version']=1;e=copy.deepcopy(p['evidence'][0]);e['id']='other';e['url']='https://other.example/';p['evidence'].append(e)
        wire=provider_payload(p);self.assertEqual(len(wire['evidence']),2)
        for e in p['evidence']:
            for s in segments(e):self.assertEqual(resolve({'segment_id':s['segment_id']},p['evidence'])['id'],e['id'])
        p['evidence'][1]['unit_id']='other-unit'
        self.assertTrue(all('unit_id' in e for e in provider_payload(p)['evidence']))

    def test_recorded_coverage_uses_returned_proof_after_trimming(self):
        from sales.agent6.reading_coverage import measured
        pack={'document_id':'doc','final_url':'https://example.org'}
        unit={'text':'abcdef','offset':10,'allowed_ranges':[[0,6]]}
        proof={'id':'one','hash':digest('abc'),'document_id':'doc','url':pack['final_url'],'offset':10,'text':'abc'}
        self.assertFalse(measured(pack,unit,[proof])['complete_selected_unit'])
        self.assertTrue(measured(pack,unit,[{**proof,'text':'abcdef'}])['complete_selected_unit'])
        self.assertFalse(measured(pack,unit,[])['complete_selected_unit'])

class RemoteWork(unittest.TestCase):
    def test_explicit_freedom_of_location_and_restrictions(self):
        from sales.commercial.job_activity import geo_value
        positive='Lavori dove vuoi. Entrando nel nostro network potrai lavorare da remoto.'
        self.assertEqual(geo_value(positive)[0],'GEO_COMPATIBLE')
        for text in ('Non puoi lavorare ovunque. Collaborazione da remoto.',
                     'Lavori dove vuoi, solo residenti in Germania. Remote.',
                     'Lavoriamo per clienti ovunque. Remote.',
                     'Remote work; UK-only. You can work anywhere.',
                     'Remote; Italy excluded. You can work anywhere.'):
            with self.subTest(text=text):self.assertNotEqual(geo_value(text)[0],'GEO_COMPATIBLE')
        from sales.agent6.subject_geography import validate
        validate({'subject_geography':{'status':'REMOTE_ITALY','fact_indices':[0],'region':'','reason':'Originale'}},
                 [{'field':'geography','quote':positive}],{'allowed_regions':['Veneto']})

class DuplicatePlans(unittest.TestCase):
    def test_recent_queries_trigger_bounded_replanning_feedback_not_redispatch(self):
        from sales.agent6 import memory
        b=h.IntegratedPath();b.setUp();self.addCleanup(b.tearDown)
        proposals=[{**h.query('site:linkedin.com/posts/ "cerchiamo freelance" sviluppatore'),'strategy':'freelance_role'},
                   {**h.query('site:instagram.com/p/ "cerchiamo freelance" sviluppatore'),'strategy':'freelance_role'}]
        limits=copy.deepcopy(b.c['filters'])
        answer={'status':'completed','output':{'decision':'search','reason':'Synthetic duplicate-plan replay','queries':proposals}}
        with patch.object(b.w,'model',return_value=answer),patch('sales.agent6.memory.seen_query',return_value=True),patch('sales.agent6.budget.remaining',return_value=1):
            b.w.planning({'id':68,'strategy':'SOCIAL','payload':{'round':0}},lambda:None)
        with b.store.connect() as db:
            events=[json.loads(r[0]) for r in db.execute("SELECT body FROM agent6_memory WHERE kind='plan_feedback'")]
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='search'").fetchone()[0],0)
        self.assertTrue(events)
        self.assertEqual([r['reason'] for r in events[-1]['rejected']],['recent_query_duplicate']*2)
        self.assertEqual(b.c['filters'],limits)

class TemporalContract(unittest.TestCase):
    def test_unknown_relationship_cannot_inherit_standing_invitation(self):
        from sales.agent6 import decision
        p=h.payload();o=h.response(p)
        o.update(decision='NEEDS_RESEARCH',relationship='UNKNOWN',service='unknown')
        o['action']={'type':'STOP','link_id':'','query':'','question':'External technical role not established'}
        with self.assertRaisesRegex(ValueError,'temporal_role_mismatch'):decision.validate(o,p)
        o['currentness']='UNKNOWN'
        self.assertEqual(decision.validate(o,p)[0]['decision'],'NEEDS_RESEARCH')
        self.assertIn('UNKNOWN relationship requires UNKNOWN currentness',decision.SYSTEM)
