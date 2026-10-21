"""Commercial milestones: original-page fixtures, no provider or model network."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.commercial.inspection import inspect
from sales.commercial.storage import Opportunities

def page(text,title='Alfa Srl',url='https://alfa.example/jobs/web',date=True,region='Veneto',city='Padova',code='PD',extra='',job=None):
    schema={'@type':'Organization','name':'Alfa Srl','url':'https://alfa.example/','vatID':'IT12345678901','address':{'streetAddress':'Via Roma 1','postalCode':'35100','addressLocality':city,'addressRegion':region,'addressCountry':'IT'}}
    html=f'<title>{title}</title><script type="application/ld+json">{json.dumps(schema)}</script>'
    if job:html+=f'<script type="application/ld+json">{json.dumps(job)}</script>'
    if date:html+=f'<meta property="article:published_time" content="{now()[:10]}">'
    html+=f'<h1>{title}</h1><p>{text}</p>{extra}<footer><p>Alfa Srl</p><p>P.IVA 12345678901</p><p>Via Roma 1, 35100 {city} ({code})</p><a href="mailto:info@alfa.example">Email</a></footer>'
    return {'url':url,'html':html,'status':200,'checked_at':now()}

class CommercialTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store);self.c=self.rs.create()
        self.repo=Opportunities(self.store)
    def inspect(self,p,engine='FREELANCE'):
        def read(web,url):return {**p,'url':url}
        with patch('sales.commercial.inspection.ResearchWeb.get',read):return inspect(self.store,{'url':p['url'],'commercial_engine':engine})

class FreelanceTests(CommercialTestCase):
    def test_explicit_freelance_unknown_budget_is_verified_and_saved(self):
        found=self.inspect(page('Cerchiamo uno sviluppatore WordPress freelance per un progetto web.'))
        self.assertEqual(found['result']['state'],'VERIFIED');self.assertIsNone(found['result']['compensation']['amount'])
        ident=self.repo.save(self.c,found['identity'],found['documents'],found['result'])
        self.assertEqual(self.repo.get(ident)['state'],'VERIFIED')
    def test_employee_is_rejected(self):
        self.assertEqual(self.inspect(page('Cerchiamo uno sviluppatore frontend con contratto a tempo indeterminato.'))['result']['classification'],'employee')
    def test_ambiguous_contract_and_missing_date(self):
        self.assertEqual(self.inspect(page('Cerchiamo uno sviluppatore backend.'))['result']['state'],'NEEDS_REVIEW')
        self.assertEqual(self.inspect(page('Cerchiamo sviluppatore WordPress freelance.',date=False))['result']['state'],'NEEDS_REVIEW')
    def test_expired_request(self):
        p=page('Cerchiamo sviluppatore WordPress freelance. Annuncio scaduto.')
        self.assertEqual(self.inspect(p)['result']['classification'],'expired')
    def test_duplicate_request_has_one_opportunity_and_revision(self):
        found=self.inspect(page('Cerchiamo sviluppatore WordPress freelance.'))
        ids=[self.repo.save(self.c,found['identity'],found['documents'],found['result']) for _ in range(2)]
        self.assertEqual(ids[0],ids[1]);self.assertEqual(len(self.repo.get(ids[0])['revisions']),1)

class AgencyTests(CommercialTestCase):
    def check_agency(self,text,**kwargs):
        return self.inspect(page('Siamo una web agency. '+text,title='Alfa Srl · Web agency',**kwargs),'AGENCIES')['result']
    def test_open_collaboration(self):self.assertEqual(self.check_agency('Cerchiamo sviluppatori WordPress freelance.')['state'],'VERIFIED')
    def test_standing_collaboration_no_date_or_project_required(self):
        r=self.check_agency('Accettiamo collaborazioni continuative con sviluppatori WordPress freelance.',date=False)
        self.assertEqual(r['state'],'NEEDS_REVIEW');self.assertEqual(r['classification'],'ongoing')
    def test_careers_page_is_not_external_demand(self):
        self.assertEqual(self.check_agency('Cerchiamo sviluppatore frontend a tempo indeterminato.')['state'],'REJECTED')
        self.assertEqual(self.check_agency('Lavora con noi. Invia il CV.')['state'],'REJECTED')
    def test_agency_without_request(self):self.assertEqual(self.check_agency('Realizziamo siti WordPress e piattaforme ecommerce.')['state'],'REJECTED')
    def test_generic_availability_remains_review(self):self.assertEqual(self.check_agency('Valutiamo collaborazioni WordPress e backend.')['state'],'NEEDS_REVIEW')
    def test_existing_suppliers_are_not_an_open_invitation(self):self.assertEqual(self.check_agency('Collaboriamo con sviluppatori WordPress freelance sui nostri progetti.')['state'],'NEEDS_REVIEW')
    def test_multisite_agency(self):
        address={'@type':'Organization','name':'Alfa Srl','url':'https://alfa.example/','address':{'streetAddress':'Via Verdi 3','postalCode':'20100','addressLocality':'Milano','addressRegion':'Lombardia','addressCountry':'IT'}}
        r=self.check_agency('Accettiamo collaborazioni WordPress freelance.',extra='<script type="application/ld+json">'+json.dumps(address)+'</script>')
        self.assertEqual(r['state'],'NEEDS_REVIEW');self.assertEqual(set(r['geography']['regions']),{'Veneto','Lombardia'})

class StartupTests(CommercialTestCase):
    def startup(self,text):return self.inspect(page('Siamo una startup italiana. '+text),'STARTUPS')['result']
    def test_paid_mvp(self):
        r=self.startup('Cerchiamo sviluppatore freelance per MVP web, collaborazione retribuita.')
        self.assertEqual(r['state'],'VERIFIED');self.assertEqual(r['compensation']['type'],'cash');self.assertIsNone(r['compensation']['amount'])
    def test_technical_partner(self):self.assertEqual(self.startup('Cerchiamo partner tecnico per sviluppare la piattaforma web.')['state'],'VERIFIED')
    def test_equity_and_cofounder_not_cash(self):
        r=self.startup('Cerchiamo co-founder CTO per il nostro MVP con compenso in equity.')
        self.assertEqual(r['state'],'POTENTIAL');self.assertEqual(r['classification'],'cofounder');self.assertEqual(r['compensation']['type'],'equity')
    def test_hybrid_distinguished(self):self.assertEqual(self.startup('Cerchiamo sviluppatore MVP, collaborazione retribuita cash ed equity.')['compensation']['type'],'hybrid')
    def test_funding_without_request_is_rejected(self):self.assertEqual(self.startup('Abbiamo raccolto finanziamenti per 500000 euro per il nostro MVP.')['state'],'REJECTED')
    def test_unavailable_request_not_qualified(self):
        with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=TimeoutError('Non disponibile')):
            with self.assertRaises(TimeoutError):inspect(self.store,{'url':'https://alfa.example/jobs','commercial_engine':'STARTUPS'})

class RebuildTests(CommercialTestCase):
    def evaluate(self,screen,browser):
        from sales.commercial.rebuild import evaluate
        from sales.research_analysis import identity_from
        from sales.commercial.geography import locate
        p=page('Produzione componenti industriali e servizi.')
        i=identity_from([p]);return evaluate(i,[p],locate([p],i),screen,browser)
    def test_significant_barriers_are_potential_never_verified(self):
        f={'code':'broken_contact','severity':'major','url':'https://alfa.example/contatti','quote':'HTTP 404'}
        b={'completed':True,'links':[f['url']],'findings':[{'code':'mobile_content','severity':'major','url':'https://alfa.example/','quote':'Testo fuori schermo'}]}
        r=self.evaluate({'promising':True,'findings':[f]},b)
        self.assertEqual(r['state'],'POTENTIAL');self.assertEqual(r['priority'],'high')
    def test_pagespeed_alone_is_not_rebuild_reason(self):
        r=self.evaluate({'promising':False,'findings':[]},{'completed':True,'performance':12})
        self.assertEqual(r['state'],'REJECTED')
    def test_sparse_html_requires_browser_not_assumed_adequate(self):
        p=page('Prodotti e servizi industriali.',extra='<meta name="viewport" content="width=device-width">')
        with patch('sales.commercial.browser.review',return_value={'completed':True,'findings':[],'links':[]}) as browser:
            r=self.inspect(p,'WEBSITE_REBUILD')['result']
        browser.assert_called_once();self.assertEqual(r['classification'],'browser_completed')
    def test_browser_incomplete_never_makes_potential(self):
        self.assertEqual(self.evaluate({'promising':True,'findings':[]},{'completed':False,'limits':['robots non verificabile']})['state'],'UNVERIFIABLE')
    def test_minor_problem_not_priority(self):
        r=self.evaluate({'promising':False,'findings':[{'code':'viewport','severity':'minor'}]},None)
        self.assertEqual(r['classification'],'insufficient_problems');self.assertEqual(r['state'],'REJECTED')
    def test_single_significant_problem_stays_secondary(self):
        r=self.evaluate({'promising':True,'findings':[]},{'completed':True,'links':[],'findings':[{'code':'mobile_content','severity':'major','url':'https://alfa.example/','quote':'Contenuto tagliato'}]})
        self.assertEqual(r['classification'],'insufficient_problems');self.assertEqual(r['state'],'REJECTED')
