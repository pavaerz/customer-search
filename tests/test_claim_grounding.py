import unittest
from unittest.mock import patch
from sales.db import now
from sales.research_analysis import LocalResearcher
from sales.claim_grounding import grounded_kind
from test_research import sample
from sales.research_rules import qualify

class GroundedClaimTests(unittest.TestCase):
    def test_no_project_does_not_create_fictional_technical_requirements(self):
        text='Gli ordini dei rivenditori vengono ricevuti tramite email.'
        doc={'id':'original','url':'https://alfa.example/ordini','text':text,'checked_at':now(),'official':True}
        def answer(task,data,schema):
            if 'units' in data:return {'claims':[{'unit_id':data['units'][0]['id'],'kind':'process'}]}
            if 'proposal' in data:self.fail('Nessuna proposta da revisionare: non sprecare un’altra inferenza')
            return {'project':'none','why':'','why_now':'','proposal':'','scope':'unknown','feasibility':'unknown',
                    'support_ids':[],'critical_unknowns':['Sicurezza web app immaginata'],'objections':[], 'budget_signal_id':''}
        with patch.object(LocalResearcher,'call',side_effect=answer):
            signals,proposal,review,limits=LocalResearcher(None).analyze({'name':'Alfa'},[doc],{})
        self.assertEqual(proposal['critical_unknowns'],[])
        self.assertEqual(proposal['project'],'none');self.assertEqual(review['status'],'insufficient')
        self.assertEqual(limits,[]);self.assertTrue(signals)
    def test_manufacturing_slogans_cannot_become_digital_gaps(self):
        for kind,quote in [('gap','Trasformiamo la complessità in semplicità. Flessibilità nella definizione del costo del prodotto finale.'),('process','Produciamo bevande vegetali conto terzi con materie prime innovative.'),('request','Scopri le nostre certificazioni e richiedi informazioni sui nostri prodotti.')]:
            self.assertEqual(grounded_kind(kind,quote),'business')
    def test_literal_digital_procedure_and_gap_retained(self):
        self.assertEqual(grounded_kind('gap','Il portale attuale non consente di gestire ordini multilistino.'),'gap')
        self.assertEqual(grounded_kind('process','Gli ordini devono essere trascritti in Excel.'),'process')
        self.assertEqual(grounded_kind('request','Cerchiamo un fornitore per il rifacimento completo del sito aziendale.'),'request')
    def test_fabricated_interpretation_cannot_pass_even_with_positive_model_review(self):
        identity,docs,signals,proposal,review=sample()
        signals[0].update(kind='process',quote='Produciamo bevande vegetali conto terzi con materie prime innovative.')
        signals.append({**signals[0],'id':'second','kind':'gap','quote':'Trasformiamo la complessità in semplicità.','event_key':'other'})
        proposal['support_ids']=[s['id'] for s in signals];review['support_ids']=proposal['support_ids']
        result=qualify(identity,docs,signals,proposal,review)
        self.assertNotEqual(result['status'],'qualified')
        self.assertFalse(next(g['passed'] for g in result['gates'] if g['key']=='need'))
        self.assertEqual(result['score_detail']['Concretezza del bisogno']['points'],0)
