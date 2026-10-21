"""Saved C46 originals; synthetic transport proves extraction, not model accuracy."""
import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import evidence
from sales.agent6.grounding import segments
from sales.agent6.passages import bundle
from sales.commercial.inspection import document
from sales.db import digest

FIX = json.loads(gzip.decompress((Path(__file__).parent /
    'fixtures/ai_first/campaign46/aptica-originals.json.gz').read_bytes()))
CAREERS = FIX['tasks']['7485']
INVITATION = 'Al momento non ci sono posizioni aperte ma una candidatura spontanea è sempre utile e siamo lieti di riceverla.'


def output(p, action=None):
    # Explicit offline double, deliberately NOT a promoted commercial lead.
    entity = next(s for e in p['evidence'] for s in segments(e) if 'Aptica Studio' in s['text'])
    out={'decision':'NEEDS_RESEARCH', 'entity_name':'Aptica Studio', 'subject_role':'OWNER',
            'relationship':'UNKNOWN', 'service':'frontend', 'reason':'Invito generico, contratto esterno sconosciuto.',
            'fit':'Frontend pertinente, disponibilità freelance da verificare.',
            'facts':[{'field':'entity','segment_id':entity['segment_id']}],
            'unknowns':['Collaborazione in partita IVA non provata.'], 'confidence':'MEDIUM',
            'priority':'low', 'compensation':'UNKNOWN', 'feasibility':'UNKNOWN',
            'currentness':'CURRENT_OBSERVATION',
            'assessment':{'intent':'COMPANY_ACTIVITY','intent_facts':[], 'scope':'UNKNOWN',
                          'scope_facts':[], 'existing_solution':'NOT_CHECKED','solution_facts':[],
                          'interpretation':'Verifica del contratto ancora necessaria.', 'objections':[]},
            'action':action or {'type':'STOP','link_id':'','query':'','question':'Sono ammessi collaboratori esterni?'}}
    if p.get('subject_scope_version')==1:
        out['subject_geography']={'status':'UNKNOWN','region':'','fact_indices':[],
                                  'reason':'Geografia non valutata da questo test di lettura.'}
    return out



