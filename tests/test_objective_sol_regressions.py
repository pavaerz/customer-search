"""Real saved-page and model-output regressions; no network or inference."""
import copy
import gzip
import json
import unittest
from pathlib import Path

from sales.agent6 import decision,evidence
from sales.agent6.schema import ValidationError
from sales.commercial.inspection import document

ROOT=Path(__file__).resolve().parents[1]


class CaseInsensitiveIdentity(unittest.TestCase):
    def setUp(self):
        self.case=json.loads((ROOT/'tests/fixtures/ai_first/sol-case-identity.json').read_text())

    def test_actual_sol_uppercase_quote_is_not_a_different_company(self):
        before=copy.deepcopy(self.case)
        out,_=decision.validate(self.case['output'],self.case['payload'])
        self.assertEqual(out['entity_name'],'Alkimedia')
        self.assertEqual(out['decision'],'NEEDS_RESEARCH')
        self.assertEqual(self.case,before)
        source={'url':self.case['payload']['evidence'][0]['url'],'original':True,
                'checked_at':self.case['payload']['observed_at']}
        body=decision.materialize(source,out,self.case['payload']['evidence'],self.case['payload'],'AGENCIES')
        entity=next(f for f in body['facts'] if f['field']=='entity')
        self.assertIn('ALKIMEDIA',entity['quote'])
        self.assertFalse(decision.projection(body)['READY_FOR_OUTREACH'])

    def test_case_tolerance_does_not_accept_partial_or_different_names(self):
        for name in ('Alki','Media','Alkimedia Srl','Alkimedia Beta'):
            out=copy.deepcopy(self.case['output']);out['entity_name']=name
            with self.subTest(name=name),self.assertRaisesRegex(ValidationError,'unsupported_actor'):
                decision.validate(out,self.case['payload'])

    def test_wrong_entity_passage_still_rejected(self):
        out=copy.deepcopy(self.case['output'])
        out['facts'][0]['segment_id']=out['facts'][3]['segment_id']
        with self.assertRaisesRegex(ValidationError,'unsupported_actor'):
            decision.validate(out,self.case['payload'])


class OriginalLinkRetention(unittest.TestCase):
    def test_real_pyramid_careers_label_survives_icon_duplicate_and_cap(self):
        saved=json.loads(gzip.decompress((ROOT/'tests/fixtures/ai_first/campaign44/originals.json.gz').read_bytes()))
        page=next(r['page'] for r in saved if 'lapyramid.it/' in r['page']['url'])
        links=evidence.packet(page,document(page))['links']
        target='https://www.lapyramid.it/offerte-di-lavoro-digital-marketing/'
        rows=[l for l in links if l['url']==target]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['label'],'Lavora con Noi')
        self.assertIn(rows[0],links[:8])

    def test_many_services_do_not_hide_careers_or_allow_pdf_and_actions(self):
        page={'url':'https://agency.example/','status':200,'checked_at':'2026-10-20T00:00:00Z',
              'html':''.join('<a href="/service/'+str(i)+'">Servizi '+str(i)+'</a>' for i in range(20))+
                     '<a href="/jobs/"><img src="/icon.png"></a>'+
                     '<a href="/jobs/">Careers</a><a href="/contact/">Contact</a>'+
                     '<a href="/jobs.pdf">Careers PDF</a><a href="/delete">Careers</a>'+
                     '<a href="/jobs/?token=private">Jobs</a>'}
        packet=evidence.packet(page,document(page));links=packet['links']
        self.assertEqual(links[0]['url'],'https://agency.example/jobs/')
        self.assertEqual(links[0]['label'],'Careers')
        self.assertEqual(links[1]['label'],'Contact')
        self.assertEqual(len(links),22)
        self.assertNotIn('decision',packet)
