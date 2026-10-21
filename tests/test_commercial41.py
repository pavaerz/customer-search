"""Phase 4.1: saved campaign 25 evidence plus explicitly synthetic boundaries."""
import copy,gzip,json,unittest
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.admission import listing_url
from sales.commercial.discovery import assess,followup_allowed
from sales.commercial.request_profile import relationship,hosted_request
from sales.commercial.indexed_jobs import resolution,resolution_continuity,actor_resolution
from sales.commercial.identity import establish
from sales.commercial.geography import locate,resolve_location
from sales.commercial.attribution import geographic_conflicts
from sales.commercial.inspection import inspect
from sales.commercial.opportunity_view import build,novelty,request_key
from sales.commercial.ai import eligibility
from sales.commercial.commercial_gate import sufficient
from sales.commercial.strategies import plans
from sales.commercial.audit_policy import resource_role,finish

@lru_cache
def fixture():
    with gzip.open(Path(__file__).parent/'fixtures/commercial41/campaign25.json.gz','rt') as f:return json.load(f)
def body(oid):return copy.deepcopy(next(r['body'] for r in fixture()['commercial_revisions'] if r['opportunity_id']==oid))
def pages_for(host):return sorted([copy.deepcopy(p) for u,p in fixture()['pages'].items() if '://'+host+'/' in u or '://www.'+host+'/' in u],key=lambda p:len(p['url']))

