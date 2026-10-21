"""Public-post lifecycle with synthetic sources; no external calls or real leads."""
import copy,html,json,unittest
from unittest.mock import patch
import test_agent6_campaign32 as support
from sales.agent6 import schema,social,passages
from sales.agent6.api import preview
from sales.agent6.worklist import listing
from sales.commercial.coordinator import run_campaign
from sales.agent6.coordinator import document

POST='https://mastodon.social/@alfa/123456'
PROFILE='https://mastodon.social/@alfa'
OFFICIAL='https://alfa.example/'
REQUEST='We are looking for a freelance WordPress developer to build our complete website. Remote from Italy.'
STAMP='2026-10-19T12:00:00+00:00'


class SocialCycle(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp();self.store=self.base.store;self.rs=self.base.rs
        self.rs.stop(self.base.c['id']);self.rs.paused(self.base.c['id'])
        f=copy.deepcopy(self.base.filters);f['commercial_engines']=['SOCIAL'];f['work_budget']['max_reads']=6
        f['deep_plan_token']=preview(self.store,f)['approval_token'];self.c=self.rs.create(f)
        self.post=POST;self.reads=[];self.calls=[];self.searches=[]
        self.metadata={'@context':'https://schema.org','@type':'SocialMediaPosting','author':{'@type':'Organization','name':'Alfa Srl','url':PROFILE},'articleBody':REQUEST,'datePublished':'2026-10-18'}
        self.comment='Comment by Beta Srl: no freelancers. Budget: €100 for minor CSS fixes.'
        self.official_html='<title>Alfa Srl</title><h1>Alfa Srl</h1><p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">Contatti</a><a href="'+PROFILE+'">Il nostro profilo</a>'
    def tearDown(self):self.base.tearDown()
    def post_page(self):
        return {'url':self.post,'status':200,'checked_at':STAMP,'html':'<title>Alfa Srl</title><h1>Alfa Srl</h1><p>'+REQUEST+'</p><a href="'+OFFICIAL+'">Sito ufficiale</a><p>'+html.escape(self.comment)+'</p><script type="application/ld+json">'+json.dumps(self.metadata)+'</script>'}
    def model(self,p,cfg,check):
        self.calls.append(p)
        if p['task']==schema.PLAN:
            q=support.query('site:'+social.platform(self.post)+' cerchiamo freelance WordPress Italia')
            return {'output':{'decision':'search' if not p['round'] else 'stop','reason':'Synthetic public-post strategy','queries':[q] if not p['round'] else []},'usage':{}}
        analyses=[]
        for rid in p['result_ids']:
            segments=[s for e in p['evidence'] if e['result_id']==rid for s in e['segments']]
            fields={'entity':'Alfa Srl','request':REQUEST.split(' Remote')[0]}
            if p['task']==schema.READ:fields.update(technical='WordPress developer',contract='freelance',geography='Remote from Italy.')
            facts=[]
            for field,value in fields.items():
                seg=next((s for s in segments if (s['text']==value if field=='entity' else value in s['text'])),None)
                if seg:facts.append({'field':field,'ref':{'segment_id':seg['segment_id']}})
            analyses.append({'result_id':rid,'kind':'BUYER_DEMAND','kind_ref':facts[-1]['ref'] if facts else None,'facts':facts,'hypothesis':'Synthetic request, attribution must be verified.','missing':[]})
        return {'output':{'analyses':analyses},'usage':{}}
    def run_case(self):
        def search(store,p,check):
            self.searches.append(p)
            url=OFFICIAL if p.get('selection')=='verification' else self.post
            return [{'url':url,'title':'Alfa Srl','content':REQUEST}]
        def read(url):
            self.reads.append(url)
            if url==self.post:return self.post_page()
            if url==OFFICIAL:return {'url':url,'status':200,'checked_at':STAMP,'html':self.official_html}
            raise AssertionError('Unexpected URL '+url)
        with patch('socket.create_connection',side_effect=AssertionError('No network')),patch('sales.agent6.ai.infer',side_effect=self.model),patch('sales.agent6.coordinator.acquire',side_effect=search),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=read):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:return [json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(self.c['id'],))]
    def test_original_post_and_reciprocal_company_link_complete_verification(self):
        records=self.run_case();ready=[b for b in records if b['state']=='VERIFIED']
        self.assertEqual(len(ready),1,[(b['url'],b['state'],b['reason']) for b in records])
        b=ready[0];self.assertTrue(b['identity_verified']);self.assertEqual(b['official_domain'],OFFICIAL)
        self.assertTrue(b['social_source']['official_identity_link']['verified'])
        self.assertEqual(b['budget']['kind'],'UNKNOWN');self.assertEqual(b['freshness']['published_at'],'2026-10-18')
        self.assertTrue(any(f['field']=='request' and f['url']==POST and f['original'] for f in b['facts']))
        self.assertEqual(listing(self.store,{'view':'ready','group':'company'})['total'],1)
        self.assertFalse(any('no freelancers' in e['text'] for p in self.calls for e in p.get('evidence',[])))
    def test_no_reciprocal_reference_does_not_attribute_post_to_company(self):
        self.official_html=self.official_html.replace('<a href="'+PROFILE+'">Il nostro profilo</a>','')
        records=self.run_case();self.assertFalse(any(b['state'] in ('VERIFIED','POTENTIAL') for b in records))
        self.assertTrue(any(b.get('social_source',{}).get('official_identity_link',{}).get('reason')=='official_reference_missing' for b in records))
    def test_repost_is_not_company_demand(self):
        self.metadata['sharedContent']={'url':'https://bsky.app/profile/other/post/123'}
        records=self.run_case();self.assertFalse(any(b['state'] in ('VERIFIED','POTENTIAL') for b in records))
        self.assertTrue(any(b.get('social_source',{}).get('reposted') for b in records))
    def test_old_post_cannot_borrow_official_page_freshness(self):
        self.metadata['datePublished']='2020-10-18'
        records=self.run_case();self.assertFalse(any(b['state'] in ('VERIFIED','POTENTIAL') for b in records))
        self.assertTrue(any('stale_request' in b.get('counterevidence',[]) for b in records))
    def test_indexed_instagram_is_not_read_or_promoted(self):
        self.post='https://www.instagram.com/p/example/'
        records=self.run_case();self.assertNotIn(self.post,self.reads)
        self.assertFalse(any(b['state'] in ('VERIFIED','POTENTIAL') for b in records))
        self.assertTrue(any(b.get('social_source',{}).get('status')=='INDEXED_ONLY_ACCESS_POLICY' for b in records))
    def test_comment_and_ambiguous_body_do_not_supply_request_scope(self):
        page=self.post_page();doc=document(page);scope=social.content_scope(page,doc)
        self.assertEqual(scope['analysis_text'],REQUEST)
        proof=passages.bundle([{'id':'r1','original':True,**doc,**scope}])
        self.assertTrue(proof);self.assertNotIn(self.comment,'\n'.join(e['text'] for e in proof))
        page['html']+='<p>'+REQUEST+'</p>'
        self.assertIsNone(social.content_scope(page,document(page)))
    def test_ambiguous_post_stays_review_without_ai_reading_other_authors(self):
        self.metadata.pop('articleBody')
        records=self.run_case()
        self.assertFalse(any(b['state'] in ('VERIFIED','POTENTIAL') for b in records))
        self.assertTrue(any(b.get('social_source',{}).get('status')=='PUBLIC_POST_AUTHOR_OR_SCOPE_UNVERIFIED' for b in records))
        self.assertFalse(any(e['url']==POST and e['original'] for p in self.calls for e in p.get('evidence',[])))
    def test_login_at_original_url_is_not_a_read_post(self):
        with patch.object(self,'post_page',return_value={'url':POST,'status':200,'checked_at':STAMP,
                'html':'<title>Log in</title><form><input type="password"></form>'}):
            records=self.run_case()
        self.assertFalse(any(b['state'] in ('VERIFIED','POTENTIAL') for b in records))
        self.assertTrue(any(b.get('social_source',{}).get('status')=='ORIGINAL_UNAVAILABLE' for b in records))
        self.assertFalse(any(b['original'] and b['url']==POST for b in records))
    def test_platform_query_does_not_authorize_arbitrary_sites_or_profiles(self):
        for q in ('site:evil.example cerco WordPress','site:mastodon.social@evil.example cerco WordPress','site:mastodon.social site:bsky.app cerco WordPress'):
            self.assertFalse(social.query_policy({'query':q})['allowed'])
        self.assertTrue(social.query_policy({'query':'site:bsky.app cerco freelance WordPress Italia'})['allowed'])
        self.assertFalse(social.post_url(PROFILE));self.assertFalse(social.post_url('https://evil.example/@alfa/123'))


if __name__=='__main__':unittest.main()