class Extraction(unittest.TestCase):
    def test_saved_model_input_omitted_text_that_exists_in_the_original(self):
        text = document(CAREERS['original_page'])['text']
        self.assertIn(INVITATION, text)
        self.assertFalse(any(INVITATION in e['text'] for e in FIX['saved_ai_evidence_1201']))

    def test_short_destination_preserves_full_invitation_without_larger_total_budget(self):
        page=CAREERS['original_page']; doc=document(page); pack=evidence.packet(page,doc)
        result=evidence.passages(pack,pack['units'][0],3000)
        self.assertTrue(any(INVITATION in e['text'] for e in result))
        self.assertLessEqual(sum(len(e['text'].encode()) for e in result),3000)
        for e in result:
            self.assertEqual(e['text'],doc['text'][e['offset']:e['offset']+len(e['text'])])
            self.assertEqual(e['hash'],digest(e['text']))

    def test_long_careers_page_keeps_negative_and_spontaneous_conditions(self):
        for sentence in (INVITATION, 'No open positions; unsolicited applications are welcome.',
                         'Non accettiamo candidature freelance né portfolio spontanei.'):
            text=('Servizi e prodotti per aziende\n'*120)+sentence+'\nSviluppatore Front End\n'+('Informazioni\n'*100)
            records=[{'id':'one','url':'https://company.example/jobs','text':text,'original':True}]
            result=bundle(records,1600,compact=True)
            self.assertTrue(any(sentence in e['text'] for e in result), sentence)
            self.assertLessEqual(sum(len(e['text'].encode()) for e in result),1600)

    def test_invitation_outside_selected_ad_boundaries_stays_outside(self):
        text='Un annuncio diverso e senza richieste.\n'+INVITATION
        result=bundle([{'id':'one','url':'https://board.example','text':text,
                        'original':True,'allowed_ranges':[[0,38]]}],1600,compact=True)
        self.assertFalse(any(INVITATION in e['text'] for e in result))


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath(); self.base.setUp()
        self.addCleanup(self.base.tearDown)
        # Match the existing live Sol context cap; the new geography contract
        # is included in the input estimate. This changes only the test DB.
        self.base.c['filters']['commercial']['ai']['max_input_tokens']=20480
        with self.base.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',
                       (json.dumps(self.base.c['filters']),self.base.c['id']))

    def task(self,payload):
        self.base.w.enqueue('candidate','AGENCIES',payload,'reading46')
        with self.base.store.connect() as db:
            r=db.execute("SELECT * FROM research_tasks WHERE fingerprint='reading46'").fetchone()
            return {**dict(r),'payload':json.loads(r['payload'])}

    def test_destination_reaches_model_with_attribution_and_resume_has_one_call(self):
        task=self.task(copy.deepcopy(CAREERS)); captured=[]
        def infer(p,cfg,check):
            captured.append(p)
            return {'output':output(p),'usage':{'input_tokens':100,'output_tokens':100}}
        with patch('sales.agent6.ai.infer',side_effect=infer) as model:
            self.base.w.execute(task,lambda:None)
            variant=copy.deepcopy(task);variant['payload']['url']+='#main'
            self.base.w.execute(variant,lambda:None)
            self.assertEqual(model.call_count,1)
        p=captured[0]; es=p['evidence']
        matching=[e for e in es if INVITATION in e['text']]
        self.assertTrue(matching)
        self.assertEqual(matching[0]['url'],CAREERS['url'])
        self.assertNotEqual(matching[0]['document_id'],CAREERS['research_parent']['packet']['document_id'])
        self.assertTrue(any(e['url'].endswith('/white-label/') for e in es))
        # The same logical subject can cite separately attributed documents.
        self.assertTrue(all(e['unit_id']==p['unit_id'] for e in es))
        with self.base.store.connect() as db:
            bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertEqual(len(bodies),1)
            self.assertEqual(bodies[0]['decision'],'NEEDS_RESEARCH')
            self.assertIsNone(bodies[0]['budget']['amount'])
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],1)

    def test_legacy_fragment_link_on_current_original_does_not_schedule_another_read(self):
        task=self.task(copy.deepcopy(CAREERS))
        def infer(p,cfg,check):
            link=next(l for l in p['links'] if l['url'].endswith('#main'))
            return {'output':output(p,{'type':'READ_LINK','link_id':link['id'],'query':'',
                       'question':'Leggere il contenuto principale.'}),
                    'usage':{'input_tokens':100,'output_tokens':100}}
        # Current link selection removes same-page fragments before inference.
        # Retain defense-in-depth coverage for an older saved link selection.
        with patch('sales.agent6.ai.infer',side_effect=infer),patch(
                'sales.agent6.source_context.select_links',side_effect=lambda packet,*a:packet['links'][:8]):
            self.base.w.execute(task,lambda:None)
        with self.base.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM research_tasks').fetchone()[0],1)
            body=json.loads(db.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(body['validation_status'],'ACCEPTED',body.get('technical_error'))

    def test_cross_page_fragment_link_is_queued_once_with_canonical_destination(self):
        task=self.task(copy.deepcopy(FIX['tasks']['7480']))
        def infer(p,cfg,check):
            link=next(l for l in p['links'] if '/lavora-con-noi/' in l['url'])
            return {'output':output(p,{'type':'READ_LINK','link_id':link['id'],'query':'',
                       'question':'Sono ammessi freelance esterni?'}),
                    'usage':{'input_tokens':100,'output_tokens':100}}
        with patch('sales.agent6.ai.infer',side_effect=infer):
            self.base.w.execute(task,lambda:None)
        with self.base.store.connect() as db:
            rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE fingerprint!='reading46'")]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['url'],CAREERS['url'])
        self.assertEqual(rows[0]['research_parent']['link_url'],CAREERS['url'])
