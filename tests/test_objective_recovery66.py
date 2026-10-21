"""Saved Campaign 59 sources/answers, offline only; no fabricated live leads."""
import copy
import gzip
import json
from pathlib import Path
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import test_ai_first as h
from scripts.run_objective_validation_sol import SOL_CONFIG
from sales.agent6 import evidence, decision
from sales.agent6.research_dispatch import assess
from sales.commercial.geography import resolve_location
from sales.commercial.inspection import document
from sales.db import digest

ROOT=Path(__file__).parent/'fixtures/ai_first/recovery66'
SAVED={r['record_id']:r for r in json.loads(gzip.decompress((ROOT/'originals.json.gz').read_bytes()))}


def replay(rid, *, saved_answer=False, depth=0, repeat=False):
    base=h.IntegratedPath();base.setUp()
    try:
        base.c['filters']['commercial']['ai'].update(SOL_CONFIG)
        base.c['filters']['commercial']['ai']['provider']='MOCK'
        base.c['filters']['regions']=['Veneto','Lombardia','Friuli-Venezia Giulia']
        row=SAVED[rid];page=copy.deepcopy(row['page'])
        base.w.enqueue('candidate',row['flow'],{'url':page['url'],'original_page':page,'depth':depth},'recovery66')
        with base.store.connect() as db:
            t=db.execute("SELECT * FROM research_tasks WHERE fingerprint='recovery66'").fetchone()
            task={**dict(t),'payload':json.loads(t['payload'])}
        seen=[]
        def model(flow,key,payload,check,**kwargs):
            seen.append(copy.deepcopy(payload))
            if not saved_answer:return {'status':'invalid','error':'offline_capture_no_model'}
            receipt=row['execution']['body']
            output=(json.loads((ROOT/'rent-response.json').read_text()) if rid==1932 else receipt['output'])
            return {'status':'completed','output':copy.deepcopy(output),'evidence':copy.deepcopy(receipt['evidence'])}
        def infer(payload,config,check):
            seen.append(copy.deepcopy(payload))
            return {'output':{},'usage':{}}
        with (patch.object(base.w,'model',side_effect=model) if saved_answer else nullcontext()),patch(
            'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Saved originals only')),patch(
            'sales.agent6.ai.infer',side_effect=infer):
            base.w.execute(task,lambda:None)
            if repeat:base.w.execute(task,lambda:None)
        with base.store.connect() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            tasks=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute(
                "SELECT * FROM research_tasks WHERE fingerprint!='recovery66'")]
        return seen,records,tasks
    finally:base.tearDown()


