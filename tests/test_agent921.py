"""9.2.1 alignment. Synthetic boundaries and frozen originals; no live services."""
import copy
import unittest
from unittest.mock import patch
from sales.agent6 import qualification, commercial_view, alignment, website_review, schema, commercial_policy
from sales.agent6.website_audit import audit
from sales.agent6.worklist import listing
from sales.agent6 import memory
from test_agent6 import source, output, identity, evaluated, DATE
import test_agent6_campaign32 as support
from test_agent6_campaign32 import query
from scripts.replay_agent92 import load, replay


def agency(role='collaboratori freelance', extra='', contacts=True):
    request='Cerchiamo '+role+'. Remote from Italy.'
    s=source('Alfa Srl\nPosted 2 days ago\nSiamo una web agency.\n'+request+'\n'+extra)
    fields={'entity':'Alfa Srl','request':request,'contract':request,'geography':'Remote from Italy.'}
    p,o=output(s,'AGENCY_PARTNERSHIP',fields)
    o['analyses'][0]['missing']=['technical','budget','contact','scope','feasibility']
    ident=identity()
    if not contacts:ident['contacts']=[]
    return qualification.evaluate(s,o['analyses'][0],p['evidence'],'AGENCIES',ident)


def startup(terms):
    request='We are looking for a technical cofounder and frontend developer. Remote from Italy.'
    s=source('Alfa Srl\nPosted 2 days ago\nWe are a startup.\n'+request+'\n'+terms)
    p,o=output(s,'BUYER_DEMAND',{'entity':'Alfa Srl','request':request,'technical':'frontend developer',
        'contract':terms,'geography':'Remote from Italy.'})
    return qualification.evaluate(s,o['analyses'][0],p['evidence'],'STARTUPS',identity())


def content_pages():
    # Realistically bad *content structure*, no injected CSS/HTTP defects.
    html='<title>Alfa</title><h1>Alfa</h1>'+''.join(
        '<p>I servizi di Alfa includono lavorazioni industriali: '+('dettagli della produzione e dei prodotti ' * 15)+'</p>'
        for _ in range(4))+''.join('<a href="/servizio'+str(n)+'">Scopri di più</a>' for n in range(5))
    return [{'url':'https://alfa.example/'+p,'html':html,'status':200,'checked_at':DATE} for p in ('','prodotti')]


