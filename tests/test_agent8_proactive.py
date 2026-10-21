"""Synthetic end-to-end company research, protected transport replaced offline.

These outcomes are fixtures, not customers or commercial validation.
"""
import copy,json,unittest
from unittest.mock import patch
import test_agent6_campaign32 as support
from sales.agent6 import website_audit,website_review,proactive,schema
from sales.agent6.api import preview
from sales.agent6.worklist import listing
from sales.commercial.coordinator import run_campaign

ROOT='https://alfa.example/'


def pages():
    organization={'@context':'https://schema.org','@type':'Organization','name':'Alfa Srl','legalName':'Alfa Srl',
        'url':ROOT,'vatID':'IT12345678901','address':{'@type':'PostalAddress','streetAddress':'Via Roma 12','addressLocality':'Padova','postalCode':'35100','addressRegion':'Veneto','addressCountry':'IT'}}
    def page(path,body,status=200):
        return {'url':ROOT+path,'status':status,'checked_at':'2026-10-19T12:00:00+00:00',
            'html':'<title>Alfa Srl</title><script type="application/ld+json">'+json.dumps(organization)+'</script>'+
                   '<h1>Alfa Srl</h1><p>Produciamo macchinari industriali su misura per lavorazioni meccaniche e cataloghi tecnici.</p>'+body+
                   '<footer>Alfa Srl · Partita IVA: 12345678901 · Sede legale: Via Roma 12, 35100 Padova (PD)<a href="mailto:info@alfa.example">Ufficio commerciale</a></footer>'}
    return {
        ROOT:page('','<a href="/prodotti">Prodotti</a><a href="/contatti">Contatti</a>'),
        ROOT+'prodotti':page('prodotti','<a href="/catalogo">Catalogo completo</a>'),
        ROOT+'contatti':page('contatti','<a href="/preventivo">Richiedi preventivo</a>'),
        ROOT+'catalogo':page('catalogo','<h1>Not found</h1>',404),
        ROOT+'preventivo':page('preventivo','<h1>Not found</h1>',404),
    }


def browser(pages,defects=True):
    return {'completed':True,'outcome':'complete','pages':[{'url':p['url'],'viewport':390,'complete':True,'scope':'rendered',
             'measurements':{'clipped':3 if defects else 0,'overflow':180 if defects else 0}} for p in pages],
        'findings':[{'code':'mobile_content','severity':'major','url':ROOT,'viewport':390,'quote':'Tre blocchi fuori larghezza in due misure a 390 px.'}] if defects else []}


