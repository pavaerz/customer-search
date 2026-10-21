"""Saved public original from 36; no live HTTP or AI. No invented outcome."""
import gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import passages,schema,grounding,qualification,ai,commercial_policy
from sales.commercial.indexed_jobs import same_company_name
from sales.research_analysis import identity_from

SAVED=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/agent6/campaign36/kondividi.json.gz').read_bytes()))

class Campaign36(unittest.TestCase):
    def setUp(self):
        self.r={**SAVED['document'],'id':'r1'}
    def test_saved_invitation_and_vat_survive_actual_payload_bound(self):
        ev=passages.bundle([self.r],4500)
        p={'task':schema.READ,'flow':'AGENCIES','result_ids':['r1'],'evidence':grounding.attach(ev)}
        while ai.input_bytes(p)>8192 and p['evidence']:p['evidence'].pop()
        text='\n'.join(e['text'] for e in p['evidence'])
        self.assertIn('cerchiamo collaboratori',text)
        self.assertIn('partita IVA attiva',text)
        self.assertFalse(passages.coverage([self.r],p['evidence'])[0]['uncovered_invitation_spans'])
        for e in p['evidence']:
            self.assertEqual(e['text'],self.r['text'][e['offset']:e['offset']+len(e['text'])])
            for s in grounding.segments(e):
                ref=grounding.resolve({'segment_id':s['segment_id']},p['evidence'])
                f=qualification.quote(ref,p['evidence'])
                self.assertEqual(f['quote'],self.r['text'][f['document_start']:f['document_end']])
    def test_original_identity_matches_brand_without_substring_matching(self):
        ident=identity_from([SAVED['page']])
        self.assertEqual(ident['identity_status'],'verified')
        self.assertEqual(ident['name'],'Kondividi Srls')
        for name in ['Kondividi Srls','Kondividi S.r.l.s.','Kondividi S. R. L. S.']:
            self.assertTrue(same_company_name(name,'KONDIVIDI'))
        for name in ['Kondividi Group Srls','Altra Kondividi Srls','Srls']:
            self.assertFalse(same_company_name(name,'KONDIVIDI'))
    def test_old_truncation_cannot_prove_absence(self):
        ev=schema.bundle([self.r],4500)
        e=next(e for e in ev if '\nKONDIVIDI\n' in e['text']);a=e['text'].index('KONDIVIDI')
        ref={'id':e['id'],'start':a,'end':a+len('KONDIVIDI')}
        analysis={'kind':'SUPPLIER_OFFER','facts':[{'field':'entity','ref':ref}],'missing':[]}
        src={**self.r,'allowed_regions':['Emilia-Romagna']}
        result=qualification.evaluate(src,analysis,ev,'AGENCIES',identity_from([SAVED['page']]))
        self.assertEqual(result['state'],'NEEDS_REVIEW')
        self.assertTrue(result['identity_verified'])
        self.assertEqual(result['budget']['kind'],'UNKNOWN')
    def test_selection_does_not_mix_document_offsets_or_ignore_negations(self):
        other={'id':'r2','url':'https://other.example','text':'Non cerchiamo freelance WordPress.\nPartita IVA non richiesta.','original':True}
        ev=passages.bundle([self.r,other],4500)
        for e in ev:
            original=self.r if e['result_id']=='r1' else other
            self.assertEqual(e['url'],original['url'])
            self.assertEqual(e['text'],original['text'][e['offset']:e['offset']+len(e['text'])])
        self.assertTrue(any('Non cerchiamo' in e['text'] for e in ev))
        self.assertLessEqual(sum(len(e['text'].encode()) for e in ev),4500)
    def test_short_document_keeps_complete_evidence(self):
        from test_agent6 import source,output,identity
        src=source();ev=passages.bundle([{'id':'1',**src}])
        self.assertEqual(''.join(e['text'] for e in ev),src['text'])

    def test_invitation_labelled_signal_still_warrants_original_read(self):
        text='Come Web Agency Modena in continua espansione, cerchiamo collaboratori con almeno due anni di esperienza nel web design e nel web marketing, pronti a ...'
        b={'state':'DISCOVERED','kind':'AGENCY_PARTNERSHIP','facts':[{'field':'signal','quote':text}]}
        self.assertTrue(commercial_policy.investigation(b,initial=True)['allowed'])
        self.assertFalse(commercial_policy.investigation(b,initial=False)['allowed'])
        self.assertEqual(b['state'],'DISCOVERED')
        self.assertEqual(b['facts'][0]['field'],'signal')

    def test_signal_fallback_does_not_admit_generic_negative_or_unpaid_invites(self):
        for text in ['Cerchiamo collaboratori.', 'Non cerchiamo collaboratori web design.',
                     'Cerchiamo collaboratori freelance WordPress a titolo gratuito.',
                     'I nostri collaboratori realizzano siti WordPress.',
                     'Cerchiamo collaboratori commerciali per servizi energetici.']:
            b={'state':'DISCOVERED','kind':'AGENCY_PARTNERSHIP','facts':[{'field':'signal','quote':text}]}
            self.assertFalse(commercial_policy.investigation(b,initial=True)['allowed'],text)

if __name__=='__main__':unittest.main()