class Alignment(unittest.TestCase):
    def test_public_generic_email_and_provenance(self):
        b=evaluated()
        for mailbox in ('info','contatti','commerciale','hello','office'):
            b['contacts']=[{'type':'email','value':mailbox+'@alfa.example','url':b['url']}]
            a=alignment.dimensions(b)
            self.assertTrue(a['READY_FOR_OUTREACH'])
            self.assertEqual(a['public_channels'][0]['url'],b['url'])

    def test_missing_and_unattributed_email_never_invented(self):
        b=evaluated()
        for channels in ([],[{'type':'email','value':'info@alfa.example'}],
                         [{'type':'email','value':'hello@other.example','url':'https://other.example'}]):
            b['contacts']=channels
            a=alignment.dimensions(b)
            self.assertTrue(a['OPPORTUNITY_QUALIFIED'])
            self.assertFalse(a['CONTACT_AVAILABLE']);self.assertFalse(a['READY_FOR_OUTREACH'])
            self.assertEqual(a['public_channels'],[])

    def test_request_qualified_without_contact(self):
        s=source();p,o=output(s);ident=identity();ident['contacts']=[]
        o['analyses'][0]['missing']=['contact']
        b=qualification.evaluate(s,o['analyses'][0],p['evidence'],'SOCIAL',ident)
        self.assertEqual(b['state'],'VERIFIED')
        self.assertFalse(b['commercial_alignment']['CONTACT_AVAILABLE'])
        self.assertTrue(b['completion_queue']['promising'])

    def test_agency_no_stack_or_generic_invitation(self):
        b=agency()
        self.assertEqual(b['state'],'POTENTIAL',b)
        self.assertEqual(b['affinity']['value'],'UNKNOWN_AFFINITY')
        self.assertNotIn('technical',b['missing'])
        self.assertEqual(b['completion_queue']['active_assignment'],'UNKNOWN')
        generic=agency('collaboratori')
        self.assertEqual(generic['state'],'POTENTIAL',generic['reason'])
        self.assertFalse(generic['external'])
        self.assertIn('contract_terms',generic['optional_unknowns'])

    def test_different_stack_is_not_an_exclusion(self):
        b=agency('collaboratori freelance per sviluppo software in Rust e Go')
        self.assertEqual(b['state'],'POTENTIAL',b['reason'])
        self.assertEqual(b['affinity']['value'],'POSSIBLE_AFFINITY')

    def test_matching_skills_rank_without_whitelist(self):
        b=agency('collaboratori freelance React e Next.js')
        self.assertEqual(b['affinity']['value'],'HIGH_AFFINITY')
        self.assertEqual(b['state'],'POTENTIAL')

    def test_php_and_jquery_are_supported_requested_skills(self):
        from sales.commercial.demand import technical_fit
        for skill in ('PHP','jQuery','SCSS','Next.js'):
            self.assertEqual(technical_fit('', 'We need a freelance developer using '+skill)['status'],'COMPATIBLE')
            s=source('Alfa Srl\nPosted 2 days ago\nWe are looking for a freelance '+skill+' developer. Remote from Italy.')
            p,o=output(s,fields={'entity':'Alfa Srl','request':'We are looking for a freelance '+skill+' developer. Remote from Italy.',
                                'technical':skill,'contract':'freelance','geography':'Remote from Italy.'})
            validated=schema.validate(o,p)
            self.assertEqual(qualification.evaluate(s,validated['analyses'][0],p['evidence'],'AZIENDE',identity())['state'],'VERIFIED')

    def test_clearly_unrelated_requested_activity_rejected(self):
        b=agency('camerieri freelance')
        self.assertEqual(b['state'],'REJECTED')
        self.assertEqual(b['affinity']['value'],'CLEARLY_UNRELATED')

    def test_email_alone_does_not_create_interest(self):
        b={'url':'https://alfa.example','official_domain':'https://alfa.example','identity_verified':True,
           'original':True,'state':'REJECTED','contacts':identity()['contacts']}
        a=alignment.dimensions(b)
        self.assertTrue(a['CONTACT_AVAILABLE']);self.assertFalse(a['READY_FOR_OUTREACH'])
        self.assertEqual(a['COMMERCIAL_INTEREST'],'UNKNOWN')

    def test_startup_types_and_no_imputed_equity_value(self):
        cases=[('Paid freelance contract.', 'PAID_DEVELOPMENT_OPPORTUNITY'),
               ('Technical cofounder role.', 'TECHNICAL_COFOUNDER_OPPORTUNITY'),
               ('Equity-only compensation.', 'EQUITY_ONLY_OPPORTUNITY'),
               ('Terms to be discussed.', 'TECHNICAL_COFOUNDER_OPPORTUNITY')]
        for terms,kind in cases:
            with self.subTest(terms=terms):
                b=startup(terms);v=commercial_view.enrich(b)
                self.assertNotEqual(b['state'],'REJECTED',b['reason'])
                self.assertEqual(v['commercial_alignment']['arrangement'],kind)
                self.assertIsNone(v['commercial_alignment']['equity_value'])
                self.assertIsNone(v['project_value']['amount'])
                if kind!='PAID_DEVELOPMENT_OPPORTUNITY':
                    self.assertEqual(v['opportunity_type'],'OPPORTUNITA_IMPRENDITORIALE')
                    self.assertNotEqual(v['commercial_dimensions']['buying_intent']['value'],'DECLARED_REQUEST')

    def test_unknown_arrangement_and_budget_stay_unknown(self):
        a=alignment.dimensions({'state':'NEEDS_REVIEW'})
        self.assertEqual(a['arrangement'],'UNCLEAR_ARRANGEMENT')
        self.assertEqual(agency()['budget']['kind'],'UNKNOWN')
        self.assertEqual(agency(extra='Budget: €500 fixed price')['state'],'REJECTED')
        entrepreneurial=startup('Equity-only compensation. Budget: €500 fixed price')
        self.assertNotEqual(entrepreneurial['state'],'REJECTED')
        self.assertEqual(entrepreneurial['budget']['kind'],'UNKNOWN')
        self.assertEqual(entrepreneurial['declared_financial_terms']['amount'],500)

    def test_snippet_is_not_qualified_or_contact_ready(self):
        s=source(original=False);p,o=output(s)
        b=qualification.evaluate(s,o['analyses'][0],p['evidence'],'SOCIAL',identity())
        self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))
        self.assertFalse(b['commercial_alignment']['READY_FOR_OUTREACH'])

    def test_shared_rules_in_each_flow(self):
        s=source();p,o=output(s);ident=identity();ident['contacts']=[]
        for flow in ('AZIENDE','AGENCIES','SOCIAL','STARTUPS','NEWS'):
            b=qualification.evaluate(s,o['analyses'][0],p['evidence'],flow,ident)
            self.assertEqual(b['state'],'VERIFIED',flow)
            self.assertFalse(b['commercial_alignment']['CONTACT_AVAILABLE'])

    def test_commercial_queries_generic_agency_and_cofounder(self):
        for flow,text in [('AGENCIES','web agency cerca collaboratori freelance Veneto'),
                          ('STARTUPS','startup cerca cofounder sviluppatore MVP Veneto')]:
            self.assertTrue(commercial_policy.assess_query(query(text),flow)['allowed'])

    def test_recorded_nhw_is_replayed_without_rewriting_history(self):
        f=load();original=copy.deepcopy(f['cases'][0])
        b=replay(f['cases'][0],f['configuration']['regions'])
        self.assertEqual(f['cases'][0],original)
        self.assertEqual(b['state'],'NEEDS_REVIEW')
        self.assertEqual(b['missing'],['publication'])
        self.assertFalse(any(v['field']=='technical' for v in b['facts']))
        self.assertTrue(b['commercial_alignment']['CONTACT_AVAILABLE'])
        self.assertEqual(b['completion_queue']['active_assignment'],'UNKNOWN')


