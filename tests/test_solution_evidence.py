import unittest
from unittest.mock import patch
from sales.db import now
from sales.claim_selection import grounded_units
from sales.solution_evidence import materialize_solutions,eligible_units
from sales.research_analysis import LocalResearcher
from sales.research_rules import validate_signals,qualify
from sales.claim_grounding import grounded_kind
from test_research import sample


class SolutionEvidenceTests(unittest.TestCase):
    def test_only_literal_known_spans_are_accepted(self):
        text='Il nuovo negozio online è già operativo per tutti i rivenditori.'
        units=grounded_units('doc',text,text)
        claims,errors=materialize_solutions('doc',text,units,{'existing_solution_ids':[units[0]['id']]})
        self.assertFalse(errors);self.assertEqual(claims[0]['quote'],text)
        self.assertEqual(claims[0]['kind'],'counterevidence')
        for ids in (['inventato'],[[]],[True]):
            claims,errors=materialize_solutions('doc',text,units,{'existing_solution_ids':ids})
            self.assertFalse(claims);self.assertTrue(errors)

    def test_focused_check_supplies_counterproof_to_correlation(self):
        text='L’azienda presenta il suo nuovo sito web, disponibile anche in lingua inglese.'
        doc={'id':'original','text':text,'research_text':text,'url':'https://alfa.example/news',
             'official':True,'checked_at':now()}
        def answer(task,data,schema):
            if 'existing_solution_ids' in schema['properties']:
                return {'existing_solution_ids':[data['units'][0]['id']]}
            if 'units' in data:return {'claims':[{'unit_id':data['units'][0]['id'],'kind':'event'}]}
            self.assertEqual({s['kind'] for s in data['signals']},{'event','counterevidence'})
            return {'project':'none','support_ids':[],'critical_unknowns':[], 'budget_signal_id':''}
        with patch.object(LocalResearcher,'call',side_effect=answer):
            signals,proposal,review,limits=LocalResearcher(None).analyze({'name':'Alfa'},[doc],{})
        self.assertFalse(limits);self.assertEqual(proposal['project'],'none')
        self.assertEqual(len(signals),2)
        self.assertEqual(len({s['event_key'] for s in signals}),1)

    def test_two_roles_in_one_quote_do_not_create_independence(self):
        identity,docs,_,proposal,review=sample()
        quote=docs[0]['text']+' Il budget del progetto è di 6000 euro.'
        docs[0]['text']=quote
        signals,errors=validate_signals([{'document_id':docs[0]['id'],'quote':quote,'kind':kind}
                                         for kind in ('request','budget')],docs)
        self.assertFalse(errors);self.assertEqual(len(signals),2)
        proposal.update(support_ids=[s['id'] for s in signals],budget_signal_id=signals[1]['id'])
        review['support_ids']=proposal['support_ids']
        result=qualify(identity,docs,signals,proposal,review)
        self.assertEqual(result['budget'],6000)
        self.assertEqual(result['score_detail']['Riscontri indipendenti']['points'],0)
        self.assertEqual(result['confidence'],'media')

    def test_existing_website_does_not_by_itself_veto_a_documented_rebuild(self):
        args=sample()
        args[2].append({**args[2][0],'id':'existing','kind':'counterevidence',
                        'quote':'Il nostro sito aziendale è già online.','event_key':'existing'})
        self.assertEqual(qualify(*args)['status'],'qualified')
        args[4]['existing_solution_checked']=False
        self.assertNotEqual(qualify(*args)['status'],'qualified')
        args[4].update(existing_solution_checked=True,small_fix_sufficient=True)
        self.assertNotEqual(qualify(*args)['status'],'qualified')

    def test_closed_request_still_vetoes_model_approval(self):
        args=sample()
        args[2].append({**args[2][0],'id':'closed','kind':'counterevidence',
                        'quote':'La richiesta è chiusa: il fornitore già selezionato ha concluso il progetto.',
                        'event_key':'closed'})
        self.assertNotEqual(qualify(*args)['status'],'qualified')

    def test_no_extra_inference_for_unrelated_physical_facts(self):
        self.assertEqual(eligible_units([{'id':'a','text':'Produciamo carpenterie metalliche su misura.'}]),[])
        unit={'id':'b','text':'Il configuratore online è già disponibile.'}
        self.assertEqual(eligible_units([unit]),[unit])

    def test_unavailable_or_future_tool_is_not_an_operating_solution(self):
        for quote in ('Il nostro portale non è disponibile.',
                      'L’accesso al nostro portale è sospeso per un guasto.',
                      'Il nuovo shop sarà disponibile il mese prossimo.',
                      'Il portale è ancora in progettazione.'):
            self.assertEqual(grounded_kind('counterevidence',quote),'business')
        self.assertEqual(grounded_kind('counterevidence','Il nostro sito è già online.'),'counterevidence')

    def test_rejected_interpretation_keeps_literal_source_and_diagnostic(self):
        text='L’accesso al nostro portale è sospeso per un guasto.'
        doc={'id':'offline','text':text,'url':'https://alfa.example/avviso','checked_at':now()}
        signals,errors=validate_signals([{'document_id':'offline','kind':'counterevidence','quote':text}],[doc])
        self.assertFalse(errors);self.assertEqual(signals[0]['quote'],text)
        self.assertEqual(signals[0]['kind'],'business')
        self.assertEqual(signals[0]['model_kind'],'counterevidence')
        self.assertIn('non disponibile',signals[0]['classification_note'])
