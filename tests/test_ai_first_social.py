"""Public originals supplied by offline doubles, not live platform integration."""
import copy
import html
import json
import unittest
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import api,evidence,social
from sales.agent6.coordinator import AgentCoordinator
from sales.commercial.inspection import document

POST='https://mastodon.social/@alfa/123456'
PROFILE='https://mastodon.social/@alfa'
OFFICIAL='https://alfa.example/collabora'
REQUEST='Collaboriamo con professionisti freelance per progetti WordPress e frontend.'
COMMENT='Beta Srl: scrivere a commentatore@beta.example. Pubblicato il: 01/01/2010. US only.'


def post_page(url=POST,request=REQUEST,profile=PROFILE):
    content='<p>'+html.escape(request)+'</p><p>Remote from Italy.</p><p>info@alfa.example</p><a href="'+OFFICIAL+'">Sito ufficiale</a>'
    metadata={'@type':'SocialMediaPosting','url':url,'articleBody':content,
              'author':{'@type':'Organization','name':'Alfa Srl','url':profile},
              'datePublished':'2026-10-19'}
    return {'url':url,'status':200,'checked_at':harness.DATE,
            'html':'<title>Social network</title><h1>Alfa Srl</h1>'+content+
                   '<aside>'+html.escape(COMMENT)+'<a href="https://beta.example/">Sito del commentatore</a></aside>'+
                   '<script type="application/ld+json">'+json.dumps(metadata)+'</script>'}


class EvidenceBoundary(unittest.TestCase):
    def test_social_original_excludes_comments_dates_and_links_on_both_platforms(self):
        for url,profile in (('https://instagram.com/p/Example/','https://instagram.com/alfa/'),
                            ('https://linkedin.com/posts/alfa-example/','https://linkedin.com/company/alfa/')):
            with self.subTest(url=url):
                page=post_page(url,profile=profile);doc=document(page);packet=evidence.packet(page,doc)
                self.assertEqual(len(packet['units']),1)
                unit=packet['units'][0];parts=evidence.passages(packet,unit)
                text='\n'.join(e['text'] for e in parts)
                self.assertIn(REQUEST,text)
                self.assertIn('Alfa Srl',text)
                self.assertNotIn('Beta',text)
                self.assertNotIn('US only',text)
                self.assertNotIn('Social network',text)
                self.assertEqual([d['value'] for d in unit['dates']],['2026-10-19'])
                self.assertEqual([l['url'] for l in packet['links']],[OFFICIAL])
                for part in parts:
                    self.assertEqual(part['text'],doc['text'][part['offset']:part['offset']+len(part['text'])])
                self.assertTrue(social.scoped_geography(unit,['Veneto'])['allowed'])

    def test_missing_or_other_post_metadata_cannot_supply_an_original(self):
        page=post_page()
        page['html']=page['html'].split('<script')[0]
        self.assertEqual(evidence.packet(page,document(page))['units'],[])
        page=post_page();page['html']=page['html'].replace('"url": "'+POST+'"','"url": "'+POST+'other"')
        self.assertEqual(evidence.packet(page,document(page))['units'],[])

    def test_specific_job_does_not_use_other_job_or_platform_geography(self):
        url='https://linkedin.com/jobs/view/123456/'
        job={'@type':'JobPosting','url':url,'title':'Frontend freelance',
             'description':'Remote US only. Complete website project.',
             'hiringOrganization':{'name':'Alfa Srl','url':OFFICIAL,
                                   'address':{'addressCountry':'Italy'}},
             'datePosted':'2026-10-19'}
        page={'url':url,'checked_at':harness.DATE,'status':200,
              'html':'<p>Platform footer Italia</p><script type="application/ld+json">'+json.dumps(job)+'</script>'}
        unit=evidence.packet(page,document(page))['units'][0]
        self.assertFalse(social.scoped_geography(unit,['Veneto'])['allowed'])
        page['html']=page['html'].replace('"url": "'+url+'"','"url": "'+url+'other"')
        self.assertEqual(evidence.packet(page,document(page))['units'],[])

    def test_reciprocal_identity_requires_owner_and_original_author(self):
        page=post_page();doc=document(page);unit=evidence.packet(page,doc)['units'][0]
        ctx=social.scoped_context(page,doc,unit,'Alfa Srl')
        identity={'identity_status':'verified','name':'Alfa Srl','website':OFFICIAL}
        official={'url':OFFICIAL,'checked_at':harness.DATE,'status':200,
                  'html':'<h1>Alfa Srl</h1><a href="'+PROFILE+'">Profilo</a>'}
        self.assertTrue(social.reciprocal(ctx,official,identity)['verified'])
        for context,owner,markup in (
            (ctx,identity,'<h1>Alfa Srl</h1>'),
            ({**ctx,'reposted':True},identity,official['html']),
            (ctx,{**identity,'name':'Beta Srl'},official['html']),
            ({**ctx,'author_profile':None},identity,official['html']),
        ):
            self.assertFalse(social.reciprocal(context,{**official,'html':markup},owner)['verified'])

    def test_unknown_or_foreign_remote_not_made_italian_by_owner_address(self):
        for text in ('Remote US only.','Remote, location to be agreed.','Remoto UK only.'):
            page=post_page(request=REQUEST+' '+text)
            page['html']=page['html'].replace('Remote from Italy.','')
            unit=evidence.packet(page,document(page))['units'][0]
            self.assertFalse(social.scoped_geography(unit,['Veneto'])['allowed'],text)

    def test_social_dossier_shows_attribution_without_borrowing_other_requests(self):
        import subprocess
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const text=fs.readFileSync('static/worklist.js','utf8');
const start=text.indexOf('function agent8SourceContext(');
const end=text.indexOf('\ndocument.addEventListener',start+1);
const esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const ctx={esc,link:(url,label)=>'<a href="'+esc(url)+'">'+esc(label)+'</a>'};
vm.createContext(ctx);vm.runInContext(text.slice(start,end),ctx);
const url='https://instagram.com/p/example/';
const result=ctx.agent8SourceContext({
 social_source:{url,platform:'instagram.com',status:'PUBLIC_POST_READ',original_read:true,
  author_name:'Alfa <script>alert(1)</script>',published_at:'2026-10-19',official_identity_link:{verified:true}},
 facts:[{field:'request',original:true,url,quote:'Cerchiamo freelance <b>frontend</b>'},
        {field:'request',original:true,url:'https://elsewhere.example/',quote:'Other company request'},
        {field:'request',original:false,url,quote:'Snippet only'}]});
