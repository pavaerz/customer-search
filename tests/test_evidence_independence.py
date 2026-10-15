import unittest
from sales.research_rules import independent,validate_signals,qualify
from test_research import sample


class EvidenceIndependenceTests(unittest.TestCase):
    def test_same_origin_cannot_erase_a_contradiction(self):
        identity,docs,signals,proposal,review=sample()
        counter={**signals[0],'id':'counter','kind':'counterevidence','quote':'Il fornitore già selezionato ha concluso il progetto.'}
        signals.append(counter)
        kept=independent(signals)
        self.assertEqual(len(kept),2)
        result=qualify(identity,docs,signals,proposal,review)
        self.assertNotEqual(result['status'],'qualified')
        self.assertFalse(next(g['passed'] for g in result['gates'] if g['key']=='counterevidence'))

    def test_copied_article_keeps_distinct_facts_without_independence_bonus(self):
        identity,docs,_,proposal,review=sample()
        event='L’azienda inaugura una nuova rete di distribuzione in Germania.'
        gap='La piattaforma non permette ai distributori di gestire gli ordini multilistino.'
        docs=[{**docs[0],'id':str(n),'url':f'https://source{n}.example/news','text':event+' '+gap} for n in range(2)]
        claims=[{'document_id':'0','kind':'event','quote':event},{'document_id':'1','kind':'gap','quote':gap}]
        signals,errors=validate_signals(claims,docs);self.assertEqual(errors,[])
        ids=[s['id'] for s in signals];proposal['support_ids']=ids;review['support_ids']=ids
        result=qualify(identity,docs,signals,proposal,review)
        self.assertEqual(len(result['signals']),2)
        self.assertEqual(result['score_detail']['Riscontri indipendenti']['points'],0)
        self.assertNotEqual(result['status'],'qualified')

    def test_shared_template_does_not_merge_different_scoped_article_bodies(self):
        boilerplate=' '.join('menu'+str(i) for i in range(300))
        facts=['Abbiamo aperto una nuova divisione dedicata ai mercati esteri.',
               'Il portale clienti è già online e permette di inviare ordini.']
        docs=[{'id':str(n),'url':f'https://alfa.example/{n}','text':boilerplate+' '+fact,
               'research_text':fact,'body_scope':'articleBody','checked_at':'2026-10-14'} for n,fact in enumerate(facts)]
        signals,errors=validate_signals([{'document_id':str(n),'kind':'event' if n==0 else 'counterevidence','quote':fact} for n,fact in enumerate(facts)],docs)
        self.assertEqual(errors,[]);self.assertEqual(len(signals),2)
        self.assertEqual(len({s['event_key'] for s in signals}),2)

    def test_short_generic_quote_does_not_swallow_specific_fact(self):
        rows=[{'id':'a','kind':'business','event_key':'a','quote':'Produciamo componenti industriali.'},
              {'id':'b','kind':'event','event_key':'b','quote':'Produciamo componenti industriali. Abbiamo aperto un nuovo canale per distribuire la nuova linea in Germania.'}]
        self.assertEqual(len(independent(rows)),2)
        self.assertEqual(len(independent(rows+[dict(rows[1])])),2)

    def test_confidence_does_not_rise_with_more_quotes_from_one_copied_origin(self):
        identity,docs,signals,proposal,review=sample()
        for n,quote in enumerate(['Produciamo componenti per le aziende italiane.', 'La sede operativa si trova a Padova.']):
            signals.append({**signals[0],'id':'extra'+str(n),'kind':'business','quote':quote})
        proposal['support_ids']=[s['id'] for s in signals];review['support_ids']=proposal['support_ids']
        result=qualify(identity,docs,signals,proposal,review)
        self.assertEqual(result['status'],'qualified')
        self.assertEqual(result['confidence'],'media')
