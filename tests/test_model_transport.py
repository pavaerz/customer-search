import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from sales.claim_selection import grounded_units, selection_schema, materialize
from sales.db import now
from sales.discovery_control import _context
from sales.model_transport import compact, translate, encoded_size
from sales.research_analysis import LocalResearcher, schema_check


class Cache:
    def __init__(self): self.values = {}
    def settings(self): return {'ollama_model': 'qwen2.5:7b'}
    def cache_get(self, key, hours): return copy.deepcopy(self.values.get(key))
    def cache_set(self, key, value): self.values[key] = copy.deepcopy(value)


class ModelTransportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        guard=patch("sales.heavy.DATA",Path(temporary.name))
        guard.start();self.addCleanup(guard.stop)

    def inputs(self, document='a' * 64, text=None, **fields):
        text = text or 'Il portale attuale non consente di gestire ordini multilistino.'
        units = grounded_units(document, text, text)
        data = {'document_id': document, 'company': 'Alfa Srl',
                'url': 'https://alfa.example/ordini', 'document_role': 'company_page',
                'units': [{'id': u['id'], 'text': u['text']} for u in units], **fields}
        return data, selection_schema(units), units, text

    @staticmethod
    def answer(url, payload, **kwargs):
        data = json.loads(payload['messages'][1]['content'])
        return {'message': {'content': json.dumps({'claims': [
            {'unit_id': data['units'][0]['id'], 'kind': 'gap'}]})},
            'prompt_eval_count': 100, 'eval_count': 12, 'eval_duration': 1000000000}

    def test_aliases_round_trip_exact_original_citations(self):
        data, schema, units, text = self.inputs()
        before = copy.deepcopy((data, schema))
        wire, ws, back = compact(data, schema)
        self.assertLess(encoded_size(wire, ws), encoded_size(data, schema))
        response = {'claims': [{'unit_id': wire['units'][0]['id'], 'kind': 'gap'}]}
        self.assertTrue(schema_check(response, ws))
        decoded = translate(response, back)
        self.assertTrue(schema_check(decoded, schema))
        claims, errors = materialize(data['document_id'], text, units, decoded)
        self.assertFalse(errors); self.assertEqual(claims[0]['quote'], text)
        self.assertEqual((data, schema), before)

    def test_nested_proposal_and_review_references_leave_prose_untouched(self):
        ident = 'f' * 20
        data = {'signals': [{'id': ident, 'quote': ident}],
                'proposal': {'support_ids': [ident], 'budget_signal_id': ident, 'why': ident}}
        schema = {'type': 'object', 'properties': {'inference': {'type': 'object',
            'properties': {'event_id': {'type': 'string', 'enum': ['', ident]}}}}}
        wire, ws, back = compact(data, schema)
        self.assertEqual(wire['signals'][0]['quote'], ident)
        self.assertEqual(wire['proposal']['why'], ident)
        self.assertEqual(wire['proposal']['support_ids'], ['s1'])
        self.assertEqual(ws['properties']['inference']['properties']['event_id']['enum'], ['', 's1'])
        self.assertEqual(translate({'inference': {'event_id': 's1', 'reason': 's1'}}, back),
                         {'inference': {'event_id': ident, 'reason': 's1'}})

    def test_changed_document_hash_reuses_extraction_but_returns_current_ids(self):
        cache = Cache(); researcher = LocalResearcher(cache)
        with patch('sales.research_analysis.api_json', side_effect=self.answer) as api:
            first = self.inputs(); second = self.inputs(document='b' * 64)
            researcher.call('Estrai', *first[:2])
            result = researcher.call('Estrai', *second[:2])
        self.assertEqual(api.call_count, 1)
        claims, errors = materialize(second[0]['document_id'], second[3], second[2], result)
        self.assertFalse(errors); self.assertEqual(claims[0]['document_id'], 'b' * 64)

    def test_context_changes_invalidate_cache(self):
        for change in ({'company': 'Beta'}, {'url': 'https://beta.example/'},
                       {'document_role': 'linked_solution'}, {'published_at': '2026-10-14'},
                       {'text': 'Il portale non consente di gestire le prenotazioni dei clienti.'}):
            with self.subTest(change=change):
                researcher = LocalResearcher(Cache())
                with patch('sales.research_analysis.api_json', side_effect=self.answer) as api:
                    researcher.call('Estrai', *self.inputs()[:2])
                    researcher.call('Estrai', *self.inputs(**change)[:2])
                self.assertEqual(api.call_count, 2)

    def test_unknown_alias_is_rejected_and_not_cached(self):
        store = Cache()
        result = {'message': {'content': '{"claims":[{"unit_id":"u999","kind":"gap"}]}'}}
        with patch('sales.research_analysis.api_json', return_value=result):
            with self.assertRaises(ValueError): LocalResearcher(store).call('Estrai', *self.inputs()[:2])
        self.assertFalse(store.values)

    def test_legacy_cached_results_warm_compact_cache_without_inference(self):
        store = Cache(); researcher = LocalResearcher(store)
        with patch('sales.research_analysis.api_json', side_effect=self.answer):
            researcher.call('Estrai', *self.inputs()[:2])
        store.values = {k: v for k, v in store.values.items() if k.startswith('v4:')}
        with patch('sales.research_analysis.api_json', side_effect=AssertionError('No inference')):
            researcher.call('Estrai', *self.inputs()[:2])
            result = researcher.call('Estrai', *self.inputs(document='b' * 64)[:2])
        self.assertEqual(result['claims'][0]['unit_id'], self.inputs(document='b' * 64)[2][0]['id'])

    def test_timings_and_cache_hits_are_recorded_without_content(self):
        context = {'details': {}}; token = _context.set(context)
        try:
            researcher = LocalResearcher(Cache())
            with patch('sales.research_analysis.api_json', side_effect=self.answer):
                researcher.call('Estrai', *self.inputs()[:2])
                researcher.call('Estrai', *self.inputs()[:2])
        finally: _context.reset(token)
        metrics = context['details']['model']
        self.assertEqual((metrics['calls'], metrics['cache_hits'], metrics['errors']), (1, 1, 0))
        self.assertEqual(metrics['eval_count'], 12)
        self.assertLess(metrics['input_chars_after'], metrics['input_chars_before'])
        self.assertNotIn('alfa', json.dumps(metrics))

    def test_stop_during_inference_does_not_cache_late_result(self):
        store = Cache(); stopped = False
        def check():
            if stopped: raise InterruptedError()
        def answer(*args, **kwargs):
            nonlocal stopped
            stopped = True
            return self.answer(*args, **kwargs)
        with patch('sales.research_analysis.api_json', side_effect=answer):
            with self.assertRaises(InterruptedError):
                LocalResearcher(store, check).call('Estrai', *self.inputs()[:2])
        self.assertFalse(store.values)

    def test_description_only_skips_proposal_after_reading_all_pages(self):
        docs = [{'id': str(i), 'url': f'https://alfa.example/{i}', 'official': True,
                 'checked_at': now(), 'text': text} for i, text in enumerate([
                     'Produciamo mobili in legno su misura per le aziende.',
                     'Realizziamo accessori industriali per i rivenditori.'])]
        def answer(task, data, schema):
            self.assertIn('units', data, 'A description alone must not generate a proposal')
            return {'claims': [{'unit_id': data['units'][0]['id'], 'kind': 'business'}]}
        with patch.object(LocalResearcher, 'call', side_effect=answer) as call:
            signals, proposal, review, limits = LocalResearcher(None).analyze({}, docs, {})
        self.assertEqual(call.call_count, 2); self.assertEqual(len(signals), 2)
        self.assertEqual(proposal['project'], 'none'); self.assertFalse(limits)
        self.assertEqual(review['outcome'], 'no_need_signal')
