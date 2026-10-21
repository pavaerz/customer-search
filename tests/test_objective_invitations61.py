"""Saved real career originals; synthetic boundaries are explicitly labelled."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import evidence
from sales.agent6.career_roles import separate,owner_proof
from sales.agent6.response_channels import collect
from sales.agent6.source_context import select_links
from sales.commercial.inspection import document
from sales.commercial.identity import establish
import test_ai_first as h
from scripts.run_objective_validation_sol import SOL_CONFIG


def original(host):
    rows=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/reference60/originals.json.gz').read_bytes()))
    if isinstance(rows,dict):rows=list(rows.values())
    return copy.deepcopy(next(r['page'] for r in rows if host in r['url']))


class RoleScopes(unittest.TestCase):
    def setUp(self):
        self.page=original('jampaa');self.doc=document(self.page)
        self.packet=evidence.packet(self.page,self.doc)
        self.identity=establish([self.page])
        separate(self.page,self.packet,self.identity['identity_status']=='verified')

    def test_seven_real_roles_are_separate_literal_ranges(self):
        self.assertEqual(len(self.packet['units']),7)
        for u in self.packet['units']:
            self.assertEqual(u['text'],self.doc['text'][u['offset']:u['offset']+len(u['text'])])
        wp=self.packet['units'][0];ux=self.packet['units'][2]
        self.assertIn('40 ore settimanali',wp['text']);self.assertNotIn('full Remote',wp['text'])
        self.assertIn('full Remote',ux['text']);self.assertNotIn('40 ore settimanali',ux['text'])
        self.assertNotIn('Model Context Protocol',wp['text'])
        self.assertEqual(wp['dates'],[])  # Page observation/footer is not job publication.

    def test_scope_proofs_and_identity_offsets_are_grounded(self):
        for u in self.packet['units']:
            proof=evidence.passages(self.packet,u,3000)
            for e in proof:
                self.assertEqual(e['text'],self.doc['text'][e['offset']:e['offset']+len(e['text'])])
                self.assertGreaterEqual(e['offset'],u['offset'])
                self.assertLessEqual(e['offset']+len(e['text']),u['offset']+len(u['text']))
            owner=owner_proof(self.page,self.doc,u,self.identity)
            self.assertEqual(owner['text'],'JAMPAA S.R.L.')
            self.assertEqual(owner['text'],self.doc['text'][owner['offset']:owner['offset']+len(owner['text'])])

    def test_each_role_has_only_its_application_and_shared_owner_contact(self):
        values=[]
        for u in self.packet['units'][:3]:
            controls=collect(self.page,u,self.identity,True)
            forms=[c['value'] for c in controls if c['type']=='application_link']
            self.assertEqual(len(forms),1);values+=forms
            self.assertIn(forms[0],u['career_role']['links'])
            links=select_links(self.packet,u,'AGENCIES',True)
            self.assertTrue(all(l['url'] in u['career_role']['links'] for l in links))
        self.assertEqual(len(set(values)),3)

    def test_unverified_owner_and_non_career_pages_not_split(self):
        for verified,path in [(False,self.page['url']),(True,'https://www.jampaa.it/servizi/')]:
            p={**self.page,'url':path};pack=evidence.packet(p,document(p));separate(p,pack,verified)
            self.assertEqual(len(pack['units']),1)

    def test_real_closed_and_standing_pages_not_relabelled(self):
        for host in ('brainylabs','wp-ok','adviva'):
            p=original(host);pack=evidence.packet(p,document(p));before=copy.deepcopy(pack)
            separate(p,pack,True)
            self.assertEqual(pack,before)

    def test_synthetic_product_headings_without_invitation_are_not_roles(self):
        p={**self.page,'html':'<h2>WordPress</h2><p>Vendiamo siti web e servizi</p><h2>WooCommerce</h2><p>Vendiamo ecommerce</p>'}
        pack=evidence.packet(p,document(p));separate(p,pack,True)
        self.assertEqual(len(pack['units']),1)

    def test_long_synthetic_role_preserves_hours_and_closure(self):
        body='Cerchiamo uno sviluppatore WordPress freelance.\n'+('Competenze richieste PHP e CSS.\n'*100)+'40 ore settimanali\nQuesta posizione è chiusa\n'
        proof=evidence.passages({'final_url':self.page['url'],'document_id':'d','observed_at':'2026-10-21'},
            {'id':'u','origin':'page','text':body},1000)
        visible='\n'.join(e['text'] for e in proof)
        self.assertIn('40 ore settimanali',visible);self.assertIn('posizione è chiusa',visible)

    def test_synthetic_global_closure_is_not_lost_between_archived_roles(self):
        body='Cerchiamo uno sviluppatore WordPress. '+('Competenze PHP e CSS. '*20)+'Invia la tua candidatura.'
        p={**self.page,'html':'<p>Al momento non ci sono posizioni aperte.</p><h2>Frontend Developer</h2><p>'+body+'</p><h2>Backend Developer</h2><p>'+body+'</p>'}
        pack=evidence.packet(p,document(p));separate(p,pack,True)
        self.assertEqual(len(pack['units']),1)
        proof=evidence.passages(pack,pack['units'][0],700)
        self.assertTrue(any('non ci sono posizioni aperte' in e['text'] for e in proof))

class RoleQueue(unittest.TestCase):
    def test_actual_roles_get_distinct_ledger_records_without_extra_fetch_and_resume_replays(self):
        b=h.IntegratedPath();b.setUp()
        try:
            b.c['filters']['commercial']['ai'].update(SOL_CONFIG)
            b.c['filters']['commercial']['ai'].update(provider='MOCK',max_calls_per_engine=10)
            p=original('jampaa');seen=[]
            b.w.enqueue('candidate','AGENCIES',{'url':p['url'],'original_page':p},'role-test')
            def task(first=False):
                with b.store.connect() as db:
                    r=db.execute("SELECT * FROM research_tasks WHERE fingerprint='role-test'" if first else "SELECT * FROM research_tasks WHERE json_extract(payload,'$.unit_id') IS NOT NULL ORDER BY id LIMIT 1").fetchone()
                    return {**dict(r),'payload':json.loads(r['payload'])}
            def infer(payload,cfg,check):seen.append(copy.deepcopy(payload));return {'output':{},'usage':{}}
            with patch('sales.agent6.ai.infer',side_effect=infer),patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('offline')):
                first=task(True);b.w.execute(first,lambda:None)
                second=task();b.w.execute(second,lambda:None)
                with patch('sales.agent6.budget.remaining',return_value=0):
                    replay=b.w.execute(first,lambda:None)
                self.assertNotEqual(replay,{'deferred_resource':'ai_verify'})
            self.assertEqual(len(seen),2)
            self.assertNotEqual(seen[0]['unit_id'],seen[1]['unit_id'])
            self.assertEqual(seen[0]['metadata']['role_title'],'Sviluppatore WordPress')
            shown='\n'.join(e['text'] for e in seen[0]['evidence'])
            self.assertIn('40 ore settimanali',shown);self.assertIn('partita IVA',shown)
            self.assertNotIn('full Remote',shown)
            with b.store.connect() as db:
                keys=[r[0] for r in db.execute('SELECT candidate_id FROM commercial_ai_executions')]
                units=[r[0] for r in db.execute("SELECT json_extract(body,'$.evidence_unit_id') FROM agent6_records")]
            self.assertEqual(len(set(keys)),2);self.assertEqual(len(set(units)),2)
        finally:b.tearDown()

class GeographyRecovery(unittest.TestCase):
    def test_real_answer_is_rejected_but_explicitly_corrected_fact_type_is_valid(self):
        from sales.agent6.decision import validate
        r=json.loads((Path(__file__).parent/'fixtures/ai_first/reference60/geography-response.json').read_text())
        with self.assertRaisesRegex(ValueError,'wrong_geography_fact'):
            validate(r['response'],r['payload'])
        # Offline mutation, NOT a new model answer or automatic relabelling.
        corrected=copy.deepcopy(r['response'])
        cited=corrected['facts'][corrected['subject_geography']['fact_indices'][0]]
        corrected['facts'].append({**cited,'field':'geography'})
        corrected['subject_geography']['fact_indices']=[len(corrected['facts'])-1]
        out,_=validate(corrected,r['payload'])
        self.assertEqual(out['decision'],'NEEDS_RESEARCH')
        corrected['subject_geography']['region']='Lombardia'
        with self.assertRaisesRegex(ValueError,'subject_region_not_supported'):
            validate(corrected,r['payload'])

    def test_retry_is_bounded_and_never_overrides_disabled_repairs(self):
        from sales.agent6 import ai,decision
        p={'task':decision.TASK}
        for retries,expected in [(0,1),(1,2)]:
            c={'filters':{'commercial':{'ai':{**SOL_CONFIG,'max_retries':retries}}}}
            with patch.object(ai,'_call_once',return_value={'status':'invalid','error':'wrong_geography_fact','execution_id':1}) as run:
                result=ai.call(None,c,'AGENCIES','page:original',p,lambda:None)
                self.assertEqual(run.call_count,expected)
                if retries:self.assertIn('Geography indices',run.call_args.args[4]['repair']['instruction'])
            self.assertEqual(result['status'],'invalid')
