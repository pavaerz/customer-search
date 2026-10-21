"""Fault injection on cited facts; no invented live opportunity or remote calls."""
import copy
import html
import unittest
from unittest.mock import patch
import test_agent6 as base
import test_agent6_campaign32 as support
from test_agent7 import response
from sales.agent6 import schema, qualification
from sales.agent6.field_recovery import merge


class Fields(unittest.TestCase):
    def setUp(self):
        self.p,self.o=base.output()
        self.p['recover_fields']=True

    def test_bad_entity_does_not_destroy_real_request(self):
        a=self.o['analyses'][0]
        entity=next(f for f in a['facts'] if f['field']=='entity')
        entity['ref']['end']-=1  # Deliberately truncated name, not a valid alias.
        out,errors=schema.validate_response(self.o,self.p)
        got=out['analyses'][0]
        self.assertEqual(errors[0]['code'],'unsupported_actor')
        self.assertNotIn('entity',[f['field'] for f in got['facts']])
        self.assertIn('request',[f['field'] for f in got['facts']])
        body=qualification.evaluate(base.source(),got,self.p['evidence'],'AZIENDE',base.identity())
        self.assertTrue(body['identity_verified'])
        self.assertEqual(body['entity_name'],'Alfa Srl')
        self.assertIn('entity',body['deterministic_completion']['added_fields'])

    def test_cross_result_fact_is_removed_not_borrowed(self):
        e=copy.deepcopy(self.p['evidence'][0]);e.update(id='foreign',result_id='other')
        self.p['evidence'].append(e)
        fact=self.o['analyses'][0]['facts'][0]
        fact['ref']={**fact['ref'],'id':'foreign'}
        out,errors=schema.validate_response(self.o,self.p)
        self.assertEqual(errors[0]['code'],'wrong_source')
        self.assertTrue(out['analyses'][0]['facts'])
        self.assertTrue(all(f['ref']['id']!='foreign' for f in out['analyses'][0]['facts']))

    def test_invalid_kind_source_still_invalidates_interpretation(self):
        self.o['analyses'][0]['kind_ref']['id']='invented'
        with self.assertRaises(schema.ValidationError):schema.validate_response(self.o,self.p)

    def test_repair_cannot_overwrite_valid_request_with_new_direction(self):
        valid,_=schema.validate_response(self.o,self.p);saved=valid['analyses'][0]
        saved['field_errors']=[{'field':'contact','code':'unknown_or_ambiguous_segment'}]
        repaired=copy.deepcopy(saved);repaired['kind']='SUPPLIER_OFFER'
        repaired['facts']=[f for f in repaired['facts'] if f['field']=='request']
        out,pool=merge(saved,self.p['evidence'],repaired,self.p['evidence'],['contact'])
        self.assertEqual(out['kind'],saved['kind'])
        self.assertEqual(out['facts'],saved['facts'])
        self.assertEqual(out['field_errors'][0]['field'],'contact')
        self.assertEqual(len(pool),len(self.p['evidence']))

    def test_failed_repair_preserves_prior_facts_and_unresolved_identity(self):
        self.o['analyses'][0]['facts'][0]['ref']['end']-=1
        valid,_=schema.validate_response(self.o,self.p);saved=valid['analyses'][0]
        out,pool=merge(saved,self.p['evidence'],None,[],['entity'])
        self.assertEqual([f['field'] for f in out['facts']],[f['field'] for f in saved['facts']])
        self.assertIn('entity',out['missing'])
        for f in out['facts']:
            q=schema.quote(f['ref'],pool)
            self.assertIn(q['quote'],base.TEXT)

    def test_shape_failures_remain_strict(self):
        self.o['analyses'][0]['facts']='not a list'
        with self.assertRaises(schema.ValidationError):schema.validate_response(self.o,self.p)


class TargetedRepair(unittest.TestCase):
    def test_partial_validated_output_replays_with_field_diagnostics(self):
        fixture=support.Campaign32Fix();fixture.setUp();self.addCleanup(fixture.tearDown)
        payload,_=base.output();payload['recover_fields']=True
        def partial(p,cfg,check):
            o=support.provider(p,cfg,check)
            fact=o['output']['analyses'][0]['facts'][0]
            fact['ref']={**fact['ref'],'end':fact['ref']['end']-1}
            return o
        from sales.agent6 import ai
        first=ai.call(fixture.store,fixture.c,'AZIENDE','page:partial',payload,lambda:None,partial)
        self.assertTrue(first['partial'])
        with patch('sales.agent6.ai.infer',side_effect=AssertionError('Replay must be free')):
            second=ai.call(fixture.store,fixture.c,'AZIENDE','page:partial',payload,lambda:None)
        self.assertTrue(second['replayed'])
        self.assertEqual(first['output']['analyses'][0]['field_errors'],second['output']['analyses'][0]['field_errors'])

    def test_worker_reads_once_repairs_only_identity_and_keeps_request(self):
        fixture=support.Campaign32Fix();fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.c['filters']['commercial']['ai']['max_calls_per_candidate']=4
        url='https://alfa.example/careers'
        page={'url':url,'status':200,'checked_at':base.DATE,'html':
            '<title>Alfa Srl</title>'+''.join('<p>'+html.escape(x)+'</p>' for x in base.TEXT.splitlines())+
            '<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">Contatti</a>'}
        calls=[]
        def model(payload,cfg,check):
            calls.append(payload)
            o=response(payload)
            a=o['output']['analyses'][0]
            if len(calls)==1:
                a['facts'][0]['ref']={'segment_id':'invalid-identity'}
            else:
                self.assertEqual(payload['repair']['fields'],['entity'])
                a['facts']=[f for f in a['facts'] if f['field']=='entity']
            # Kind grounded independently: the injected error concerns one field.
            a['kind_ref']=next(s['segment_id'] for e in payload['evidence'] for s in e['segments'] if 'We are looking for' in s['text'])
            a['kind_ref']={'segment_id':a['kind_ref']}
            return o
        fixture.rs.enqueue(fixture.c['id'],'candidate','AZIENDE',{'url':url,'query':'fixture'},'repair-case')
        with patch('socket.create_connection',side_effect=AssertionError('No network')),patch('sales.agent6.ai.infer',side_effect=model),patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page) as read:
            task=fixture.rs.claim(fixture.c['id'],fixture.c['generation'])
            fixture.w.execute(task,lambda:None);fixture.rs.task_done(task['id'])
            task=fixture.rs.claim(fixture.c['id'],fixture.c['generation'])
            self.assertIsNone(task)  # 9.1: exact owner anchor completes the field locally.
        self.assertEqual(read.call_count,1)
        self.assertEqual(len(calls),1)
        import json
        with fixture.store.connect() as c:
            body=json.loads(c.execute('SELECT body FROM agent6_records ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertTrue(body['identity_verified'])
        self.assertIn('request',[f['field'] for f in body['facts']])
        self.assertEqual(body['field_errors'],[])
        self.assertNotIn('entity',body['missing'])


if __name__=='__main__':unittest.main()