class Saved41(CommercialTestCase):
    def original(self,oid):
        b=body(oid);p=fixture()['pages'][b['url']]
        with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=lambda url:copy.deepcopy(fixture()['pages'][url])):
            out=inspect(self.store,{'url':p['url'],'commercial_engine':b['engine'],'allowed_regions':fixture()['campaign']['filters']['regions']})
        out['result']['identity']=out['identity'];return out
    def test_01_pacer_workload_not_contract(self):
        r=self.original(772)['result'];self.assertEqual(r['classification'],'publisher_unresolved');self.assertEqual(r['relationship']['workload'],'FULL_TIME');self.assertEqual(r['relationship']['employment_relationship'],'EXTERNAL');self.assertEqual(build(r)['status'],'RESEARCH_REQUIRED')
    def test_02_pacer_never_publisher_contact(self):
        out=self.original(772);self.assertEqual(out['identity']['name'],'Pacer');self.assertIsNone(out['identity']['website']);self.assertEqual(out['identity']['contacts'],[])
        self.assertEqual(out['result']['actor_attribution']['publisher_identity'],'bebee.com');self.assertIsNone(out['identity']['name_fields']['legal_name'])
    def graphalia(self):return copy.deepcopy(next(d['body'] for d in fixture()['commercial_discovery'] if 'graphalia' in d['url']))
    def test_03_graphalia_admitted(self):self.assertEqual(assess(self.graphalia(),'AGENCIES')['decision'],'admit')
    def test_04_graphalia_not_technical_proof(self):
        r=assess(self.graphalia(),'AGENCIES');self.assertFalse(r['technical_request_verified']);self.assertEqual(r['admission_stage'],'COLLABORATION_SIGNAL')
    def test_05_bebee_root(self):self.assertTrue(listing_url('https://bebee.com/it/jobs/role'))
    def test_06_actual_three_followups(self):
        for t in fixture()['research_tasks']:
            if t['id'] in (3952,3953,3990):
                p=t['payload'];self.assertTrue(listing_url(p['url']));self.assertEqual(assess(p,t['strategy'])['reason'],'generic_job_listing');self.assertFalse(followup_allowed({'request_blocks':[1]},p))
    def test_07_remote_descendants(self):self.assertTrue(listing_url('https://it.bebee.com/jobs/remote/developer'))
    def test_08_individual_pacer_admitted(self):self.assertEqual(assess(body(772)['discovery'],'STARTUPS')['decision'],'admit')
    def test_09_revool_copies_not_official(self):
        for i in (778,780,787):self.assertEqual(resolution_continuity({'resolution_company':'Revool','resolution_role':'Web Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'},body(i)['discovery'])['status'],'UNRESOLVED')
    def test_10_startup_bakery_unknown(self):
        r=resolution({'url':'https://it.linkedin.com/jobs/view/developer-at-startup-bakery-123','title':'Freelance Backend Developer at Startup Bakery'});self.assertFalse(r['indexed_job']['identity_verified']);self.assertIn('sito ufficiale',r['query'])
    def test_11_cosmico_not_bebee(self):
        out=self.original(764);self.assertEqual(out['identity']['name'],'Cosmico Italia');self.assertEqual(out['identity']['contacts'],[]);self.assertIsNone(out['identity']['website']);self.assertEqual(build(out['result'])['status'],'RESEARCH_REQUIRED');self.assertTrue(actor_resolution(out['result']))
        self.assertEqual(out['identity']['name_fields']['selected_name'],'Cosmico Italia');self.assertNotIn('sector',out['identity']);self.assertIsNone(out['identity']['location'])
    def test_12_tecnofinestra_name(self):
        i=establish(pages_for('tecnofinestra.it'));self.assertEqual(i['name'],'Tecnofinestra');self.assertIn('provincia',i['identity_original']['name']);self.assertEqual(i['identity_status'],'verified')
    def test_13_tecnofinestra_offices(self):
        p=pages_for('tecnofinestra.it');g=locate(p,establish(p));self.assertEqual(g['regions'],['Emilia-Romagna']);self.assertTrue(any(l['location_role']=='OPERATING_OFFICE' for l in g['locations']))
    def test_14_peradotto_address(self):
        p=pages_for('peradottoimpianti.it');i=establish(p);self.assertEqual(i['identity_status'],'verified');self.assertEqual(locate(p,i)['regions'],['Valle d’Aosta']);self.assertEqual(resolve_location('11018 Villeneuve (AO)')['region'],'Valle d’Aosta')
    def test_15_cmc_name(self):
        i=establish(pages_for('carpenteriainfissi.it'));self.assertTrue(i['name'].startswith('CMC'));self.assertNotIn('Valle Antica',i['name']);self.assertEqual(i['legal_id'],'IT00824910574')
    def test_16_cmc_still_outside(self):
        p=pages_for('carpenteriainfissi.it');g=geographic_conflicts(locate(p,establish(p)),[],['Veneto','Emilia-Romagna']);self.assertFalse(g['eligible']);self.assertEqual(g['regions'],['Lazio'])
    def test_17_irrelevant_actual_linkedin(self):
        for i in (776,792,794,796):self.assertEqual(assess(body(i)['discovery'],'FREELANCE')['decision'],'exclude')
    def test_18_valid_linkedin_retained(self):self.assertEqual(assess(body(774)['discovery'],'FREELANCE')['decision'],'admit')
    def test_23_outbound_without_audit(self):self.assertEqual(build(body(779))['status'],'WORTH_REVIEWING')
    def test_24_outbound_partial_not_defect(self):
        v=build(body(769));self.assertEqual(v['status'],'WORTH_REVIEWING');self.assertIn('nessun difetto',str(v['missing']))
    def test_29_known_preserved(self):
        b=body(772);self.assertEqual(novelty(b,[{'id':1,'campaign_id':24,'body':b}])['status'],'ALREADY_SEEN')
    def test_30_syndication_not_independent_request(self):
        a=body(780);b=copy.deepcopy(a);b['url']='https://other.test/jobs/1';self.assertEqual(request_key(a),request_key(b))
    def test_real_budvar_skips_before_ai(self):self.assertEqual(eligibility(body(773)),(False,'target_geography_unresolved_or_excluded'))
    def test_redirect_listing_no_followup_or_identity_reads(self):
        p=page('Elenco aziende','Lavoro sviluppatore',url='https://bebee.com/it/jobs/role/web')
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p) as get:
            with self.assertRaisesRegex(ValueError,'generic_job_listing'):inspect(self.store,{'url':'https://bebee.com/it/jobs/individual-123','commercial_engine':'FREELANCE'})
            self.assertEqual(get.call_count,1)
    def test_original_fixture_unchanged(self):
        b=body(772);before=copy.deepcopy(b);build(b);self.assertEqual(b,before)