class ActualAgencyFollowups(unittest.TestCase):
    def test_saved_requests_queue_only_the_offered_invitation_without_promotion(self):
        for rid in (1909,1912):
            with self.subTest(record=rid):
                seen,records,tasks=replay(rid,saved_answer=True,repeat=True)
                self.assertEqual(len(tasks),1)
                task=tasks[0]
                self.assertEqual(task['kind'],'candidate')
                action=SAVED[rid]['record']['research_action']
                offered=next(l for l in seen[0]['links'] if l['id']==action['link_id'])
                self.assertEqual(task['payload']['url'],offered['url'])
                self.assertEqual(task['payload']['research_question'],action['question'])
                self.assertEqual(task['payload']['depth'],1)
                self.assertEqual(records[0]['decision'],'NEEDS_RESEARCH')
                self.assertTrue(records[0]['research_dispatch']['allowed'])
                self.assertFalse(decision.projection(records[0])['READY_FOR_OUTREACH'])

    def test_same_existing_depth_limit_still_stops_actual_invitation(self):
        _,records,tasks=replay(1909,saved_answer=True,depth=100)
        self.assertEqual(tasks,[])
        self.assertEqual(records[0]['decision'],'NEEDS_RESEARCH')

    def test_saved_full_portfolio_invitation_reaches_model(self):
        seen,_,_=replay(1909)
        text='\n'.join(e['text'] for e in seen[0]['evidence'])
        self.assertIn('Siamo sempre alla ricerca di talenti da coinvolgere nei nostri progetti.',text)
        self.assertIn('Inviaci il tuo portfolio',text)
        self.assertIn('Fluido Factory',text)
        self.assertIn('Elementor',text)

    def test_generic_supplier_and_unoffered_or_irrelevant_routes_stay_blocked(self):
        body=copy.deepcopy(SAVED[1909]['record'])
        links=body['evidence_packet']['links']
        self.assertTrue(assess(body,links)['allowed'])
        variants=[]
        for key,value in [('type','SEARCH_SUBJECT'),('type','INSPECT_BROWSER'),
                          ('link_id','invented'),('question','Quali sono i prezzi dei servizi?')]:
            b=copy.deepcopy(body);b['research_action'][key]=value;variants.append(b)
        for key,value in [('entity_name',''),('decision','NOT_INTERESTING'),('facts',[])]:
            b=copy.deepcopy(body);b[key]=value;variants.append(b)
        for intent in ('TRAINING','COMPLETED_PROJECT'):
            b=copy.deepcopy(body);b['commercial_assessment']['intent']=intent;variants.append(b)
        for b in variants:self.assertFalse(assess(b,links)['allowed'])
        for label in ('Richiedi un preventivo','I nostri partner','Portfolio','Contatti'):
            self.assertFalse(assess(body,[{'id':body['research_action']['link_id'],'label':label}])['allowed'])
        self.assertFalse(assess(body)['allowed'])


class OriginalJobDescription(unittest.TestCase):
    def proofs(self):
        page=SAVED[1944]['page'];pk=evidence.packet(page,document(page));unit=pk['units'][0]
        return unit,evidence.passages(pk,unit,3000)

    def test_real_description_and_conflicting_metadata_survive_same_byte_limit(self):
        unit,proofs=self.proofs();text='\n'.join(e['text'] for e in proofs)
        self.assertIn('Based in a country where we currently employ or engage remote engineers',text)
        self.assertIn('Italy, Spain, or Portugal',text)
        self.assertIn('right to work there',text)
        self.assertIn('applicantLocationRequirements',text)
        self.assertIn('Germany',text);self.assertIn('Poland',text)
        self.assertIn('FULL_TIME',text);self.assertIn('hiringOrganization',text)
        self.assertLessEqual(sum(len(e['text'].encode()) for e in proofs),3000)
        for e in proofs:
            self.assertEqual(e['text'],unit['text'][e['offset']:e['offset']+len(e['text'])])
            self.assertEqual(e['document_id'],unit['document_id'])
            self.assertEqual(e['unit_id'],unit['id'])
            self.assertEqual(e['hash'],digest(e['text']))

    def test_real_worker_preserves_description_and_metadata_within_input_cap(self):
        from sales.commercial.token_count import estimate
        seen,records,tasks=replay(1944)
        text='\n'.join(e['text'] for e in seen[0]['evidence'])
        self.assertIn('Based in a country',text)
        self.assertIn('applicantLocationRequirements',text)
        self.assertLessEqual(estimate(seen[0],SOL_CONFIG)['tokens'],SOL_CONFIG['max_input_tokens'])
        from sales.agent6.grounding import provider_payload
        wire=json.dumps(provider_payload(seen[0]),ensure_ascii=False)
        self.assertIn('Based in a country',wire)
        self.assertIn('applicantLocationRequirements',wire)
        self.assertFalse(tasks)
        self.assertFalse(any(r.get('decision')=='INTERESTING' for r in records))

    def test_html_paragraph_offsets_and_units_remain_isolated(self):
        job={'@type':'JobPosting','title':'Frontend developer',
             'description':'<p>Generic intro.</p>'*80+'<p>No salary. Equity only.</p>'+
                 '<ul><li>Applicants must live in Italy.</li></ul>',
             'hiringOrganization':{'name':'First Company'}}
        other={'@type':'JobPosting','description':'Paid freelance project in Germany.',
               'hiringOrganization':{'name':'Other Company'}}
        page={**SAVED[1944]['page'],'html':'<script type="application/ld+json">'+json.dumps([job,other])+'</script>'}
        pk=evidence.packet(page,document(page));unit=pk['units'][0]
        proofs=evidence.passages(pk,unit,1800);text='\n'.join(e['text'] for e in proofs)
        self.assertIn('No salary. Equity only.',text)
        self.assertIn('Applicants must live in Italy.',text)
        self.assertIn('First Company',text)
        self.assertNotIn('Other Company',text)
        self.assertNotIn('Paid freelance',text)
        for e in proofs:self.assertEqual(e['text'],unit['text'][e['offset']:e['offset']+len(e['text'])])


