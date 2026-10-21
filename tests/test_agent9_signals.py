"""Campaign 38 originals; repairs are explicitly offline provider doubles."""
import gzip,json,hashlib,copy,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import qualification,signals,document_units,passages,schema,grounding
from sales.research_analysis import identity_from

CASES=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/agent9/campaign38.json.gz').read_bytes()))['cases']
KOND,BAKECA=CASES


def fact(source,field,text):
    start=source['text'].index(text)
    e={'id':'all','result_id':'r1','url':source['url'],'text':source['text'],
       'hash':hashlib.sha256(source['text'].encode()).hexdigest(),'original':True,'offset':0,'checked_at':source['checked_at']}
    return {'field':field,'ref':{'id':'all','start':start,'end':start+len(text)}},e


class Signals(unittest.TestCase):
    def test_original_hashes(self):
        for case in CASES:self.assertEqual(hashlib.sha256(case['source']['text'].encode()).hexdigest(),case['text_sha256'])

    def test_actual_model_rejection_is_challenged_even_with_invitation_in_payload(self):
        source=KOND['source'];a=KOND['analysis']['analyses'][0];e=KOND['evidence']
        self.assertTrue(any('cerchiamo collaboratori' in x['text'] for x in e))
        result=qualification.evaluate(source,a,e,'AGENCIES',identity_from([KOND['page']]))
        self.assertEqual(result['state'],'NEEDS_REVIEW')
        self.assertEqual(result['deterministic_completion']['superseded_kind'],'SUPPLIER_OFFER')
        kinds={s['type'] for s in result['commercial_signals']}
        self.assertIn('supplier_offer',kinds);self.assertIn('collaboration_invitation',kinds)
        self.assertEqual(result['budget']['kind'],'UNKNOWN')
        self.assertFalse(qualification.semantics.decision_metadata(result)['negative_feedback_reliable'])
        for s in result['commercial_signals']:
            self.assertEqual(s['quote'],source['text'][s['start']:s['end']])

    def test_signal_is_not_invented_from_supplier_negation_or_other_unit(self):
        for text in ('Offriamo siti web WordPress ai nostri clienti.',
                     'Non cerchiamo collaboratori web design.',
                     'Cercavamo sviluppatori WordPress per un progetto concluso.',
                     'Cerchiamo commerciali.\nOffriamo WordPress.'):
            source={**KOND['source'],'text':text}
            self.assertFalse(any(s['type']=='collaboration_invitation' for s in signals.extract_signals(source)))
        self.assertEqual(signals.extract_signals({**KOND['source'],'original':False}),[])

    def test_seo_headline_cannot_be_company_identity(self):
        for name in ('Web Agency Modena esperta in siti internet e SEO','VivereRoma è il supplemento romano di Vivere Srl'):
            self.assertFalse(schema.actor_span_valid(name,0,len(name)))
        for name in ('Kondividi Srls','Alfa Web Agency'):
            self.assertTrue(schema.actor_span_valid(name,0,len(name)))

    def test_invitation_heading_and_requirements_remain_one_local_signal(self):
        source={**KOND['source'],'text':'Collabora con noi\nCerchiamo professionisti esterni con partita IVA.\nSviluppatori WordPress e frontend per i nostri progetti.'}
        signals_found=signals.extract_signals(source)
        self.assertTrue(any(s['type']=='collaboration_invitation' for s in signals_found))
        unrelated=signals.extract_signals({**source,'text':'Cerchiamo commerciali.\nOffriamo WordPress ai clienti.'})
        self.assertEqual([s['type'] for s in unrelated],['supplier_offer'])

    def test_saved_bakeca_identity_is_not_borrowed_from_neighbour(self):
        source=BAKECA['source'];units=document_units.extract(source)
        self.assertGreater(len(units),2)
        req='Cercasi ragazzo (anche freelance) con conoscenza dei vari CMS, wordpress in primis, ma anche nell\'ordine Prestashop, Magento, e con bas …'
        f,e=fact(source,'request',req);owner,_=fact(source,'entity','VivereRoma è il supplemento romano di Vivere Srl')
        a={'kind':'BUYER_DEMAND','facts':[f,owner],'missing':[]}
        b=qualification.evaluate(source,a,[e],'STARTUPS')
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertIsNone(b['entity_name'])
        self.assertIn('cross_unit_attribution',b['semantic_issues'])
        self.assertTrue(b['withheld_evidence']);self.assertEqual(b['budget']['kind'],'UNKNOWN')
        request=next(f for f in b['facts'] if f['field']=='request')
        unit=next(u for u in units if u['id']==request['document_unit_id'])
        self.assertEqual(unit['subject'],'tattiche marketing')
        self.assertEqual(unit['date_quote'],'19/10/2026');self.assertEqual(unit['location_quote'],'Barletta')
        self.assertNotIn('VivereRoma',unit['text'])
        self.assertEqual(units,document_units.extract(source))

    def test_explicit_boundaries_required_and_cross_unit_budget_withheld(self):
        source={**BAKECA['source'],'text':'Cerchiamo freelance WordPress\nAzienda: Alfa Srl\n19/10/2026\nPadova\nCandidati\nBudget: € 5000\nAzienda: Beta Srl\n19/10/2026\nTorino\nCandidati'}
        facts=[]
        for field,text in [('request','Cerchiamo freelance WordPress'),('entity','Alfa Srl'),('budget','Budget: € 5000')]:
            f,e=fact(source,field,text);facts.append(f)
        b=qualification.evaluate(source,{'kind':'BUYER_DEMAND','facts':facts,'missing':[]},[e],'STARTUPS')
        self.assertNotIn('budget',[f['field'] for f in b['facts']])
        self.assertEqual(b['budget']['kind'],'UNKNOWN');self.assertIn('cross_unit_attribution',b['semantic_issues'])
        self.assertEqual(document_units.extract({**source,'text':'Alfa e Beta cercano WordPress'}),[])

    def test_worker_queues_one_original_repair_without_refetch_or_auto_promotion(self):
        import test_agent6_campaign32 as support
        base=support.Campaign32Fix();base.setUp();self.addCleanup(base.tearDown)
        base.c['filters']['commercial']['ai']['max_calls_per_candidate']=4
        page=copy.deepcopy(KOND['page']);url=page['url']
        base.rs.enqueue(base.c['id'],'candidate','AGENCIES',{'url':url,'query':'fixture','original_page':page,'depth':3},'signal-test')
        def model(p,cfg,check):
            if p.get('repair'):return {'output':{'invalid':'Synthetic failed recovery'},'usage':{'input_tokens':100,'output_tokens':50}}
            segments=[s for e in p['evidence'] for s in e['segments']]
            supplier=next(s for s in segments if 'servizi di web design' in s['text'])
            return {'output':{'analyses':[{'result_id':'r1','kind':'SUPPLIER_OFFER','kind_ref':{'segment_id':supplier['segment_id']},'facts':[], 'hypothesis':'Synthetic negative reproducing observed omission.','missing':[]}]},'input_tokens':100,'output_tokens':50}
        with patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('No refetch')),patch('sales.agent6.ai.infer',side_effect=model),patch('socket.create_connection',side_effect=AssertionError('Offline only')):
            task=base.rs.claim(base.c['id'],base.c['generation']);base.w.execute(task,lambda:None);base.rs.task_done(task['id'])
            repair=base.rs.claim(base.c['id'],base.c['generation'])
            self.assertIsNone(repair)  # 9.1 literal owner and invitation need no paid repair
        with base.store.connect() as c:
            b=json.loads(c.execute('select body from agent6_records order by id desc limit 1').fetchone()[0])
            self.assertEqual(b['state'],'NEEDS_REVIEW')
            self.assertTrue(b['deterministic_completion']['added_fields'])
            self.assertEqual(c.execute("select count(*) from research_tasks where state='pending'").fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0],1)

    def test_saved_invitation_without_currentness_stays_promising_not_qualified_crm(self):
        import test_agent6_campaign32 as support
        from sales.agent6.api import save_contact
        base=support.Campaign32Fix();base.setUp();self.addCleanup(base.tearDown)
        base.c['filters']['commercial']['ai']['max_calls_per_candidate']=4
        base.c['filters']['regions']=['Emilia-Romagna']
        page=copy.deepcopy(KOND['page']);url=page['url'];calls=[]
        base.rs.enqueue(base.c['id'],'candidate','AGENCIES',{'url':url,'query':'fixture','original_page':page},'positive-signal-test')
        def model(p,cfg,check):
            calls.append(p)
            segments=[s for e in p['evidence'] for s in e['segments']]
            def ref(predicate):return {'segment_id':next(s['segment_id'] for s in segments if predicate(s['text']))}
            request=ref(lambda t:'cerchiamo collaboratori' in t)
            a={'result_id':'r1','kind':'AGENCY_PARTNERSHIP','kind_ref':request,
               'facts':[{'field':'entity','ref':ref(lambda t:t=='Kondividi Srls')},
                        {'field':'request','ref':request},
                        {'field':'request','ref':ref(lambda t:'Siamo sempre alla ricerca' in t)},
                        {'field':'technical','ref':request},
                        {'field':'contract','ref':ref(lambda t:'partita IVA attiva' in t)}],
               'hypothesis':'Standing external collaboration, not a guaranteed project.','missing':[]}
            return {'output':{'analyses':[a]},'input_tokens':100,'output_tokens':100}
        with patch('socket.create_connection',side_effect=AssertionError('Offline only')),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('Saved page only')),patch('sales.agent6.ai.infer',side_effect=model):
            for _ in range(1):
                task=base.rs.claim(base.c['id'],base.c['generation']);base.w.execute(task,lambda:None);base.rs.task_done(task['id'])
            with base.store.connect() as c:
                row=c.execute('select id,body from agent6_records order by id desc limit 1').fetchone();b=json.loads(row['body'])
            self.assertEqual(b['state'],'NEEDS_REVIEW',b['reason'])
            self.assertIn('publication',b['missing'])
            self.assertTrue(b['completion_queue']['promising'])
            self.assertEqual(b['entity_name'],'Kondividi Srls');self.assertTrue(b['identity_verified'])
            self.assertEqual(b['budget']['kind'],'UNKNOWN');self.assertTrue(b['contacts'])
            self.assertEqual(b['collaboration_geography']['remote_work'],'UNKNOWN')
            with self.assertRaisesRegex(ValueError,'qualificazione'):
                save_contact(base.store,row['id'])
            with base.store.connect() as c:
                self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
                followups=[json.loads(r[0]) for r in c.execute("select payload from research_tasks where kind='search'")]
                self.assertEqual(len(followups),1)
                self.assertEqual(followups[0]['missing'],'publication')
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