assert(result.includes('instagram.com'));
assert(result.includes('Alfa &lt;script&gt;'));
assert(!result.includes('<script>'));
assert(result.includes('Cerchiamo freelance &lt;b&gt;frontend'));
assert(!result.includes('Other company request'));
assert(!result.includes('Snippet only'));
assert(result.includes('collegamento aziendale verificato'));
const unknown=ctx.agent8SourceContext({social_origin:{url,status:'ORIGINAL_UNAVAILABLE',original_read:false}});
assert(unknown.includes('non consultabile'));
assert(unknown.includes('Autore indicato dal post:</strong> Non verificato'));
assert(unknown.includes('Data non verificata'));
assert(!unknown.includes('collegamento aziendale verificato'));
const excluded=ctx.agent8SourceContext({commercial_exclusions:[{code:'large_group',
 quote:'Siamo una multinazionale <script>',url:'https://alfa.example/'}]});
assert(excluded.includes('Fuori dai criteri: Grande gruppo'));
assert(excluded.includes('&lt;script&gt;'));
assert(!excluded.includes('<script>'));
"""
        subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)


class OriginalCycle(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath();self.base.setUp()
        self.store,self.rs=self.base.store,self.base.rs
        self.rs.stop(self.base.c['id']);self.rs.paused(self.base.c['id'])
        filters=copy.deepcopy(self.base.filters)
        filters.update(decision_engine='ai_first_1',commercial_engines=['SOCIAL'])
        filters['deep_plan_token']=api.preview(self.store,filters)['approval_token']
        self.c=self.rs.create(filters);self.worker=AgentCoordinator(self.store,self.c)
        self.worker.initialize()

    def tearDown(self):
        self.base.tearDown()

    def task(self):
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE kind='candidate' ORDER BY id DESC").fetchone()
            return {**dict(row),'payload':json.loads(row['payload'])}

    def test_original_then_reciprocal_owner_preserves_dates_scope_and_contact(self):
        official={'url':OFFICIAL,'checked_at':harness.DATE,'status':200,
                  'html':'<title>Alfa Srl</title><h1>Alfa Srl</h1><p>Partita IVA: 12345678901</p>'
                         '<footer>Sede legale: Via Roma 12, 35100 Padova (PD)</footer>'
                         '<a href="'+PROFILE+'">Il nostro profilo</a>'}
        calls=[]
        def model(payload,cfg,check):
            calls.append(payload)
            out=harness.response(payload)
            if len(calls)==1:
                out.update(decision='NEEDS_RESEARCH',
                           action={'type':'READ_LINK','query':'','link_id':payload['links'][0]['id'],
                                   'question':'Verificare sul sito ufficiale il collegamento al profilo autore.'})
            return {'output':out,'usage':{}}
        identity={'identity_status':'verified','name':'Alfa Srl','website':OFFICIAL,'contacts':[]}
        self.worker.enqueue('candidate','SOCIAL',{'url':POST},'original')
        with patch('sales.agent6.research.CompanyWeb.get',side_effect=lambda url:post_page() if url==POST else official),patch(
                'sales.agent6.research.identity_from',return_value=identity),patch(
                'sales.agent6.ai.infer',side_effect=model):
            self.worker.execute(self.task(),lambda:None)
            self.worker.execute(self.task(),lambda:None)
        self.assertEqual(len(calls),2)
        self.assertFalse(calls[0]['identity']['verified'])
        self.assertTrue(calls[1]['identity']['verified'])
        self.assertTrue(calls[1]['social_source']['official_identity_link']['verified'])
        for p in calls:
            self.assertNotIn(COMMENT,'\n'.join(e['text'] for e in p['evidence']))
            self.assertEqual([d['value'] for d in p['dates']],['2026-10-19'])
        with self.store.connect() as db:
            b=json.loads(db.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
        self.assertEqual(b['decision'],'INTERESTING')
        self.assertEqual(b['url'],POST)
        self.assertTrue(b['social_source']['original_read'])
        self.assertEqual(b['social_source']['author_name'],'Alfa Srl')
        self.assertEqual(b['contacts'][0]['value'],'info@alfa.example')
        self.assertEqual(b['contacts'][0]['attribution'],'verified_social_owner_mailbox')
        self.assertEqual(b['open_paid_project'],'UNKNOWN')

    def test_unisolated_post_is_unverifiable_without_ai(self):
        self.worker.enqueue('candidate','SOCIAL',{'url':POST},'unisolated')
        page=post_page();page['html']=page['html'].split('<script')[0]
        with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No unscoped inference')):
            self.worker.execute(self.task(),lambda:None)
        with self.store.connect() as db:
            b=json.loads(db.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
        self.assertEqual(b['state'],'UNVERIFIABLE')
        self.assertIsNone(b['decision'])
        self.assertTrue(b['social_source']['original_read'])
        self.assertEqual(b['validation_status'],'SOCIAL_SCOPE_UNVERIFIED')
