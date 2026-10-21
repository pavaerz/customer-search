"""3B.5: saved HTML replay plus synthetic unit/integration tests. No external I/O."""
import copy,json,tempfile,unittest,os,time
from pathlib import Path
from unittest.mock import patch
from scripts.replay_commercial3b5 import load,replay,pages_for
from sales.commercial import target_fit
from sales.commercial.geography import region,resolve_location
from sales.commercial.context import extract
from sales.commercial.identity import establish
from sales.commercial.entity_scope import profile
from sales.commercial.discovery import assess
from sales.commercial.presentation import history,lead_type
from sales.commercial.ai_schema import validate_output,unknown_output,evidence_bundle
from sales.commercial.catalog import BUDGETS,PILOT

class Historical35(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.x=load();cls.replayed={r['revision']:r for r in replay()['replay']}
    def test_parklab_region(self):self.assertEqual(self.replayed[876]['geography']['regions'],['Lombardia'])
    def test_parklab_partner_not_automatic_project(self):
        r=self.replayed[876];self.assertEqual(r['lead_profile']['type'],'PARTNERSHIP_PROSPECT');self.assertEqual(r['replay_decision'],'NEEDS_REVIEW');self.assertIsNone(r['compensation']['amount'])
    def test_parklab_technical_recipient_selected(self):
        from sales.commercial.inspection import document
        from sales.commercial.evidence import select,trim_to_payload
        from sales.commercial.ai_schema import SYSTEM
        original=next(r for r in self.x['commercial_revisions'] if r['id']==876)
        b=self.replayed[876]['replayed_body'];docs=[document(p) for p in pages_for(self.x,original)]
        evidence,metrics=select('443',docs,result=b)
        payload={'candidate_id':'443','evidence':evidence};trim_to_payload(payload,SYSTEM,8192,metrics)
        self.assertTrue(any('Sviluppatori web e team tech' in e['text'] for e in evidence))
    def test_apice_requester_and_no_false_conflict(self):
        r=self.replayed[875];self.assertEqual(r['identity']['name'],'Apiceweb');self.assertFalse(r['commercial_intent']['contradictions']);self.assertEqual(r['commercial_intent']['requester'],'publisher');self.assertEqual(r['replay_decision'],'NEEDS_REVIEW')
    def test_apice_both_technical_roles_and_external(self):
        blocks=extract(self.x['pages']['https://www.apiceweb.it/lavora-con-noi'])
        for skill in ['Wordpress','PrestaShop']:
            matches=[b for b in blocks if skill.lower() in str(b['role']).lower()]
            self.assertTrue(matches,skill);self.assertTrue(any(b['commercial_intent']['relationship']=='external' for b in matches),skill)
    def test_apice_currentness_geo_budget_unknown(self):
        r=self.replayed[875];self.assertEqual(r['verification']['currentness'],'unknown');self.assertEqual(r['geography']['regions'],['Veneto']);self.assertIsNone(r['compensation']['amount'])
    def test_amts_no_borrowed_entities(self):
        r=self.replayed[891];self.assertEqual(r['identity']['attribution']['role'],'ACTOR_UNRESOLVED');self.assertEqual(r['identity']['locations'],[]);self.assertIsNone(r['identity']['legal_id']);self.assertIsNone(r['target_fit']);self.assertEqual(r['lead_profile']['type'],'DATA_QUALITY_REVIEW')
    def test_vanzo_page_not_directory(self):
        r=self.replayed[878];self.assertNotEqual(r['target_fit']['source_role'],'directory');self.assertFalse(r['target_fit']['audit_allowed'])
    def test_olivi_recovered_owner_vat(self):
        r=self.replayed[879];self.assertEqual(r['identity']['legal_id'],'IT01658140353');self.assertEqual(r['identity']['identity_status'],'verified');self.assertEqual(r['replay_decision'],'UNVERIFIABLE')
    def test_pichler_real_size_remains_low_priority(self):
        r=self.replayed[904];self.assertEqual(r['target_fit']['size']['employees'],250);self.assertEqual(r['lead_profile']['type'],'LOW_PRIORITY_TARGET')
    def test_browser_historical_not_repaired_by_replay(self):
        for rid in [884,897]:
            b=self.replayed[rid]['replayed_body']['browser'];self.assertFalse(b['completed']);self.assertEqual(b['findings'],[])
    def test_boutique_history_keeps_executed_audit(self):
        rows=[r for r in self.x['commercial_revisions'] if r['opportunity_id']==735];h=history(rows)
        self.assertEqual(h['latest_decision']['revision_id'],899);self.assertEqual(h['latest_audit']['revision_id'],897);self.assertEqual(h['best_available_evidence']['revision_id'],897)
    def test_bad_agency_query_filtered(self):
        rows=[d for d in self.x['commercial_discovery'] if d['body'].get('origin',{}).get('task_id')==3821 and d['body']['origin'].get('acquisition')=='search']
        before=sum(d['decision']=='admit' for d in rows);after=sum(assess(d['body'],d['engine'],d['body'].get('origin'))['decision']=='admit' for d in rows)
        self.assertLess(after,before);self.assertEqual(before,8)
    def test_catalog_and_bibliography_before_fetch(self):
        for word in ['amtstorino','trenidicarta']:
            d=next(d for d in self.x['commercial_discovery'] if word in d['url']);self.assertEqual(assess(d['body'],d['engine'])['decision'],'exclude')
    def test_all_originals_present(self):self.assertEqual(self.x['missing_originals'],[]);self.assertEqual(len(self.x['pages']),66)

class Synthetic35(unittest.TestCase):
    def test_thousands(self):
        for text,n in [('1.300 dipendenti',1300),('1,300 employees',1300),('250+ dipendenti',250),('circa 300 addetti',300),('250–300 dipendenti',250)]:
            self.assertEqual(target_fit.counterevidence(text)[0]['employees'],n)
    def test_invalid_numbers_unknown(self):
        for s in ['000 dipendenti','1.30 dipendenti','0000 employees','300–200 dipendenti','300 sedie','1,3 milioni']:
            self.assertEqual(target_fit.counterevidence(s),[],s)
    def test_named_other_company_size_not_borrowed(self):
        from test_commercial_engines import page
        from sales.commercial.attribution import identity
        p=page('Produciamo serramenti su misura.');p['html']+='<p>Beta ha 1300 dipendenti.</p>'
        self.assertEqual(target_fit.evaluate(identity([p]),[p])['size']['status'],'UNKNOWN')
    def test_geography_components(self):
        for s,r in [('Milano','Lombardia'),('MI','Lombardia'),('20131','Lombardia'),('via Ampère 61/A, 20131, Milano, IT','Lombardia'),('Padova','Veneto'),('PD','Veneto'),('35121 Padova (PD)','Veneto')]:self.assertEqual(region(s),r,s)
    def test_geography_unknown_and_conflicting(self):
        for s in ['Via Milano 10','Serviamo clienti a Milano','99999','20131 Milano (PD)','Lombardia Group']:self.assertIsNone(region(s),s)
    def test_candidate_not_new_requester(self):
        from sales.commercial.intent import classify_block
        for q in ['Sei un professionista freelance alla ricerca di nuove opportunità?','Sei uno sviluppatore WordPress?','Ti occupi di sviluppo frontend?']:
            r=classify_block('Cerchiamo sviluppatore WordPress freelance. '+q);self.assertFalse(r['contradictions'])
    def test_real_multiple_named_subjects_still_reviewed(self):
        from sales.commercial.intent import classify_block
        r=classify_block('Alfa ricerca sviluppatori WordPress freelance. Beta ricerca sviluppatori frontend freelance.')
        self.assertTrue(r['contradictions']);self.assertEqual(r['actor_relation'],'MULTIPLE_VALID_ACTORS')
    def test_official_reseller_page_scope(self):
        self.assertEqual(target_fit.source_role('https://produttore.example/rivenditori/','Rivenditori','Produciamo serramenti per rivenditori'),'company_candidate')
        self.assertEqual(target_fit.source_role('https://directory.example/','Elenco aziende','Directory di imprese'),'directory')
    def test_startup_alternatives_no_budget_increase(self):
        from sales.commercial.catalog import plan
        ps=plan('STARTUPS');self.assertTrue(any(p['family']=='startup_external' for p in ps));self.assertTrue(any('piattaforma MVP' in p['query'] for p in ps));self.assertEqual(PILOT['max_queries_per_engine'],3);self.assertEqual(BUDGETS['browser_max_resources'],60);self.assertEqual(BUDGETS['browser_total_seconds'],120)
    def test_pdf_still_first(self):self.assertEqual(assess({'url':'https://alfa.example/a.pdf'},'AGENCIES')['reason'],'excluded_pdf')
    def test_private_diagnostics_bounded_and_secret_free(self):
        from sales.commercial.private_diagnostics import retain
        from sales.db import Store
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.db');retain(store,1,{'code':'ERROR','fields':['actor'],'contested_value':'sk-proj-secret','Authorization':'Bearer secret','evidence_ids':['secret','EVIDENCE_'+'a'*20]})
            f=Path(d)/'ai-validation-private/validation-1.json';text=f.read_text();self.assertNotIn('secret',text);self.assertEqual(f.stat().st_mode&0o777,0o600)
            os.utime(f,(time.time()-90000,)*2);retain(store,2,{'code':'ERROR'},retention_hours=1);self.assertFalse(f.exists())
    def test_zero_retention_disables_new_files(self):
        from sales.commercial.private_diagnostics import retain
        from sales.db import Store
        with tempfile.TemporaryDirectory() as d:
            retain(Store(Path(d)/'test.db'),1,{},0);self.assertFalse((Path(d)/'ai-validation-private').exists())

class AIValidation35(unittest.TestCase):
    def fixture(self):
        docs=[{'id':'d','url':'https://alfa.example/','text':'Cerchiamo sviluppatori WordPress freelance.\nAlfa Srl\nCandidature aperte.'}]
        r={'company':'Alfa Srl','identity':{'name':'Alfa Srl','identity_status':'verified'},'verification':{'checks':{'temporal_basis':True}},'url':'https://alfa.example/'}
        e=evidence_bundle('7',docs,result=r);o=unknown_output({'candidate_id':'7'});ref=lambda word:next({'id':v['id'],'quote':v['text']} for v in e if word in v['text'])
        o.update(actor='Alfa',commercial_intent='FREELANCE_OPPORTUNITY',direction='BUYER',requested_service='WordPress',technical_relevance=True,relationship_type='UNKNOWN',supporting_evidence=[ref('Cerchiamo')],identity_evidence=[ref('Alfa')])
        return e,o,r
    def test_supported_owner_alias(self):
        e,o,r=self.fixture();self.assertEqual(validate_output(o,'7',e,r)['actor'],'Alfa')
    def test_nonexistent_and_wrong_actor(self):
        for value in ['Beta','invented-alias']:
            e,o,r=self.fixture();o['actor']=value
            with self.assertRaises(ValueError):validate_output(o,'7',e,r)
    def test_invented_service_rejected(self):
        e,o,r=self.fixture();o['requested_service']='applicazione sanitaria con blockchain'
        with self.assertRaises(ValueError):validate_output(o,'7',e,r)
    def test_unsupported_technical(self):
        e,o,r=self.fixture();o=unknown_output({'candidate_id':'7'});o['technical_relevance']=True
        with self.assertRaisesRegex(ValueError,'unsupported_technical'):validate_output(o,'7',e,r)
    def test_temporal_role_not_owner_footer(self):
        e,o,r=self.fixture();o['temporal_evidence']=o['identity_evidence']
        with self.assertRaisesRegex(ValueError,'temporal_role'):validate_output(o,'7',e,r)
    def test_malformed_json_diagnosed(self):
        from sales.commercial.ai_diagnostics import diagnose
        e,o,r=self.fixture();d=diagnose('{invalid','7',e,r);self.assertEqual(d['diagnosis'],'SCHEMA_ERROR');self.assertEqual(len(d['response_hash']),64)
    def test_missing_evidence(self):
        e,o,r=self.fixture()
        with self.assertRaises(ValueError):validate_output(o,'7',[],r)