class Synthetic41(CommercialTestCase):
    def test_19_agency_partner(self):self.assertEqual(assess({'url':'https://agency.example/collabora','title':'Cerchiamo partner di sviluppo','content':'Collaboriamo con sviluppatori frontend esterni'},'AGENCIES')['decision'],'admit')
    def test_20_agency_seller(self):self.assertEqual(assess({'url':'https://agency.example/servizi','title':'Sviluppo web','content':'Offriamo servizi WordPress e realizziamo siti per clienti.'},'AGENCIES')['decision'],'exclude')
    def test_21_unpaid_cofounder_not_customer(self):
        r=self.inspect(page('Startup: cerchiamo cofounder tecnico per sviluppo piattaforma web, equity senza compenso.'),'STARTUPS')['result'];self.assertNotEqual(r['state'],'VERIFIED');self.assertNotEqual(build(r)['status'],'READY_TO_CONTACT')
    def test_22_external_startup_request(self):self.assertEqual(assess({'url':'https://startup.example/jobs','title':'Startup: cerchiamo sviluppatore WordPress freelance per piattaforma, compenso a progetto'},'STARTUPS')['decision'],'admit')
    def test_25_form_resource_scope(self):self.assertEqual(resource_role('https://www.google.com/recaptcha/api.js','script','https://example.test/'),'FORM')
    def test_26_blank_is_unvalidated(self):
        r=finish({'completed':False,'pages':[{'url':'https://a.test','viewport':390,'complete':False,'measurements':{'visible_content':False,'overflow':200}}],'findings':[{'code':'horizontal_overflow'}]});self.assertEqual(r['findings'],[]);self.assertEqual(r['independent_measurements'],[])
    def test_27_insufficient_ai_gate(self):self.assertFalse(sufficient('FREELANCE',{},[])['allowed'])
    def test_28_shadow_does_not_promote(self):
        b=body(780);b['ai_assessment']={'status':'completed','output':{'state':'VERIFIED'}};self.assertEqual(build(b)['status'],'RESEARCH_REQUIRED')
    def test_contract_conflict_retains_both(self):
        r=relationship('Collaborazione a progetto con Partita IVA. Contratto a tempo indeterminato. Tempo pieno.');self.assertEqual(r['employment_relationship'],'AMBIGUOUS');self.assertTrue(r['evidence']['external']);self.assertTrue(r['evidence']['employee'])
    def test_workload_alone_unknown_relationship(self):self.assertEqual(relationship('Tempo pieno')['employment_relationship'],'UNKNOWN')
    def test_rejected_employee_still_rejected(self):self.assertEqual(relationship('Contratto a tempo indeterminato')['employment_relationship'],'EMPLOYEE')
    def test_official_candidate_admitted_without_invented_identity(self):
        p={'resolution_company':'Revool','resolution_role':'Web Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'}
        item={'url':'https://revool.example/','title':'Revool - agenzia digitale','content':'Sito ufficiale e contatti'}
        r=resolution_continuity(p,item);self.assertEqual(r['status'],'SUPPORTED');self.assertFalse(r['identity_verified']);self.assertEqual(assess({**p,**item},'FREELANCE')['decision'],'admit')
    def test_wrong_company_not_resolved(self):self.assertEqual(resolution_continuity({'resolution_company':'Revool','resolution_role':'Web Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'},{'url':'https://other.test/','title':'Other Srl web developer'})['status'],'UNRESOLVED')
    def test_service_area_not_office(self):
        p=page('Serviamo clienti in tutta Lombardia.',extra='<section class="customers">Cliente con sede a Torino</section>');g=locate([p],establish([p]));self.assertEqual(g['regions'],['Veneto'])
    def test_unknown_location_not_inferred_from_query(self):self.assertIsNone(resolve_location('Immaginaria Località')['region'])
    def test_agency_families_diverse(self):
        p=plans('AGENCIES',['Veneto','Toscana']);self.assertGreaterEqual(len({i['family'] for i in p}),7);self.assertTrue(any(i['exploration'] for i in p));self.assertEqual({i['region'] for i in p},{'Veneto','Toscana'})
    def test_outbound_sector_diversity(self):
        p=plans('WEBSITE_REBUILD',['Veneto']);self.assertGreaterEqual(len({i['sector_group'] for i in p}),8);self.assertEqual(len({i['sector_group'] for i in p[:3]}),3)
    def test_partial_keeps_independent_measurement(self):
        r=finish({'completed':False,'pages':[{'url':'https://a.test','viewport':390,'complete':True,'measurements':{'visible_content':True,'overflow':150}},{'url':'https://a.test','viewport':1366,'complete':False,'measurements':{}}],'findings':[]});self.assertEqual(len(r['independent_measurements']),1);self.assertEqual(r['observations'][0]['status'],'CONFIRMED');self.assertFalse(r['completed'])
    def test_unknown_external_script_remains_critical(self):self.assertEqual(resource_role('https://cdn.other.test/app.js','script','https://a.test/'),'CRITICAL')
    def test_consent_not_assumed_optional(self):self.assertEqual(resource_role('https://cdn-cookieyes.com/client_data/a/script.js','script','https://a.test/'),'CONSENT')
    def test_encoded_listing_path(self):self.assertTrue(listing_url('https://bebee.com/it/jobs/role%2Fweb'))
    def test_individual_remote_word_allowed(self):self.assertFalse(listing_url('https://bebee.com/it/jobs/remote-developer-123'))
    def test_foreign_address_not_sardinia_from_su(self):
        self.assertNotEqual(resolve_location('Parigi - SU APPUNTAMENTO')['region'],'Sardegna')
    def test_company_mentioned_in_client_testimonial_not_domain(self):
        p={'resolution_company':'PACER','resolution_role':'Full Stack Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'}
        for item in [d['body'] for d in fixture()['commercial_discovery'] if d['id'] in (1066,1071)]:
            self.assertEqual(resolution_continuity(p,item)['status'],'UNRESOLVED')
    def test_contradictory_original_request_kept_not_ready(self):
        r=self.inspect(page('Cerchiamo sviluppatore WordPress freelance con partita IVA e contratto a tempo indeterminato.'),'FREELANCE')
        b={**r['result'],'identity':r['identity']};self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertEqual(b['relationship']['employment_relationship'],'AMBIGUOUS')
        v=build(b);self.assertIn(v['status'],('WORTH_REVIEWING','RESEARCH_REQUIRED'));self.assertIn('Contratto discordante',str(v['missing']))
    def test_contract_conflict_does_not_hide_other_conflicts(self):
        b=body(772);b.update(state='NEEDS_REVIEW',classification='publisher_unresolved',relationship=relationship('Freelance. Contratto a tempo indeterminato.'))
        b['commercial_intent']={**b.get('commercial_intent',{}),'contradictions':[{'code':'conflicting_contracts'},{'code':'conflicting_identity'}]}
        self.assertEqual(build(b)['status'],'NOT_ACTIONABLE')
    def test_legal_suffix_not_required_in_official_site_title(self):
        r=resolution_continuity({'resolution_company':'Startup Bakery srl','resolution_role':'Backend Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'},{'url':'https://startupbakery.example','title':'Startup Bakery - sito ufficiale'})
        self.assertEqual(r['status'],'SUPPORTED');self.assertFalse(r['identity_verified'])
    def test_tourism_query_not_forced_to_manufacturing(self):
        p=next(p for p in plans('WEBSITE_REBUILD',['Veneto']) if p['sector_group']=='tourism');self.assertIn('prenotazioni',p['query']);self.assertNotIn('produzione',p['query'])
    def test_resolved_supplier_homepage_can_follow_own_careers_only(self):
        r={'engine':'FREELANCE','classification':'no_request','commercial_intent':{'commercial_role':'SELLER'},'identity':{'identity_status':'verified','website':'https://alfa.example/','resolution':{'official_domain_verified':True}}}
        self.assertTrue(followup_allowed(r,{'url':'https://alfa.example/lavora-con-noi','anchor':'Lavora con noi'}))
        for url in ('https://other.example/lavora-con-noi','https://alfa.example/servizi','https://alfa.example/jobs.pdf','https://bebee.com/jobs/role/web'):
            self.assertFalse(followup_allowed(r,{'url':url,'anchor':'Link'}))
        r['identity']['resolution']['official_domain_verified']=False
        self.assertFalse(followup_allowed(r,{'url':'https://alfa.example/lavora-con-noi','anchor':'Lavora con noi'}))
    def test_fixed_term_is_employment_not_workload(self):
        r=relationship('Contratto a tempo determinato. Part-time.');self.assertEqual(r['contract_type'],'EMPLOYMENT');self.assertEqual(r['workload'],'PART_TIME')
    def test_indexed_full_time_onsite_not_contract_proof(self):
        from sales.commercial.indexed_jobs import parse_indexed_job
        r=parse_indexed_job({'url':'https://example.test/job','title':'Web Developer full-time on-site at Alfa'});self.assertIsNone(r['contract_hint']);self.assertIsNone(r['commercial_compatibility'])