class Audit(unittest.TestCase):
    def test_desktop_overflow_does_not_become_mobile_defect(self):
        p=pages()[ROOT];b=browser([p],False)
        b['pages'].append({'url':ROOT,'viewport':1366,'complete':True,'scope':'rendered','measurements':{'overflow':20}})
        b['findings']=[{'code':'horizontal_overflow','severity':'moderate','url':ROOT,'viewport':1366,'quote':'Overflow misurato solo desktop'}]
        result=website_audit.audit([p],b)
        self.assertEqual(next(o for o in result['observations'] if o['code']=='responsive')['status'],'PASS')

    def test_external_shop_is_counterevidence_not_another_company_page(self):
        p=pages()[ROOT];p['html']+='<a href="https://shop.example/">Negozio online</a><a href="https://other.example/privacy">Privacy</a>'
        target={'url':'https://shop.example/','html':'<h1>Vendita prodotti Alfa</h1>','status':200,'purpose':'external_solution'}
        result=website_audit.audit([p,target])
        self.assertEqual(len(result['external_solutions']),1)
        self.assertTrue(result['external_solutions'][0]['access']['content_read'])
        self.assertEqual([x['url'] for x in result['pages']],[ROOT])
        request=website_review.payload(result,{'offer_evidence':[]},{})
        self.assertIn('Vendita prodotti Alfa',request['external_solutions'][0]['text'])

    def test_missing_viewport_does_not_invent_mobile_or_performance_problem(self):
        report=website_audit.audit([pages()[ROOT]])
        observations={o['code']:o for o in report['observations']}
        self.assertEqual(observations['viewport']['status'],'ISSUE')
        self.assertEqual(observations['responsive']['status'],'UNKNOWN')
        self.assertEqual(observations['performance']['status'],'UNKNOWN')
        self.assertEqual(report['website_opportunity'],'LIMITED_OR_UNPROVEN')

    def test_real_http_results_and_completed_browser_required(self):
        acquired=list(pages().values());r=website_audit.audit(acquired,browser(acquired))
        self.assertEqual(r['website_opportunity'],'REVIEW_COMPLETE_PROJECT')
        self.assertEqual(len([o for o in r['observations'] if o['code']=='broken_commercial_path']),2)
        b=browser(acquired);b['pages'][0]['complete']=False
        incomplete=website_audit.audit(acquired,b)
        self.assertFalse(any(o['code']=='mobile_content' for o in incomplete['observations']))

    def test_unvisited_link_is_not_broken_and_pdf_not_followed(self):
        p=pages()[ROOT];p['html']+='<a href="/catalogo.pdf">Catalogo PDF</a>'
        self.assertFalse(any(x['url'].endswith('.pdf') for x in website_audit.public_links(p)))
        self.assertFalse(any(o['code']=='broken_commercial_path' for o in website_audit.audit([p])['observations']))

    def test_ai_cannot_invent_observations_or_sell_minor_fixes_as_complete_project(self):
        request={'observations':[{'id':'a','severity':'minor','dimension':'TECHNICAL_ISSUES','url':ROOT}],
                 'business_facts':[{'id':'b'}]}
        value={'decision':'COMPLETE_PROJECT','observation_ids':['a'],'business_fact_ids':['b'],
               'reason':'Inferenza','scope':'Rifacimento completo','why_not_small_fix':'Motivo','objections':[],'unknowns':[]}
        with self.assertRaisesRegex(ValueError,'insufficient_full_project'):website_review.validate(value,request)
        value['observation_ids']=['invented']
        with self.assertRaisesRegex(ValueError,'unknown_audit_evidence'):website_review.validate(value,request)


