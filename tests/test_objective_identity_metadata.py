"""Real C44 metadata regression; no network, inference or historical writes."""
import gzip
import json
import unittest
from pathlib import Path

from sales.commercial.identity import establish, metadata_brand, seo_name

NOISY='Alkimedia, Realizzazione siti web, creazione siti internet, progettazione grafica, posizionamento siti internet'


class OwnerNames(unittest.TestCase):
    def test_real_c44_seo_list_has_separate_visible_owner_brand(self):
        cases=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/campaign44/originals.json.gz').read_bytes()))
        original=next(c['page'] for c in cases if 'webbes.it' in c['page']['url'])
        identity=establish([original])
        self.assertEqual(identity['name'],'Alkimedia')
        self.assertEqual(identity['identity_status'],'verified')
        proof=next(c for c in identity['identity_evidence'] if c['method']=='owned_metadata_and_visible_self_identification')
        self.assertEqual(proof['quote'],'Noi di Alkimedia')
        self.assertEqual(identity['identity_original']['name'],NOISY)
        self.assertEqual(identity['name_fields']['legal_name'],None)

    def test_metadata_prefix_without_self_identification_is_not_a_brand_proof(self):
        for text in ('Il nostro cliente Alkimedia cerca freelance.',
                     'Noi di AlkimediaPartner lavoriamo per clienti.',
                     'Alkimedia, Realizzazione siti web',
                     'Il logo Alkimedia è nel nostro portfolio.'):
            self.assertIsNone(metadata_brand(NOISY,text))
        self.assertIsNone(metadata_brand('Unioncamere Piemon','Noi di Unioncamere Piemonte'))

    def test_service_description_does_not_poison_an_independent_legal_name(self):
        html='<title>Alfa Srl</title><h1>Alfa Srl</h1><footer>Alfa Srl<br>P. IVA 12345678901<br>Via Roma 3, Padova Veneto<br>info@alfa.example</footer>'
        html+='<script type="application/ld+json">'+json.dumps({'@type':'Organization','name':NOISY,'url':'https://alfa.example'})+'</script>'
        identity=establish([{'url':'https://alfa.example/','html':html,'checked_at':'2026-10-20T12:00:00+00:00'}])
        self.assertEqual(identity['name'],'Alfa Srl')
        self.assertFalse(seo_name('Studio Ricerca, Sviluppo e Innovazione Srl'))
        self.assertTrue(seo_name(NOISY))