class AddressComponents(unittest.TestCase):
    def test_actual_address_resolves_and_saved_answer_validates_unchanged(self):
        quote='Rent s.r.l. - Via Pontebbana, 42 - 33080 Fiume Veneto (PN) - C.F. e P.IVA 01300700935'
        found=resolve_location(quote)
        self.assertEqual(found['region'],'Friuli-Venezia Giulia')
        self.assertEqual(found['city'],'Fiume Veneto')
        _,records,tasks=replay(1932,saved_answer=True)
        self.assertEqual(records[0]['decision'],'NOT_INTERESTING')
        self.assertEqual(records[0]['subject_geography']['status'],'IN_TARGET')
        self.assertEqual(tasks,[])

    def test_other_real_locations_and_province_conflicts_are_not_overridden(self):
        for text in ('33080 Fiume Veneto (PN); sede a Milano',
                     '33080 Fiume Veneto (PN); regione Veneto',
                     '33080 Fiume Veneto (PD)',
                     '33080 Fiume Veneto (PN); 20100 Milano (MI)'):
            result=resolve_location(text)
            self.assertEqual(result['basis'],'CONFLICT',text)
            self.assertIsNone(result['region'],text)
        self.assertEqual(resolve_location('Serviamo clienti in 33080 Fiume Veneto (PN)')['basis'],'SERVICE_AREA')

    def test_street_named_after_region_does_not_override_exact_municipality(self):
        result=resolve_location('Via Piemonte 12 - 33080 Fiume Veneto (PN)')
        self.assertEqual(result['region'],'Friuli-Venezia Giulia')
        result=resolve_location('31029 Vittorio Veneto (TV)')
        self.assertEqual(result['region'],'Veneto')


class ExplorationDirections(unittest.TestCase):
    def check(self,query,flow):
        from sales.agent6.discovery_intent import assess as intent
        from sales.agent6.commercial_policy import assess_query
        proposal={**h.query(query),'hypothesis':'Verificare una possibile collaborazione o lacuna digitale; non è una richiesta provata.'}
        return intent(proposal,flow,['Veneto']),assess_query(proposal,flow,['Veneto'])

    def test_campaign59_rejected_queries_can_explore_without_claiming_demand(self):
        for query,flow in [('"posizioni aperte" sviluppatore freelance','AGENCIES'),
                           ('Veneto hotel nuova gestione riapertura 2026','NEWS')]:
            for result in self.check(query,flow):self.assertTrue(result['allowed'],result)
        self.assertEqual(self.check('Veneto hotel nuova gestione riapertura 2026','NEWS')[1]['intent'],
                         'company_event_to_verify')

    def test_generic_jobs_statistics_and_unconstrained_or_remain_blocked(self):
        for query,flow in [('posizioni aperte sviluppatore','AGENCIES'),
                           ('open positions frontend employee only','AGENCIES'),
                           ('posizioni aperte idraulico freelance','AGENCIES'),
                           ('Veneto hotel','NEWS'),('sondaggio nuova gestione hotel Veneto','NEWS'),
                           ('(posizioni aperte sviluppatore freelance OR agenzie web)','AGENCIES')]:
            self.assertFalse(all(r['allowed'] for r in self.check(query,flow)),query)


if __name__=='__main__':unittest.main()