class ProactiveCycle(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.rs=self.base.store,self.base.rs
        self.rs.stop(self.base.c['id']);self.rs.paused(self.base.c['id'])
        f=copy.deepcopy(self.base.filters);f['commercial_engines']=['AZIENDE'];f['work_budget']['max_reads']=6
        f['deep_plan_token']=preview(self.store,f)['approval_token'];self.c=self.rs.create(f)
        self.pages=pages();self.calls=[];self.reads=[]
    def tearDown(self):self.base.tearDown()

    def model(self,p,cfg,check):
        self.calls.append(p)
        if p['task']==schema.PLAN:
            q=support.query('produttori macchinari Veneto prodotti sito ufficiale');q['strategy']=proactive.STRATEGY
            return {'output':{'decision':'search' if not p['round'] else 'stop','queries':[q] if not p['round'] else [],'reason':'Synthetic test plan'},'usage':{}}
        self.assertEqual(p['task'],website_review.TASK)
        return {'output':{'decision':'COMPLETE_PROJECT','observation_ids':[o['id'] for o in p['observations']],
            'business_fact_ids':[f['id'] for f in p['business_facts']],
            'reason':'Ipotesi sintetica: percorsi di catalogo e richiesta non raggiungibili e contenuti mobile tagliati.',
            'scope':'Riprogettazione coordinata di catalogo, navigazione e richiesta commerciale.',
            'why_not_small_fix':'La proposta da discutere unisce percorsi informativi e commerciali su pagine distinte; non basta il solo intervento mobile.',
            'objections':['Il cliente può preferire correzioni mirate; verificare la priorità.'],'unknowns':[]},'usage':{}}

    def run_case(self,browser_defects=True):
        def read(url):self.reads.append(url);return self.pages[url]
        with patch('socket.create_connection',side_effect=AssertionError('No network')),patch('sales.agent6.ai.infer',side_effect=self.model),patch('sales.agent6.coordinator.acquire',return_value=[{'url':ROOT,'title':'Alfa Srl','content':'Produzione macchinari industriali in Veneto.'}]),patch('sales.agent6.proactive.CompanyWeb.get',side_effect=read),patch('sales.commercial.browser.review',side_effect=lambda store,pages,*a,**kw:browser(pages,browser_defects)):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:
            records=[json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(self.c['id'],))]
        return next(b for b in records if b.get('website_audit'))

    def test_company_without_declared_request_reaches_proactive_worklist(self):
        body=self.run_case()
        self.assertEqual(body['state'],'POTENTIAL',body['reason'])
        self.assertEqual(body['opportunity_type'],'OPPORTUNITA_PROATTIVA')
        self.assertFalse(body['explicit_demand'])
        self.assertEqual(body['budget']['kind'],'UNKNOWN')
        self.assertEqual(body['purchase_intent'],'UNKNOWN')
        self.assertTrue(body['identity_verified'])
        self.assertEqual(len(set(self.reads)),len(self.reads))
        self.assertFalse(any(p['task']==schema.SCREEN for p in self.calls))
        from datetime import datetime,timezone
        self.assertEqual(listing(self.store,{'view':'ready'},at=datetime.now(timezone.utc))['total'],1)
        self.assertEqual(listing(self.store,{'view':'ready','type':'OPPORTUNITA_PROATTIVA','region':'Veneto','complete':'1'})['total'],1)
        self.assertEqual(listing(self.store,{'view':'ready','type':'DEMANDA_ESPLICITA'})['total'],0)
        self.assertEqual(listing(self.store,{'view':'ready','sector':'industria'})['total'],1)

    def test_good_site_does_not_spend_commercial_ai_or_become_lead(self):
        for path in ('catalogo','preventivo'):self.pages[ROOT+path]['status']=200
        b=self.run_case(False)
        self.assertEqual(b['state'],'REJECTED')
        self.assertFalse(any(p['task']==website_review.TASK for p in self.calls))

    def test_inaccessible_linked_shop_preserves_dossier_without_claiming_absence(self):
        self.pages[ROOT]['html']+='<a href="https://shop.example/">Shop online</a>'
        b=self.run_case()
        self.assertIn('https://shop.example/',self.reads)
        self.assertEqual(b['state'],'POTENTIAL')
        self.assertNotIn('existing_solution',b['missing'])
        self.assertTrue(any(p['task']==website_review.TASK for p in self.calls))
        self.assertFalse(b['website_audit']['external_solutions'][0]['access']['content_read'])

    def test_low_commercial_fit_is_not_promoted_despite_bad_site(self):
        for p in self.pages.values():p['html']=p['html'].replace('Produciamo macchinari industriali su misura per lavorazioni meccaniche e cataloghi tecnici.','Il mio diario personale.')
        b=self.run_case()
        self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))
        self.assertFalse(any(p['task']==website_review.TASK for p in self.calls))

    def test_stop_after_paid_interpretation_resumes_without_refetch_or_second_call(self):
        from sales.agent6.coordinator import AgentCoordinator
        from sales.agent6 import memory
        self.rs.enqueue(self.c['id'],'candidate','AZIENDE',{'url':ROOT,'query':'synthetic','proactive':True,'strategy':proactive.STRATEGY},'proactive-stop')
        w=AgentCoordinator(self.store,self.c);w.initialize()
        task=self.rs.claim(self.c['id'],self.c['generation'])
        def read(url):self.reads.append(url);return self.pages[url]
        saved=memory.save_record
        def stop_before_record(*args,**kwargs):
            self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
            raise InterruptedError('Synthetic Stop after completed inference')
        with patch('socket.create_connection',side_effect=AssertionError('No network')),patch('sales.agent6.ai.infer',side_effect=self.model),patch('sales.agent6.proactive.CompanyWeb.get',side_effect=read),patch('sales.commercial.browser.review',side_effect=lambda store,pages,*a,**kw:browser(pages)) as rendered:
            with patch('sales.agent6.proactive.memory.save_record',side_effect=stop_before_record):
                with self.assertRaises(InterruptedError):w.execute(task,lambda:None)
            count=len(self.reads)
            self.c=self.rs.resume(self.c['id']);w=AgentCoordinator(self.store,self.c);w.initialize()
            task=self.rs.claim(self.c['id'],self.c['generation'])
            self.assertIn('browser',task['payload']['website_checkpoint'])
            w.execute(task,lambda:None)
        self.assertEqual(len(self.reads),count)
        self.assertEqual(rendered.call_count,1)
        self.assertEqual(len(self.calls),1)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],1)
            body=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
        self.assertEqual(body['state'],'POTENTIAL')


if __name__=='__main__':unittest.main()
