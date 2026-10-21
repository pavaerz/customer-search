"""Real C52 originals and synthetic safety controls; all providers mocked."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch

from sales.agent6 import decision
from sales.agent6.request_collections import observe
from sales.commercial.inspection import document
from sales.db import digest
import test_ai_first as h

PAGES=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/source53/originals.json.gz').read_bytes()))


def collection_page(extra='', entries=None):
    entries=entries or [{'@type':'ListItem','url':'https://board.example/request/'+str(i),'name':name}
                       for i,name in enumerate(('Progetto Alfa','Progetto Beta'))]
    schema={'@type':'CollectionPage','url':'https://board.example/list',
            'mainEntity':{'@type':'ItemList','itemListElement':entries}}
    html='<script type="application/ld+json">'+json.dumps(schema)+'</script><main>'
    for item in entries:
        html+='<a href="'+item['url']+'"><h2>'+item['name']+'</h2><p>Cerchiamo uno sviluppatore freelance per un progetto frontend. Condizioni economiche da verificare.</p>'+extra+'</a>'
    return {'url':'https://board.example/list','html':html+'</main>','checked_at':h.DATE,'status':200,'content_type':'text/html'}


class LiteralCards(unittest.TestCase):
    def test_real_twenty_four_cards_remain_disjoint_and_source_bound(self):
        page=PAGES[1];doc=document(page);c=observe(page,doc)
        self.assertEqual(len(c['cards']),24)
        self.assertEqual(len(c['selected']),3)
        for card in c['cards']:
            self.assertEqual(doc['text'][card['document_start']:card['document_end']],card['text'])
            self.assertEqual(card['content_hash'],digest(card['text']))
            self.assertEqual(card['document_id'],doc['id'])
            self.assertNotIn('identity_verified',card)
            self.assertNotIn('published_at',card)
        target=next(x for x in c['cards'] if x['title']=='Hajlo grandine Camper')
        self.assertIn('30% equity',target['text'])
        self.assertNotIn('ProntoVisite',target['text'])
        self.assertNotIn('Salerno',target['text'])
        self.assertTrue(any('Contaminiamoci' in x['title'] for x in c['selected']))

    def test_original_vacancy_and_product_lists_are_not_request_collections(self):
        self.assertIsNone(observe(PAGES[0],document(PAGES[0])))
        page=collection_page();page['html']=page['html'].replace('CollectionPage','Product')
        self.assertIsNone(observe(page,document(page)))

    def test_collection_schema_alone_does_not_divert_company_product_catalogue(self):
        page=collection_page()
        page['html']=page['html'].replace(
            'Cerchiamo uno sviluppatore freelance per un progetto frontend. Condizioni economiche da verificare.',
            'Catalogo di prodotti industriali con caratteristiche tecniche e configurazioni. Richiedi un preventivo.')
        self.assertIsNone(observe(page,document(page)))

    def test_real_job_does_not_offer_its_cookie_control_as_another_original(self):
        from sales.agent6.evidence import packet
        from sales.agent6.source_context import select_links
        p=packet(PAGES[0],document(PAGES[0]))
        links=select_links(p,p['units'][0],'STARTUPS',True)
        self.assertFalse(any(l['url'].split('#')[0]==PAGES[0]['url'] for l in links))
        self.assertTrue(any('/contatti/' in l['url'] for l in links))

    def test_structure_without_visible_cards_or_heading_match_is_insufficient(self):
        for replace in (('<h2>','<p>'),('Progetto Beta</h2>','Titolo diverso</h2>')):
            page=collection_page();page['html']=page['html'].replace(*replace)
            self.assertIsNone(observe(page,document(page)))

    def test_hidden_cards_and_hidden_text_do_not_supply_routing_proofs(self):
        for attr in ('hidden','aria-hidden="true"','style="display:none"','class="related-posts"'):
            page=collection_page();page['html']=page['html'].replace('<main>','<main><div '+attr+'>').replace('</main>','</div></main>')
            self.assertIsNone(observe(page,document(page)))
        page=collection_page('<span hidden>Hidden demand must not be used.</span>')
        self.assertIsNone(observe(page,document(page)))

    def test_external_pdf_action_and_ambiguous_repeated_cards_not_followed(self):
        for url in ('https://elsewhere.example/request/2','https://board.example/document.pdf',
                    'https://board.example/delete?id=2','https://board.example/list?page=2'):
            entries=[{'@type':'ListItem','name':'Progetto Alfa','url':'https://board.example/request/1'},
                     {'@type':'ListItem','name':'Progetto Beta','url':url}]
            page=collection_page(entries=entries)
            self.assertIsNone(observe(page,document(page)))
        page=collection_page();page['html']+=page['html']
        self.assertIsNone(observe(page,document(page)))


class QueueRouting(unittest.TestCase):
    def setUp(self):
        self.base=h.IntegratedPath();self.base.setUp()
        self.task={'id':1,'kind':'candidate','strategy':'STARTUPS','payload':{
            'url':PAGES[1]['url'],'original_page':copy.deepcopy(PAGES[1]),'depth':0,
            'query':'startup Veneto cerca co-founder tecnico','strategy':'technical_cofounder'}}

    def tearDown(self):self.base.tearDown()

    def queued(self):
        with self.base.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='candidate'")]

    def run_collection(self,check=lambda:None):
        with patch.object(self.base.w,'model',side_effect=AssertionError('No AI on multi-subject collection')),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Use checkpoint, no network')):
            self.base.w.execute(self.task,check)

    def test_real_collection_queues_three_originals_without_identity_or_geography_transfer(self):
        self.run_collection();rows=self.queued();self.assertEqual(len(rows),3)
        for p in rows:
            self.assertEqual(p['depth'],1)
            self.assertNotIn('original_page',p)
            self.assertNotIn('research_parent',p)
            self.assertNotIn('expected_entity',p)
            self.assertNotIn('region',p)
            self.assertEqual(p['listing_origin']['url'],p['url'])
        with self.base.store.connect() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['validation_status'],'COLLECTION_ONLY')
        self.assertIsNone(records[0]['decision']);self.assertIsNone(records[0]['entity_name'])

    def test_resume_does_not_duplicate_links_or_change_candidate_quota(self):
        self.run_collection()
        with self.base.store.connect() as db:before=[tuple(r) for r in db.execute("SELECT * FROM commercial_resources WHERE resource!='runtime_seconds'")]
        self.run_collection()
        self.assertEqual(len(self.queued()),3)
        with self.base.store.connect() as db:self.assertEqual(before,[tuple(r) for r in db.execute("SELECT * FROM commercial_resources WHERE resource!='runtime_seconds'")])

    def test_stop_during_routing_keeps_first_link_and_resumes_without_duplicates(self):
        enqueue=self.base.w.enqueue;calls=[]
        def stop(*a,**kw):
            calls.append(a)
            if len(calls)==2:raise InterruptedError('Synthetic Stop')
            return enqueue(*a,**kw)
        with patch.object(self.base.w,'enqueue',side_effect=stop):
            with self.assertRaises(InterruptedError):self.run_collection()
        self.assertEqual(len(self.queued()),1)
        self.run_collection();self.assertEqual(len(self.queued()),3)

    def test_depth_budget_and_suppression_never_bypassed(self):
        self.task['payload']['depth']=self.base.w.settings['max_verification_depth']
        self.run_collection();self.assertEqual(self.queued(),[])
        self.task['payload']['depth']=0
        with patch.object(self.base.w.rs,'suppressed',return_value='Do not contact'):
            self.run_collection()
        self.assertEqual(self.queued(),[])
        from sales.commercial.resources import BudgetExceeded
        with patch.object(self.base.w,'enqueue',side_effect=BudgetExceeded('followups')):
            self.run_collection()
        self.assertEqual(self.queued(),[])


class CurrentnessContract(unittest.TestCase):
    def test_stale_compatible_request_can_be_researched_but_not_promoted(self):
        p=h.payload();p['links']=[{'id':'careers','url':'https://alfa.example/careers'}]
        p['dates']=[{'role':'published_at','value':'2021-10-27'}]
        out=h.response(p);out.update(currentness='STALE',relationship='EXPLICIT_REQUEST',decision='NEEDS_RESEARCH')
        out['action']={'type':'READ_LINK','link_id':'careers','query':'','question':'La selezione freelance risulta ancora aperta nelle posizioni attuali?'}
        self.assertEqual(decision.validate(out,p)[0]['decision'],'NEEDS_RESEARCH')
        out['decision']='INTERESTING'
        out['assessment']['intent']='REQUESTING_EXTERNAL'
        with self.assertRaisesRegex(ValueError,'currentness_unverified'):decision.validate(out,p)

    def test_explicit_closed_fact_still_prevents_promotion(self):
        p=h.payload();out=h.response(p)
        out['facts'].append({'field':'closed','segment_id':out['facts'][1]['segment_id']})
        with self.assertRaisesRegex(ValueError,'closed_opportunity'):decision.validate(out,p)


class ContractCache(unittest.TestCase):
    def setUp(self):
        self.b=h.IntegratedPath();self.b.setUp()
        self.b.c['filters']['commercial']['ai']['max_input_tokens']=20480

    def tearDown(self):self.b.tearDown()

    def call(self,key,provider):
        from sales.agent6.ai import call
        return call(self.b.store,self.b.c,'AGENCIES',key,h.payload(),lambda:None,provider)

    def test_new_contract_not_cached_as_old_but_resume_stays_free(self):
        def provider(p,c,g):return {'output':h.response(p),'usage':{'input_tokens':100,'output_tokens':100}}
        first=self.call('page:first',provider)
        self.assertEqual(first['status'],'completed')
        with patch('sales.agent6.decision.SYSTEM',decision.SYSTEM+'\nA synthetic changed instruction.'):
            with patch('sales.agent6.ai.infer',side_effect=AssertionError('Resume must not invoke provider')):
                replay=self.call('page:first',None)
            self.assertTrue(replay['replayed']);self.assertTrue(replay['replayed_prior_contract'])
            seen=[]
            def fresh(p,c,g):seen.append(p);return provider(p,c,g)
            second=self.call('page:new-logical-call',fresh)
            self.assertEqual(second['status'],'completed');self.assertEqual(len(seen),1)
            self.assertNotEqual(first['contract_fingerprint'],second['contract_fingerprint'])
            self.assertEqual(first['input_fingerprint'],second['input_fingerprint'])
            cached=self.call('page:next',lambda *a: self.fail('Same new contract must reuse cache'))
            self.assertTrue(cached['cache_hit'])

    def test_legacy_completed_call_resumes_without_paid_reanalysis(self):
        from sales.agent6.grounding import attach
        from sales.db import encode
        def provider(p,c,g):return {'output':h.response(p),'usage':{'input_tokens':100,'output_tokens':100}}
        first=self.call('page:first',provider)
        p=h.payload();p['evidence']=attach(p['evidence']);cfg=self.b.c['filters']['commercial']['ai']
        legacy=digest(encode([cfg['provider'],cfg['endpoint'],cfg['model'],'commercial-assessment-v3',p]))
        with self.b.store.connect() as db:
            row=db.execute('SELECT body FROM commercial_ai_executions WHERE id=?',(first['execution_id'],)).fetchone()
            body=json.loads(row[0]);body.pop('input_fingerprint',None);body.pop('contract_fingerprint',None)
            db.execute('UPDATE commercial_ai_executions SET body=?,cache_key=? WHERE id=?',(encode(body),legacy,first['execution_id']))
        replay=self.call('page:first',lambda *a:self.fail('Legacy resume must not spend again'))
        self.assertTrue(replay['replayed']);self.assertTrue(replay['replayed_prior_contract'])
