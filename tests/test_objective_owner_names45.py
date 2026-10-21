"""Owner name proofs from saved C45 HTML; no provider, database or registry calls."""
import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import decision
from sales.agent6.owner_names import collect, verified
from sales.agent6.grounding import attach, segments
from sales.commercial.identity import establish
from sales.db import digest

FIX = Path(__file__).parent/'fixtures/ai_first/campaign45'
PAGE = json.loads(gzip.decompress((FIX/'owner-original.json.gz').read_bytes()))
REAL = json.loads((FIX/'partial-browser.json').read_text())['body']
FULL = 'Rechsteiner di Florian von Stepski-Doliwa'


def identity(page=PAGE):
    original = establish([page])
    return {'name': original['name'], 'verified': original['identity_status'] == 'verified',
            'domain': 'rechsteiner.it', 'verified_names': collect(page, original)}


def replay():
    out = copy.deepcopy(REAL['ai_decision']); es = []
    for i, fact in enumerate(REAL['facts']):
        es.append({'id': 'saved'+str(i), 'text': fact['quote'], 'hash': digest(fact['quote']),
            'offset': fact['document_start'], 'document_id': fact['document_id'],
            'unit_id': 'saved-unit', 'result_id': 'saved-unit', 'original': True,
            'url': fact['url'], 'checked_at': fact['checked_at']})
    es = attach(es)
    out['facts'] = [{'field': f['field'], 'segment_id': segments(e)[0]['segment_id']}
                    for f, e in zip(REAL['facts'], es)]
    p = {'unit_id': 'saved-unit', 'evidence': es, 'identity': identity(), 'links': [],
         'dates': [], 'observed_at': PAGE['checked_at'], 'geography_allowed': True}
    return out, p


class Names(unittest.TestCase):
    def test_actual_public_name_and_proprietor_are_proven_on_same_original(self):
        before = copy.deepcopy(PAGE); ident = identity()
        self.assertEqual(ident['name'], 'Rechsteiner')
        self.assertEqual([a['name'] for a in ident['verified_names']], [FULL])
        self.assertTrue(verified(ident, FULL))
        self.assertFalse(verified({**ident, 'verified_names': []}, FULL))
        self.assertEqual(ident['verified_names'][0]['basis'], 'owned_proprietor_footer')
        self.assertEqual(PAGE, before)

    def test_real_negative_keeps_decision_while_preserving_owner_identity(self):
        out, p = replay()
        out, _ = decision.validate(out, p)
        body = decision.materialize({'url': PAGE['url'], 'original': True}, out, p['evidence'], p, 'AZIENDE')
        self.assertTrue(body['identity_verified'])
        self.assertEqual(body['entity_name'], FULL)
        self.assertEqual(body['identity']['name'], 'Rechsteiner')
        self.assertEqual(body['decision'], 'NOT_INTERESTING')
        self.assertEqual(body['state'], 'REJECTED')
        self.assertEqual(body['budget']['amount'], None)
        self.assertEqual(body['entity_key'], digest('domain:rechsteiner.it'))

    def test_partial_reordered_and_unproved_names_still_fail(self):
        ident = identity()
        for name in ('Rechstein', 'Rechsteiner di Florian', 'Florian von Stepski-Doliwa Rechsteiner', 'Rechsteiner Srl'):
            self.assertFalse(verified(ident, name), name)
        out, p = replay(); out['entity_name'] = 'Agriturismo Rechsteiner'
        with self.assertRaisesRegex(ValueError, 'unsupported_actor'):
            decision.validate(out, p)

    def test_foreign_domain_unverified_owner_and_conflicts_cannot_supply_alias(self):
        ident = establish([PAGE])
        for change in ({'website': 'https://unrelated.example'}, {'identity_status': 'unknown'},
                       {'identity_conflicts': [{'name': 'Other'}]}):
            self.assertEqual(collect(PAGE, {**ident, **change}), [])
        resolved = identity(); resolved['verified_names'][0]['url'] = 'https://unrelated.example/'
        self.assertFalse(verified(resolved, FULL))

    def test_footer_requires_address_and_valid_tax_number_on_same_line(self):
        ident = establish([PAGE])
        for old, new in [('P.I.: 04217720269', 'P.I.: 04217720260'),
                         ('P.I.: 04217720269', 'C.F.: 04217720269'),
                         ('Rechsteiner di Florian', 'Cliente Rechsteiner di Florian')]:
            self.assertIn(old, PAGE['html'])
            changed = {**PAGE, 'html': PAGE['html'].replace(old, new)}
            self.assertEqual(collect(changed, ident), [], (old, new))

    def test_names_in_hidden_credit_or_client_containers_do_not_link(self):
        ident = establish([PAGE])
        schema = '<script type="application/ld+json">'+json.dumps({'@type':'Organization', 'name':'Rechsteiner', 'url':'https://rechsteiner.it/'})+'</script>'
        legal = FULL+' - Via Roma 1, Padova P.I.: 04217720269'
        for attr in ('hidden', 'aria-hidden="true"', 'style="display: none"', 'class="credits"', 'class="clients"'):
            page = {**PAGE, 'html': schema+'<footer><div '+attr+'>'+legal+'</div></footer>'}
            self.assertEqual(collect(page, ident), [], attr)
        self.assertEqual(collect({**PAGE,'html':schema+'<p>'+legal+'</p>'}, ident), [])

    def test_two_proprietor_names_are_a_conflict_not_two_verified_owners(self):
        ident = establish([PAGE])
        other = '<footer>Rechsteiner di Altro Titolare - Via Roma 1, Padova P.I.: 04217720269</footer>'
        self.assertEqual(collect({**PAGE,'html':PAGE['html']+other}, ident), [])

    def test_explicit_owned_schema_pair_is_accepted_without_fuzzy_matching(self):
        org = {'@type':'Organization', 'name':'Marchio Alfa', 'legalName':'Alfa Servizi Srl', 'url':'https://alfa.example/'}
        page = {'url':org['url'], 'html':'<script type="application/ld+json">'+json.dumps(org)+'</script>'}
        ident = {'name':'Marchio Alfa', 'website':org['url'], 'identity_status':'verified'}
        aliases = collect(page, ident)
        self.assertEqual([a['name'] for a in aliases], ['Alfa Servizi Srl'])
        self.assertEqual(aliases[0]['basis'], 'owned_schema_name_legalName')

    def test_browser_request_cannot_borrow_a_different_verified_site(self):
        p = harness.payload(); out = harness.response(p)
        out.update(decision='NEEDS_RESEARCH', action={'type':'INSPECT_BROWSER', 'query':'', 'link_id':'', 'question':'Verificare il sito.'})
        p['identity']['name'] = 'Editore Altro'
        with self.assertRaisesRegex(ValueError, 'browser_scope_unverified'):
            decision.validate(out, p)

    def test_alias_does_not_substitute_missing_entity_citation(self):
        out, p = replay(); out['facts'] = [f for f in out['facts'] if f['field'] != 'entity']
        out['assessment'].update(intent_facts=[], scope_facts=[], solution_facts=[])
        with self.assertRaisesRegex(ValueError, 'unsupported_actor'):
            decision.validate(out, p)


