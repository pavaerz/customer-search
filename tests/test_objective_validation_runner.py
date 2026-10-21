"""Bounded evaluation contracts. Every provider is a local test double."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as h
from scripts.run_objective_validation import evaluate,load_inputs,CONFIG,MAX_CALLS,MAX_COST
from sales.agent6.grounding import provider_payload
from sales.commercial.ai_provider import ProviderError


def records(n=1):
    return [{'id':'sample-'+str(i),'flow':'AGENCIES','url':'https://alfa.example/collabora',
             'payload':h.payload(),'review':{'expected':'INTERESTING','allowed':['INTERESTING']}} for i in range(n)]


def provider(payload,config,check):
    check()
    return {'output':h.response(payload),'usage':{'input_tokens':100,'output_tokens':100}}


class EvaluationLimits(unittest.TestCase):
    def test_prepared_originals_load_without_network_or_label_leak(self):
        with tempfile.TemporaryDirectory() as tmp,patch('socket.create_connection',side_effect=AssertionError('Network')):
            folder=Path(tmp)
            payload=h.payload()
            raw=json.dumps({'payload':payload,'wire_payload':provider_payload(payload)}).encode()
            (folder/'sample.json').write_bytes(raw)
            row={k:v for k,v in records()[0].items() if k!='payload'}
            row.update(payload_file='sample.json',payload_sha256=hashlib.sha256(raw).hexdigest())
            (folder/'MANIFEST.json').write_text(json.dumps({'sources':[row]}))
            prepared=load_inputs(folder)
            self.assertEqual(len(prepared),1)
            self.assertNotIn('review',prepared[0]['payload'])
            (folder/'sample.json').write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                load_inputs(folder)

    def test_reservation_precedes_provider_and_call_limit_counts_all_attempts(self):
        saved=[]
        def infer(p,c,g):
            self.assertEqual(saved[-1]['attempts'][-1]['status'],'reserved')
            return provider(p,c,g)
        result=evaluate(records(25),infer,lambda x:saved.append(copy.deepcopy(x)))
        self.assertEqual(len(result['attempts']),MAX_CALLS)
        self.assertEqual(result['status'],'budget_reached')
        self.assertLessEqual(result['reserved_estimated_usd'],MAX_COST)
        self.assertEqual(result['metrics']['recognized_positive_invitations'],20)
        self.assertEqual(len(result['metrics']['positive_invitations_not_recovered']),5)

    def test_cost_limit_prevents_dispatch_without_increasing_budget(self):
        cfg={**CONFIG,'input_cost_per_million':1000}
        with patch('sales.commercial.ai_provider.infer',side_effect=AssertionError('Budget bypass')) as remote:
            result=evaluate(records(),remote,lambda x:None,config=cfg)
        remote.assert_not_called()
        self.assertEqual(result['status'],'budget_reached')
        self.assertEqual(result['attempts'],[])

    def test_configured_limits_are_enforced_instead_of_baseline_constants(self):
        cfg={**CONFIG,'max_calls_per_campaign':2,'max_estimated_cost':0.5}
        result=evaluate(records(3),provider,lambda x:None,config=cfg)
        self.assertEqual(len(result['attempts']),2)
        self.assertEqual(result['status'],'budget_reached')
        self.assertEqual(result['max_calls'],2)
        cfg={**cfg,'max_estimated_cost':0.01}
        result=evaluate(records(3),provider,lambda x:None,config=cfg)
        self.assertEqual(len(result['attempts']),0)
        self.assertEqual(result['max_estimated_usd'],0.01)

    def test_unavailable_model_and_bad_request_stop_the_comparison(self):
        for code in ('provider_http_400','provider_http_404'):
            with self.subTest(code=code),patch('sales.commercial.ai_provider.infer',side_effect=ProviderError(code)) as remote:
                result=evaluate(records(13),remote,lambda x:None)
            self.assertEqual(remote.call_count,1)
            self.assertEqual(result['status'],'provider_blocked')

    def test_reasoning_usage_is_recorded_but_not_double_charged(self):
        def reasoning(p,c,g):
            response=provider(p,c,g)
            response['usage'].update(reasoning_tokens=75,cached_input_tokens=50)
            return response
        result=evaluate(records(),reasoning,lambda x:None)
        self.assertEqual(result['attempts'][0]['usage']['reasoning_tokens'],75)
        self.assertAlmostEqual(result['usage_estimated_usd'],0.000525)

    def test_sol_profile_preserves_all_frozen_inputs_without_truncation(self):
        from scripts.run_objective_validation_sol import SOL_CONFIG,SOL_RESULT
        baseline=load_inputs();sol=load_inputs(config=SOL_CONFIG)
        self.assertEqual([r['payload'] for r in baseline],[r['payload'] for r in sol])
        self.assertNotEqual(SOL_RESULT.name,'VALIDATION-AI-01.json')
        self.assertEqual(SOL_CONFIG['max_calls_per_campaign'],20)
        self.assertEqual(SOL_CONFIG['max_output_tokens'],4096)
        # 20 conservative reservations including repairs fit only the proposal.
        reservation=(20480*2+4096*10)/1e6
        self.assertLessEqual(reservation*20,SOL_CONFIG['max_estimated_cost'])
        self.assertGreater(reservation*13,CONFIG['max_estimated_cost'])
        self.assertEqual(CONFIG['max_estimated_cost'],0.5)

    def test_one_semantic_repair_with_same_originals_is_accounted(self):
        sent=[]
        def infer(p,c,g):
            sent.append(copy.deepcopy(p))
            out=h.response(p)
            if len(sent)==1:
                out['facts'][0]['segment_id']='invented-reference'
            return {'output':out,'usage':{'input_tokens':100,'output_tokens':100}}
        result=evaluate(records(),infer,lambda x:None)
        self.assertEqual([r['status'] for r in result['attempts']],['invalid','valid'])
        self.assertEqual(sent[0]['evidence'],sent[1]['evidence'])
        self.assertIn('repair',sent[1])
        self.assertEqual(result['metrics']['valid_decisions'],1)

    def test_auth_failure_stops_instead_of_spending_on_remaining_sources(self):
        with patch('sales.commercial.ai_provider.infer',side_effect=ProviderError('provider_http_401')) as remote:
            result=evaluate(records(13),remote,lambda x:None)
        self.assertEqual(remote.call_count,1)
        self.assertEqual(result['status'],'provider_blocked')
        self.assertFalse(result['usage_cost_complete'])
        self.assertEqual(result['usage_missing_attempts'],1)

    def test_token_violation_stops_and_keeps_reported_usage(self):
        def oversized(p,c,g):
            return {'output':h.response(p),'usage':{'input_tokens':9000,'output_tokens':200}}
        result=evaluate(records(3),oversized,lambda x:None)
        self.assertEqual(len(result['attempts']),1)
        self.assertEqual(result['status'],'provider_blocked')
        self.assertEqual(result['attempts'][0]['usage']['input_tokens'],9000)
        self.assertTrue(result['usage_cost_complete'])
        self.assertGreater(result['usage_estimated_usd'],0)

    def test_interruption_preserves_reservation_and_never_replays_automatically(self):
        saved=[]
        def stop(p,c,g):
            raise InterruptedError('Stop')
        result=evaluate(records(),stop,lambda x:saved.append(copy.deepcopy(x)))
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['attempts'][0]['status'],'interrupted_charge_unknown')
        self.assertGreater(result['reserved_estimated_usd'],0)
        self.assertEqual(result,saved[-1])

    def test_metrics_separate_false_positives_invalid_and_unattempted_cases(self):
        cases=records(2)
        cases[1]['review']={'expected':'NOT_INTERESTING','allowed':['NOT_INTERESTING']}
        result=evaluate(cases,provider,lambda x:None)
        self.assertEqual(result['metrics']['recognized_positive_invitations'],1)
        self.assertEqual(result['metrics']['promoted_outside_positive_labels'],1)
        self.assertEqual(result['metrics']['agreement_on_valid_decisions'],1)
        self.assertEqual(result['metrics']['social_originals_evaluated'],0)