class Website(unittest.TestCase):
    def test_design_assessment_requires_rendered_styles_and_cannot_qualify_alone(self):
        page={'url':'https://alfa.example','status':200,'html':'<h1>Servizi</h1><p>Descrizione servizi.</p>','checked_at':DATE}
        style={'text':'Servizi','font_size':16,'font_weight':'400','color':'rgb(0,0,0)'}
        row={'url':page['url'],'viewport':390,'scope':'rendered','complete':True,
             'measurements':{'typography':{'headings':[style],'paragraphs':[{**style,'text':'Descrizione servizi.'}]}}}
        a=audit([page],{'completed':True,'pages':[row]})
        self.assertEqual(a['design_assessment']['status'],'PARTIAL')
        self.assertTrue(any(o.get('observation_type')=='DESIGN_ASSESSMENT' for o in a['observations']))
        self.assertEqual(a['website_opportunity'],'LIMITED_OR_UNPROVEN')
        row['complete']=False
        a=audit([page],{'completed':False,'pages':[row]})
        self.assertEqual(a['design_assessment']['status'],'NOT_ASSESSED')

    def test_content_ux_path_reaches_worklist_without_technical_errors(self):
        import test_agent8_proactive as cycle
        t=cycle.ProactiveCycle();t.setUp();self.addCleanup(t.tearDown)
        extra=content_pages()[0]['html']
        for page in t.pages.values():
            page['status']=200
            page['html']=page['html'].replace('<h1>Not found</h1>','')+extra.replace('<h1>Alfa</h1>','')
        original_model=t.model
        def model(payload,cfg,check):
            value=original_model(payload,cfg,check)
            if payload['task']==website_review.TASK:
                value['output'].update(
                    reason='Contenuti estesi senza sezioni e collegamenti generici a percorsi distinti.',
                    scope='Nuovo sito completo con architettura dei servizi e navigazione riprogettate.',
                    why_not_small_fix='Occorre riprogettare contenuti e percorsi su più pagine, non correggere un collegamento.')
            return value
        t.model=model
        b=t.run_case(False)
        self.assertEqual(b['state'],'POTENTIAL',b['reason'])
        self.assertEqual(b['proposal_type'],'COMPLETE_NEW_WEBSITE')
        self.assertFalse(b['explicit_demand'])
        self.assertEqual(b['purchase_intent'],'UNKNOWN')
        self.assertFalse(any(o['status']=='ISSUE' and o['severity']=='major' for o in b['website_audit']['observations']))
        self.assertTrue(listing(t.store,{'view':'ready'})['items'])

    def test_functioning_site_content_and_ux_are_eligible_for_review(self):
        a=audit(content_pages())
        self.assertEqual(a['website_opportunity'],'REVIEW_COMPLETE_PROJECT')
        self.assertTrue(all(o['evidence']['value']==200 for o in a['observations'] if o['code']=='http_status'))
        qualitative=[o for o in a['observations'] if o['status']=='ASSESSMENT']
        self.assertEqual({o['observation_type'] for o in qualitative},{'OBSERVED_UX_ISSUE','CONTENT_ASSESSMENT'})
        self.assertTrue(all(o['evidence']['content_hash'] and o['evidence']['checked_at'] for o in qualitative))
        p=website_review.payload(a,{'offer_evidence':[{'url':content_pages()[0]['url'],'quote':'Servizi industriali'}]},identity())
        value={'decision':'COMPLETE_PROJECT','observation_ids':[o['id'] for o in p['observations']],
               'business_fact_ids':[f['id'] for f in p['business_facts']], 'reason':'Percorsi ed offerta non distinguibili.',
               'scope':'Nuovo sito completo: struttura di servizi e navigazione.', 'why_not_small_fix':'Riorganizzare contenuti e percorsi su più pagine.',
               'objections':['Interesse da confermare.'],'unknowns':[]}
        p['external_solutions']=[{'access':{'content_read':False},'url':'https://shop.example'}]
        self.assertEqual(website_review.validate(value,p)[0]['decision'],'COMPLETE_PROJECT')
        from sales.agent6 import news_review
        news={**value,'event_ids':['event1'],'event_relation':'Nuova offerta da rappresentare nei percorsi documentati.',
              'existing_solution_check':''}
        p.update(events=[{'id':'event1'}],event_current=True)
        self.assertEqual(news_review.validate(news,p)[0]['decision'],'COMPLETE_PROJECT')
        with self.assertRaises(schema.ValidationError):
            news_review.validate({**news,'event_relation':''},p)

    def test_generic_aesthetic_opinion_not_sufficient(self):
        p={'observations':[],'business_facts':[{'id':'b'}]}
        v={'decision':'COMPLETE_PROJECT','observation_ids':[],'business_fact_ids':['b'],'reason':'Design vecchio',
           'scope':'Restyling','why_not_small_fix':'Brutto','objections':[],'unknowns':[]}
        with self.assertRaises(schema.ValidationError):website_review.validate(v,p)

    def test_blocked_crawler_produces_no_qualitative_defects(self):
        p=content_pages();p[0]['status']=403;p[1]['status']=500
        a=audit(p,{'completed':False,'failure_codes':['timeout'],'pages':[]})
        self.assertFalse(any(o['status']=='ASSESSMENT' for o in a['observations']))
        self.assertEqual(a['website_opportunity'],'LIMITED_OR_UNPROVEN')

    def test_small_fix_not_complete_rebuild(self):
        self.assertEqual(evaluated(source(source()['text'].replace('complete website','minor fixes')),
            fields={'entity':'Alfa Srl','request':'We are looking for a freelance WordPress developer to build our minor fixes. Remote from Italy.',
                    'technical':'WordPress','contract':'freelance','geography':'Remote from Italy.'})['state'],'NEEDS_REVIEW')