class Integration(unittest.TestCase):
    def test_original_owner_proof_reaches_payload_and_saved_dossier(self):
        base = harness.IntegratedPath(); base.setUp(); self.addCleanup(base.tearDown)
        base.w.enqueue('candidate','AZIENDE',{'url':PAGE['url'],'original_page':PAGE,
            'query':'Rechsteiner sito ufficiale','strategy':'official_company_sector_region'},'owner45')
        with base.store.connect() as db:
            row = db.execute("SELECT * FROM research_tasks WHERE fingerprint='owner45'").fetchone()
            task = {**dict(row),'payload':json.loads(row['payload'])}
        captured = []
        def model(p, cfg, check):
            captured.append(p)
            entity = next(s for e in p['evidence'] for s in segments(e) if FULL in s['text'])
            out = copy.deepcopy(REAL['ai_decision'])
            out['facts'] = [{'field':'entity','segment_id':entity['segment_id']}]
            out['assessment'].update(intent_facts=[], scope_facts=[], solution_facts=[])
            out['subject_geography']={'status':'UNKNOWN','region':'','fact_indices':[],
                                     'reason':'Geografia non valutata dal test di identità.'}
            return {'output':out,'usage':{'input_tokens':100,'output_tokens':100}}
        with patch('sales.agent6.ai.infer', side_effect=model) as infer:
            base.w.execute(task, lambda:None)
            base.w.execute(task, lambda:None)
            self.assertEqual(infer.call_count, 1)
        self.assertTrue(captured)
        self.assertTrue(verified(captured[0]['identity'], FULL))
        with base.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(body['decision'], 'NOT_INTERESTING', body.get('technical_error'))
            self.assertTrue(body['identity_verified'])
            self.assertFalse(body.get('verification_hold'))
