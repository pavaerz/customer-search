"""Five-flow lifecycle with synthetic companies, real extraction and qualification.

Only external search/HTTP/model transport is substituted. Sources are explicitly
synthetic; positive outcomes prove orchestration, not real commercial efficacy.
"""
import copy
import html
import json
import unittest
from unittest.mock import patch
import test_agent6 as base
import test_agent6_campaign32 as support
from sales.agent6 import FLOWS, schema
from sales.agent6 import news_review
from test_agent8_proactive import pages as audit_pages,browser as audit_browser,ROOT as AUDIT_ROOT
from sales.agent6.api import preview
from sales.commercial.coordinator import run_campaign


class FiveFlowCycle(unittest.TestCase):
    def setUp(self):
        self.fixture=support.Campaign32Fix();self.fixture.setUp()
        self.store=self.fixture.store;self.rs=self.fixture.rs
        self.rs.stop(self.fixture.c['id']);self.rs.paused(self.fixture.c['id'])
        filters=copy.deepcopy(self.fixture.filters);filters['commercial_engines']=list(FLOWS)
        filters['deep_plan_token']=preview(self.store,filters)['approval_token']
        self.c=self.rs.create(filters)
        self.names={'AZIENDE':'Alfa Srl','AGENCIES':'Beta Srl','STARTUPS':'Gamma Srl','SOCIAL':'Delta Srl','NEWS':'Epsilon Srl'}
        self.queries={'AZIENDE':'azienda cerca freelance WordPress Veneto','AGENCIES':'agenzia cerchiamo freelance WordPress collaborazione Veneto',
                      'STARTUPS':'startup cerchiamo freelance frontend MVP Italia','SOCIAL':'site:linkedin.com cerchiamo freelance WordPress Italia',
                      'NEWS':'azienda nuovi prodotti sito web Veneto'}
        self.urls={f:'https://'+name.split()[0].lower()+'.example/careers' for f,name in self.names.items()}
        self.linkedin='https://www.linkedin.com/posts/delta-freelance-wordpress'
        self.news='https://press.example/epsilon-new-products'
        self.signal='Epsilon Srl launches new products needing an online catalogue.'
        self.gap='Epsilon Srl online product catalogue is absent.'
        self.constraints=('Limited single workflow MVP for bookings. No sensitive data; authentication and access control. '
                          'No external integrations. Maintenance included and agreed.')
        self.requests={f:'We are looking for a freelance '+('frontend developer to build our complete web app.' if f=='STARTUPS' else 'WordPress developer to build our complete website.')+' Remote from Italy.' for f in self.names}
        self.pages={}
        for f,name in self.names.items():
            lines=[name,'Posted 2 days ago',self.requests[f]]
            if f=='AGENCIES':lines.append('We are a digital agency.')
            if f=='STARTUPS':lines+=['We are a startup.',self.constraints]
            if f=='NEWS':lines=[name,'Posted 2 days ago',self.gap,'complete website','WordPress','not yet available','Remote from Italy.']
            self.pages[self.urls[f]]=self.page(self.urls[f],name,lines)
        self.pages[self.news]=self.page(self.news,'Territorial News',[self.names['NEWS'],self.signal],owner=False)
        self.pages[self.news]['html']+='<meta property="article:published_time" content="2026-10-18"><a href="https://epsilon.example/">Epsilon Srl</a>'
        for url,page in audit_pages().items():
            target=url.replace(AUDIT_ROOT,'https://epsilon.example/')
            self.pages[target]={**page,'url':target,'html':page['html'].replace('alfa.example','epsilon.example').replace('Alfa Srl','Epsilon Srl')}
        self.reads=[];self.searches=[];self.calls=[]

    def page(self,url,name,lines,owner=True):
        markup='<title>'+html.escape(name)+'</title>'+''.join('<p>'+html.escape(s)+'</p>' for s in lines)
        if owner:markup+='<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@'+url.split('/')[2]+'">Contatti</a>'
        return {'url':url,'status':200,'checked_at':base.DATE,'html':markup}

    def tearDown(self):self.fixture.tearDown()

    def search(self,store,payload,check):
        self.searches.append(copy.deepcopy(payload));query=payload['query']
        flow=next((f for f,q in self.queries.items() if q==query),None)
        if flow:
            url=self.linkedin if flow=='SOCIAL' else self.news if flow=='NEWS' else self.urls[flow]
        else:
            flow=next((f for f,name in self.names.items() if name in query),None)
            if not flow:return []
            url=self.urls[flow]
        return [{'url':url,'title':self.names[flow],'content':self.signal if flow=='NEWS' else self.requests[flow]}]

    def read(self,url):
        self.assertNotIn('linkedin.com',url,'Restricted source must use an authorized alternative')
        self.reads.append(url)
        return self.pages[url]

    def model(self,p,cfg,check):
        flow=p.get('flow','NEWS' if p['task']==news_review.TASK else None)
        self.calls.append((flow,p['task']))
        name=self.names[flow]
        if p['task']==news_review.TASK:
            return {'output':{'decision':'COMPLETE_PROJECT','observation_ids':[o['id'] for o in p['observations']],
                'business_fact_ids':[f['id'] for f in p['business_facts']],
                'reason':'Ipotesi: catalogo della nuova offerta e contatto non raggiungibili nel campione.',
                'scope':'Riprogettazione dei percorsi prodotti e contatti su mobile.',
                'why_not_small_fix':'Problemi misurati in più percorsi e dimensioni richiedono una revisione coordinata.',
                'objections':['Interesse e budget non dichiarati.'],'unknowns':[],
                'event_ids':[p['events'][0]['id']],'event_relation':'Lancio prodotti e accesso al catalogo interrotto.',
                'existing_solution_check':'Il campione di pagine non offre un percorso alternativo al catalogo o alla richiesta.'},'usage':{}}
        if p['task']==schema.PLAN:
            proposal=support.query(self.queries[flow]);proposal['hypothesis']='Verify the named commercial need and independent digital gap on original sources.'
            return {'output':{'decision':'search' if not p['round'] else 'stop','reason':'Synthetic dedicated-flow plan','queries':[proposal] if not p['round'] else []},'usage':{'input_tokens':100,'output_tokens':100}}
        analyses=[]
        for rid in p['result_ids']:
            anchors=[(e,s) for e in p['evidence'] if e['result_id']==rid for s in e['segments']]
            fields={'entity':name,'signal':self.signal} if flow=='NEWS' else {'entity':name,'request':self.requests[flow].split(' Remote')[0]}
            if p['task']==schema.READ:
                if flow=='NEWS':fields.update(digital_gap=self.gap,scope='complete website',feasibility='WordPress',existing_solution='not yet available')
                else:
                    fields.update(technical='frontend developer' if flow=='STARTUPS' else 'WordPress',contract='freelance',geography='Remote from Italy.')
            facts=[]
            for field,needle in fields.items():
                anchor=next((s for e,s in anchors if (s['text']==needle if field=='entity' else needle in s['text']) and (field!='signal' or not e['original'] or e['url']==self.news)),None)
                if anchor:facts.append({'field':field,'ref':{'segment_id':anchor['segment_id']}})
            if flow=='STARTUPS' and p['task']==schema.READ:
                for e,s in anchors:
                    if e['original'] and s['text'] in self.constraints:
                        facts.append({'field':'feasibility','ref':{'segment_id':s['segment_id']}})
            analyses.append({'result_id':rid,'kind':'COMPANY_SIGNAL' if flow=='NEWS' else 'AGENCY_PARTNERSHIP' if flow=='AGENCIES' else 'BUYER_DEMAND',
                             'kind_ref':facts[0]['ref'] if facts else None,'facts':facts,'hypothesis':'Synthetic fixture, no real lead','missing':[]})
        return {'output':{'analyses':analyses},'usage':{'input_tokens':100,'output_tokens':100}}

    def test_all_flows_reach_attributed_original_decisions_with_existing_limits(self):
        def browser(store,pages,*a,**kw):
            result=audit_browser(pages)
            for finding in result['findings']:finding['url']='https://epsilon.example/'
            return result
        with patch('socket.create_connection',side_effect=AssertionError('Offline only')),patch('sales.agent6.ai.infer',side_effect=self.model),patch('sales.agent6.coordinator.acquire',side_effect=self.search),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=self.read),patch('sales.commercial.browser.review',side_effect=browser):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:
            records=[json.loads(r[0]) for r in c.execute('select body from agent6_records where campaign_id=?',(self.c['id'],))]
            calls=c.execute('select count(*) from commercial_ai_executions where campaign_id=? and attempt=1',(self.c['id'],)).fetchone()[0]
            self.assertLessEqual(calls,20)
            self.assertTrue(all(r[0]<=8 for r in c.execute('select count(*) from commercial_ai_executions where campaign_id=? and attempt=1 group by engine',(self.c['id'],))))
            self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')
        self.assertEqual(set(f for f,t in self.calls if t==schema.READ),set(FLOWS))
        for flow,name in self.names.items():
            expected='POTENTIAL' if flow in ('AGENCIES','NEWS') else 'VERIFIED'
            candidates=[b for b in records if b['entity_name']==name and b['state']==expected]
            self.assertTrue(candidates,(flow,[(b['state'],b['reason'],b.get('missing')) for b in records if b['flow']==flow],self.calls))
            b=candidates[0];self.assertTrue(b['identity_verified']);self.assertTrue(b['contacts']);self.assertEqual(b['budget']['kind'],'UNKNOWN')
            self.assertEqual(b['evidence_level'],'WEBSITE_AUDIT_VERIFIED' if flow=='NEWS' else 'ORIGINAL_VERIFIED')
            self.assertEqual(b['official_domain'].split('/')[2],self.urls[flow].split('/')[2])
        self.assertIn(self.urls['SOCIAL'],self.reads);self.assertNotIn(self.linkedin,self.reads)
        self.assertTrue(any(p.get('selection')=='verification' and self.names['SOCIAL'] in p['query'] for p in self.searches))