class Worklist(unittest.TestCase):
    def test_contactless_qualification_not_in_ready_view_and_history_unchanged(self):
        t=support.Campaign32Fix();t.setUp();self.addCleanup(t.tearDown)
        b=evaluated();b['contacts']=[]
        rid=memory.save_record(t.store,t.c,'AZIENDE',b)
        with t.store.connect() as db:before=db.execute('select body from agent6_records where id=?',(rid,)).fetchone()[0]
        self.assertEqual(listing(t.store,{'view':'verified'})['total'],1)
        self.assertEqual(listing(t.store,{'view':'ready'})['total'],0)
        self.assertEqual(listing(t.store,{'view':'all'})['counts']['ready'],0)
        with t.store.connect() as db:
            self.assertEqual(db.execute('select body from agent6_records where id=?',(rid,)).fetchone()[0],before)
            self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok')

    def test_dynamic_staleness_revokes_readiness_without_rewriting_saved_state(self):
        from datetime import datetime,timezone
        t=support.Campaign32Fix();t.setUp();self.addCleanup(t.tearDown)
        memory.save_record(t.store,t.c,'AZIENDE',evaluated())
        r=listing(t.store,{'view':'review'},at=datetime(2027,1,1,tzinfo=timezone.utc))['items'][0]
        self.assertEqual(r['saved_state'],'VERIFIED')
        self.assertFalse(r['body']['commercial_alignment']['READY_FOR_OUTREACH'])
