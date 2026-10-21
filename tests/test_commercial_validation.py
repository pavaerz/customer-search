"""Frozen original HTML and offline contracts, never model accuracy."""
import gzip
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import evidence, decision
from sales.agent6.grounding import segments
from sales.commercial.inspection import document
from sales.commercial.identity import establish
from sales.commercial.geography import locate, resolve_location
from sales.db import encode

FIXTURE=Path(__file__).parent/'fixtures/ai_first/commercial-originals.json.gz'


def originals():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def invitation_contract(payload):
    """Hand-authored review contract. No AI reasoning is simulated as measured."""
    name=payload['identity']['name']
    def ref(field,predicate):
        s=next((s for e in payload['evidence'] for s in segments(e) if predicate(s['text'])),None)
        if s is None:raise ValueError('missing_'+field)
        return {'field':field,'segment_id':s['segment_id']}
    out={'decision':'INTERESTING','entity_name':name,'subject_role':'OWNER',
            'relationship':'OPEN_FREELANCE_COLLABORATION','service':'frontend',
            'reason':'Invito pubblico a collaboratori digitali esterni.',
            'fit':'Possibile candidatura per sviluppo frontend e siti; incarichi da confermare.',
            'facts':[ref('entity',lambda t:name in t),
                     ref('request',lambda t:'cerchiamo collaboratori' in t.lower()),
                     ref('contact',lambda t:'@' in t)],
            'unknowns':['Compenso e incarichi attualmente disponibili'],
            'confidence':'HIGH','priority':'high','compensation':'UNKNOWN','feasibility':'UNKNOWN',
            'currentness':'STANDING_INVITATION',
            'assessment':{'intent':'ACCEPTING_EXTERNAL',
                          'intent_facts':[1],
                          'scope':'COLLABORATION',
                          'scope_facts':[1],
                          'existing_solution':'NOT_CHECKED','solution_facts':[],
                          'interpretation':'Invito pubblico a professionisti esterni.',
                          'objections':['Disponibilità di incarichi da confermare.']},
            'action':{'type':'REVIEW_OUTREACH','link_id':'','query':'','question':'Revisionare una candidatura spontanea.'}}
    if payload.get('subject_scope_version')==1:
        # These frozen originals have an explicit owner office, not merely a
        # service area. Keep this hand-authored contract on the current schema.
        office='Gerosa' if 'Kondividi' in name else 'Don Gennaro'
        fact=ref('geography',lambda t:office in t)
        selected=next(s for e in payload['evidence'] for s in segments(e)
                      if s['segment_id']==fact['segment_id'])
        region=resolve_location(selected['text'])['region']
        assert region in payload['allowed_regions']
        out['facts'].append(fact)
        out['subject_geography']={'status':'IN_TARGET','fact_indices':[len(out['facts'])-1],
                                 'region':region,'reason':'Sede dichiarata nel sito del soggetto.'}
    return out


class HistoricalExtraction(TestCase):
    def test_manufacturers_identity_geography_and_not_publishers(self):
        from sales.commercial.entity_scope import profile
        for key in ('D','E'):
            pages=originals()[key];identity=establish(pages);geo=locate(pages,identity)
            self.assertEqual(identity['identity_status'],'verified')
            self.assertIn('Veneto',geo['regions'])
            self.assertTrue(geo['eligible'])
            self.assertFalse(profile(pages[0])['multi_subject'])
        self.assertIn('CerealVeneta',establish(originals()['D'])['name'])
        for address in ('Via Ronchi 124/A Loreggia (PD) Italy','Via Roma 12 (PD)','Via Milano 3/B Padova'):
            self.assertEqual(resolve_location(address)['region'],'Veneto')
        self.assertIsNone(resolve_location('Via Roma')['region'])

    def test_irrelevant_profession_remains_in_model_evidence(self):
        p=originals()['C'][0];pack=evidence.packet(p,document(p))
        text='\n'.join(e['text'] for e in evidence.passages(pack,pack['units'][0],3000))
        self.assertIn('architetti, geometri',text)
        self.assertIn('sopralluoghi',text)

    def test_drupal_card_keeps_own_request_and_not_next_employer(self):
        p=originals()['F'][0];pack=evidence.packet(p,document(p))
        unit=next(u for u in pack['units'] if 'Organizzazione: Elice Group' in u['text'])
        self.assertIn('Cerchiamo sviluppatore freelance Drupal',unit['text'])
        self.assertNotIn('QUANTA',unit['text'])
        self.assertNotIn('DRUPAL DEVELOPER',unit['text'])
        self.assertIn('2015-11-03',[d['value'] for d in unit['dates']])
        self.assertIsNone(evidence.metadata_document(p,document(p),unit))

    def test_portal_detail_does_not_inherit_other_requester(self):
        p=originals()['G'][0];pack=evidence.packet(p,document(p))
        self.assertIn('ilGiornale.it',pack['units'][0]['text'])
        self.assertNotIn('Elice Group',pack['units'][0]['text'])
        self.assertEqual(next(d['value'] for d in pack['units'][0]['dates'] if d['role']=='published_at'),'2015-09-03')
        self.assertNotEqual(establish([p])['identity_status'],'verified')

    def test_structured_dates_are_used_with_roles_not_header_publication(self):
        page={'url':'https://alfa.example/job','checked_at':harness.DATE,'status':200,
              'last_modified':'Mon, 19 Oct 2026 10:00:00 GMT',
              'html':'<title>Job</title><meta name="description" content="Annuncio">'
              '<link rel="canonical" href="/job"><meta property="og:site_name" content="Alfa">'
              '<script type="application/ld+json">'+json.dumps({
                  '@type':'WebPage','url':'https://alfa.example/job','datePublished':'2015-11-03',
                  'dateModified':'2026-10-19','validThrough':'2015-12-01'})+'</script>'
              '<time itemprop="dateModified" datetime="2026-10-19"></time>'
              '<time datetime="2026-10-20"></time><p>Test</p>'}
        pack=evidence.packet(page,document(page));dates=pack['units'][0]['dates']
        self.assertEqual(pack['canonical_url'],page['url'])
        self.assertEqual(pack['description'],'Annuncio')
        self.assertEqual({d['value'] for d in dates if d['role']=='published_at'},{'2015-11-03'})
        self.assertTrue(any(d['origin']=='HTTP.Last-Modified' and d['role']=='modified_at' for d in dates))
        self.assertTrue(any(d['origin']=='HTML.time' and d['role']=='unassigned' for d in dates))
        self.assertTrue(any(d['role']=='expires_at' and d['value']=='2015-12-01' for d in dates))


