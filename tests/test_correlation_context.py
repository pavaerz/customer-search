import unittest
from sales.correlation_context import select


class CorrelationContextTests(unittest.TestCase):
    def signal(self,n,kind='business',quote='Produciamo componenti metallici in serie.'):
        return {'id':str(n),'document_id':'doc'+str(n%3),'kind':kind,'quote':quote}
    def test_risk_and_existing_solution_after_many_background_quotes_are_preserved(self):
        signals=[self.signal(i) for i in range(40)]+[self.signal(40,'risk','Dati sanitari'),self.signal(41,'business','Il nostro nuovo sito è già online.'),self.signal(42,'budget','Budget del progetto: 1000 euro.')]
        selected,note,limits=select(signals)
        self.assertEqual(limits,[]);self.assertEqual(note['background_omitted'],37)
        self.assertTrue({'40','41','42'}<={s['id'] for s in selected})
        self.assertEqual(len(signals),43)
    def test_material_facts_are_kept_for_bounded_batch_review(self):
        selected,note,limits=select([self.signal(i,'counterevidence',f'Soluzione operativa verificata {i}') for i in range(25)])
        self.assertEqual(len(selected),25);self.assertEqual(note['decision_evidence'],25)
        self.assertTrue(note['requires_batches']);self.assertEqual(limits,[])
