"""3A.2: real saved KForge evidence and explicitly synthetic counterexamples.

The KForge fixture contains actual cached HTML matched to campaign documents.
No source is fetched and historical snapshots/revisions are never mutated.
"""
import gzip
import html
import json
import unittest
from pathlib import Path
from sales.commercial.intent import classify_block
from sales.commercial.context import channels, extract, followups
from sales.commercial.qualification import evaluate
from sales.commercial.evaluation import finish
from sales.db import digest
from test_commercial_engines import page

FIXTURE=Path(__file__).parent/'fixtures/commercial32/campaign14.json.gz'
IDENTITY={'name':'Alfa Srl','identity_status':'verified','website':'https://alfa.example/','group':'agencies','contacts':[]}
GEO={'eligible':True,'country':'Italia','conflicts':[]}


def result(text,engine='AGENCIES',**kwargs):
    return evaluate(engine,IDENTITY,page(text,**kwargs),GEO)


class CommercialIntent32Tests(unittest.TestCase):
    def test_actual_kforge_snapshot_is_partnership_seller_and_keeps_counterevidence(self):
        original=FIXTURE.read_bytes()
        with gzip.open(FIXTURE,'rt') as f:saved=json.load(f)
        row=next(r for r in saved['commercial_revisions'] if r['id']==735);old=row['body']
        self.assertEqual((old['state'],old['score']),('VERIFIED',100))
        with gzip.open(FIXTURE.with_name('campaign14-pages.json.gz'),'rt') as f:p=json.load(f)['pages'][old['url']]
        r=evaluate('AGENCIES',old['identity'],p,old['geography'])
        self.assertEqual(r['state'],'REJECTED')
        self.assertEqual(r['classification'],'seller')
        self.assertEqual(r['commercial_intent']['commercial_role'],'PARTNERSHIP_SELLER')
        self.assertTrue(any('Non cerchiamo fornitori' in n['quote'] for n in r['commercial_intent']['negations']))
        self.assertFalse(r['commercial_intent']['buyer_evidence'])
        self.assertTrue(r['evidence'])
        source=channels(p)['visible']['text']
        for proof in r['evidence']:
            self.assertEqual(source[proof['start']:proof['end']],proof['quote'])
            self.assertEqual(proof['source_hash'],digest(source))
        r['state']='VERIFIED';finish(r,old['identity'],[('Forced score',100,'Regression only')])
        self.assertNotEqual(r['state'],'VERIFIED')
        self.assertEqual(FIXTURE.read_bytes(),original)
        self.assertEqual(followups(p),[])

    def test_commercial_roles_require_direction_not_keywords(self):
        cases=[
            ('Cerchiamo sviluppatore WordPress freelance.','FREELANCE_BUYER'),
            ('Offriamo sviluppatori WordPress freelance alle aziende.','SELLER'),
            ('Cerchiamo un partner tecnico WordPress a cui affidare progetti.','PARTNERSHIP_BUYER'),
            ('Diventa Partner. Siamo il tuo partner tecnico per lo sviluppo WordPress.','PARTNERSHIP_SELLER'),
            ('Cerchiamo sviluppatore WordPress a tempo indeterminato.','EMPLOYER'),
            ('Cerchiamo sviluppatore WordPress con partita IVA.','FREELANCE_BUYER'),
            ('Cerchiamo sviluppatore WordPress.','BUYER'),
            ('Diventa partner. WordPress, sviluppatori, progetti.','UNKNOWN'),
            ('Trova sviluppatori freelance per il tuo progetto.','DIRECTORY'),
            ('Pubblica un progetto. Sviluppatori freelance disponibili.','AGGREGATOR'),
            ('Le migliori agenzie web in Italia','EDITORIAL')]
        for text,role in cases:
            with self.subTest(text=text):self.assertEqual(classify_block(text,title=text)['commercial_role'],role)

    def test_negative_requests_are_not_positive(self):
        for text in ('Non cerchiamo fornitori WordPress.','Non collaboriamo con freelance WordPress.','Non accettiamo candidature spontanee WordPress.','Diventa nostro cliente WordPress.','Affidaci il tuo progetto WordPress.'):
            with self.subTest(text=text):
                r=result(text);self.assertNotEqual(r['state'],'VERIFIED');self.assertFalse(r['commercial_intent']['buyer_evidence'])

    def test_negative_employee_with_positive_external_request(self):
        r=result('Non cerchiamo dipendenti, ma accettiamo collaborazioni con sviluppatori WordPress freelance.')
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertEqual(r['commercial_intent']['negations'][0]['target'],'employee')
        self.assertFalse(r['commercial_intent']['contradictions'])

    def test_spontaneous_application_exclusion_does_not_erase_open_position(self):
        r=result('Non accettiamo candidature spontanee. Cerchiamo sviluppatore WordPress freelance per questa posizione.')
        self.assertEqual(r['state'],'VERIFIED')

    def test_contradictions_keep_both_sides_and_require_review(self):
        for text in ('Cerchiamo sviluppatore WordPress freelance. Non collaboriamo con freelance.',
                     'Non cerchiamo freelance WordPress per questo progetto, ma per altri progetti sì.',
                     'Non cerchiamo freelance. Cerchiamo sviluppatore WordPress freelance per altri progetti.'):
            with self.subTest(text=text):
                r=result(text);self.assertEqual(r['state'],'NEEDS_REVIEW');self.assertTrue(r['commercial_intent']['contradictions'])
                self.assertTrue(r['evidence']);self.assertEqual(r['verification']['status'],'contradictory')

    def test_selling_and_buying_in_separate_sections_do_not_mix(self):
        p=page('',extra='<section><h2>Servizi</h2><p>Offriamo sviluppatori WordPress freelance ai clienti.</p></section><section><h2>Collaborazioni</h2><p>Cerchiamo sviluppatori frontend freelance per i nostri progetti.</p></section>')
        blocks=extract(p);self.assertEqual(len(blocks),1)
        self.assertNotIn('Offriamo',blocks[0]['text'])
        self.assertEqual(evaluate('AGENCIES',IDENTITY,p,GEO)['state'],'VERIFIED')

    def test_third_party_named_request_does_not_belong_to_page_owner(self):
        r=result('Beta Srl cerca sviluppatore WordPress freelance. Alfa Srl offre consulenza.')
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertTrue(any('diverso' in x for x in r['limits']))

    def test_two_subjects_in_same_block_require_review(self):
        r=result('Alfa Srl cerca sviluppatore WordPress freelance. Beta Srl cerca sviluppatore frontend freelance.')
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertTrue(any(c['code']=='multiple_request_subjects' for c in r['commercial_intent']['contradictions']))

    def test_explicit_reciprocal_partnership_not_automatically_verified(self):
        r=result('Cerchiamo partner tecnici WordPress freelance a cui affidare sviluppo. Offriamo sviluppatori alle agenzie partner in uno scambio reciproco.')
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertTrue(r['commercial_intent']['contradictions'])

    def test_generic_partnership_is_not_a_contract(self):
        self.assertNotEqual(result('Diventa partner. Progetti WordPress e collaborazioni.')['state'],'VERIFIED')

    def test_verified_has_source_addressable_proof_and_unknown_availability(self):
        r=result('Cerchiamo sviluppatore WordPress freelance.')
        self.assertEqual(r['state'],'VERIFIED')
        proof=r['verified_proof'];self.assertEqual(proof['subject'],'Alfa Srl')
        self.assertIn('Cerchiamo',proof['quote']);self.assertEqual(proof['url'],r['url'])
        self.assertEqual(proof['collaboration_type'],'external')
        self.assertEqual(proof['status'],'verified_request')
        self.assertTrue(proof['temporal_limits']);self.assertFalse(r['verification']['availability_verified'])
        self.assertTrue(all(r['verification']['checks'].values()))

    def test_missing_date_or_identity_cannot_be_compensated_by_score(self):
        r=result('Cerchiamo sviluppatore WordPress freelance.',date=False)
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertEqual(r['verification']['currentness'],'unknown')
        r['state']='VERIFIED';finish(r,IDENTITY,[('Forced score',100,'Regression only')])
        self.assertNotEqual(r['state'],'VERIFIED')
        r=evaluate('AGENCIES',{**IDENTITY,'identity_status':'unknown'},page('Cerchiamo sviluppatore WordPress freelance.'),GEO)
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertNotIn('verified_proof',r)

    def test_standing_invitation_is_not_claimed_as_active_project(self):
        r=result('Accettiamo collaborazioni continuative con sviluppatori WordPress freelance.',date=False)
        self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertEqual(r['verification']['currentness'],'standing_invitation')
        self.assertNotIn('verified_proof',r)
        self.assertIsNone(r['published_at'])

    def test_careers_parent_does_not_turn_service_links_into_followups(self):
        p=page('Diventa Partner. Siamo il tuo partner tecnico WordPress.',url='https://alfa.example/diventa-partner/',extra=''.join('<a href="'+path+'">'+text+'</a>' for path,text in [('/e-commerce/','e-Commerce'),('/web-applications/','Web applications'),('/consulenza-e-commerce-gratuita/','Consulenza e-commerce')]))
        self.assertEqual(followups(p),[])

    def test_followup_has_local_hiring_evidence(self):
        p=page('',extra='<p>Cerchiamo <a href="/ruolo-42">sviluppatore WordPress freelance</a> per progetti.</p>')
        links=followups(p);self.assertEqual(len(links),1)
        self.assertIn('Cerchiamo',links[0]['anchor_context'])
        self.assertTrue(links[0]['recruitment_context'])
        self.assertEqual(links[0]['commercial_role'],'FREELANCE_BUYER')

    def test_individual_portal_request_keeps_employer_unknown(self):
        from sales.commercial.context import source_kind
        from sales.commercial.attribution import identity
        p=page('Alfa Srl cerca sviluppatore WordPress freelance.',url='https://portal.example/offerta/432',extra='<p>Tutti gli annunci di terzi</p>')
        self.assertEqual(source_kind(p),'job_portal')
        owner=identity([p]);self.assertNotEqual(owner['identity_status'],'verified')
        r=evaluate('FREELANCE',owner,p,GEO)
        self.assertTrue(r['request_blocks']);self.assertNotEqual(r['state'],'VERIFIED')