class OriginalPipeline(harness.IntegratedPath):
    def test_one_flow_cannot_exhaust_shared_capacity_before_other_flows(self):
        from sales.agent6 import FLOWS,ai
        self.c['filters']['commercial_engines']=list(FLOWS)
        self.c['filters']['commercial']['ai'].update(max_calls_per_campaign=100,max_calls_per_engine=40,
                                                    max_calls_per_candidate=4,max_estimated_cost=2)
        with self.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.c['filters']),self.c['id']))
        def provider(p,cfg,check):
            check()
            return {'output':harness.response(p),'usage':{'input_tokens':100,'output_tokens':100}}
        def call(flow,index):
            p=harness.payload();p['flow']=flow;p['identity']['probe']=index
            return ai.call(self.store,self.c,flow,'page:test-'+flow+str(index),p,lambda:None,provider)
        for i in range(40):self.assertEqual(call('AZIENDE',i)['status'],'completed')
        self.assertEqual(call('AZIENDE',40)['status'],'budget_exhausted')
        for flow in FLOWS:
            if flow!='AZIENDE':self.assertEqual(call(flow,0)['status'],'completed')

    def test_real_invitation_sources_fit_actual_input_budget_and_reach_dossier(self):
        from sales.commercial.token_count import estimate
        from sales.agent6.alignment import dimensions
        for key in ('A','B','C'):
            page=originals()[key][0]
            self.w.enqueue('candidate','AGENCIES',{'url':page['url'],'title':'Originale congelato',
                           'query':'agenzia collaborazioni','strategy':'standing','depth':0},'real-'+key)
            with self.store.connect() as db:
                row=db.execute('SELECT * FROM research_tasks WHERE fingerprint=?',('real-'+key,)).fetchone()
                task={**dict(row),'payload':json.loads(row['payload'])}
            def provider(payload,cfg,check):
                check()
                self.assertLessEqual(estimate(payload,cfg)['tokens'],8192)
                if key=='C':
                    s=next(s for e in payload['evidence'] for s in segments(e) if 'architetti, geometri' in s['text'])
                    output=harness.response(harness.payload())
                    output.update(decision='NOT_INTERESTING',entity_name='',subject_role='UNKNOWN',
                                  relationship='UNKNOWN',service='unknown',currentness='UNKNOWN',
                                  reason='Richiesta di sopralluoghi per architetti e geometri, non sviluppo web.',
                                  facts=[{'field':'request','segment_id':s['segment_id']}],
                                  assessment={'intent':'REQUESTING_EXTERNAL','intent_facts':[0],
                                              'scope':'COLLABORATION','scope_facts':[0],
                                              'existing_solution':'NOT_CHECKED','solution_facts':[],
                                              'interpretation':'La professione richiesta è diversa.',
                                              'objections':[]},
                                  action={'type':'STOP','query':'','link_id':'','question':''})
                    if payload.get('subject_scope_version')==1:
                        output['subject_geography']={'status':'UNKNOWN','fact_indices':[],
                            'region':'','reason':'Sede non verificata; professione già incompatibile.'}
                else:output=invitation_contract(payload)
                return {'output':output,'usage':{'input_tokens':100,'output_tokens':100}}
            with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch('sales.agent6.ai.infer',side_effect=provider),patch(
                    'sales.agent6.qualification.evaluate',side_effect=AssertionError('Legacy gate')):
                self.w.execute(task,lambda:None)
            with self.store.connect() as db:
                row=db.execute('SELECT id,body FROM agent6_records WHERE json_extract(body,\'$.url\')=?',(page['url'],)).fetchone()
                b=json.loads(row['body'])
                for fact in b['facts']:
                    saved=db.execute('SELECT text FROM research_documents WHERE id=?',(fact['document_id'],)).fetchone()
                    self.assertIsNotNone(saved)
                    self.assertEqual(saved[0][fact['document_start']:fact['document_end']],fact['quote'])
            from sales.agent6.api import dossier
            self.assertEqual(dossier(self.store,row['id'])['body']['decision'],b['decision'])
            self.assertEqual(b['decision'],'NOT_INTERESTING' if key=='C' else 'INTERESTING',b.get('technical_error'))
            self.assertEqual(b['open_paid_project'],'UNKNOWN')
            if key!='C':self.assertTrue(dimensions(b)['CONTACT_AVAILABLE'])
            self.assertEqual(b['budget']['amount'],None)
