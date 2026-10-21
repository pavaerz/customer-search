"""Historical redirect replay and synthetic dedup/CRM tests, entirely offline."""
import gzip,json,unittest,copy
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import site_identity,memory,api,qualification
from sales.agent6.coordinator import AgentCoordinator
from sales.providers import PublicWeb
import test_agent8_proactive as support
import test_agent6_campaign32 as base_support


class Redirects(unittest.TestCase):
    def test_offline_discovery_audit_qualification_to_crm(self):
        base=support.ProactiveCycle();base.setUp();self.addCleanup(base.tearDown)
        body=base.run_case()
        self.assertEqual(body['state'],'POTENTIAL')
        self.assertEqual(body['commercial_dimensions']['buying_intent']['value'],'UNKNOWN')
        self.assertIsNone(body['project_value']['amount'])
        with base.store.connect() as c:
            rid=c.execute("select id from agent6_records where campaign_id=? and state='POTENTIAL'",(base.c['id'],)).fetchone()[0]
        saved=api.save_contact(base.store,rid)
        self.assertIsInstance(saved['prospect_id'],int)
        self.assertTrue(body['website_audit']['major_evidence_ids'])
        self.assertTrue(body['documents'])

    def test_saved_campaign38_redirects_keep_real_pages(self):
        cases=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/agent9/redirects38.json.gz').read_bytes()))
        for case in cases:
            pages,identity,relation=site_identity.resolve(case['pages'],case['requested'])
            self.assertTrue(pages);self.assertTrue(relation['cross_domain'])
            self.assertTrue(relation['final_domain'].endswith('.com'))
            self.assertFalse(relation['chain_recorded']) # historical client did not save hops
            if 'quid' in case['requested']:self.assertTrue(relation['relationship_verified'])
            else:self.assertFalse(relation['relationship_verified']) # incomplete identity is not fabricated

    def test_unrelated_redirect_not_trusted_despite_verified_final_identity(self):
        page={**support.pages()[support.ROOT],'requested_url':'https://unrelated.it/'}
        pages,identity,relation=site_identity.resolve([page],page['requested_url'])
        self.assertTrue(pages);self.assertEqual(identity['identity_status'],'verified')
        self.assertFalse(relation['relationship_verified'])

    def test_protected_transport_records_each_hop_and_checks_each_destination(self):
        from unittest.mock import MagicMock
        first=MagicMock(status=302);first.getheader.side_effect=lambda key,default='':'http://alfa.com/' if key=='Location' else default
        final=MagicMock(status=200);final.getheader.side_effect=lambda key,default='':'text/html' if key=='Content-Type' else default
        final.read.side_effect=[b'<html',b'>Hello</html>']
        connections=[MagicMock(),MagicMock()]
        for c,r in zip(connections,[first,final]):c.getresponse.return_value=r
        web=PublicWeb(None);checked=[]
        with patch.object(web,'policy',side_effect=checked.append),patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('93.184.216.34',80))]),patch('sales.providers.socket.create_connection',return_value=MagicMock()),patch('sales.providers.http.client.HTTPConnection',side_effect=connections):
            result=web._raw('http://alfa.it/')
        self.assertEqual(checked,['http://alfa.it/','http://alfa.com/'])
        self.assertEqual(result['redirect_chain'],[{'url':'http://alfa.it/','location':'http://alfa.com/','status':302}])
        self.assertEqual(result['acquisition_requested_url'],'http://alfa.it/')

    def test_original_to_canonical_reaches_one_crm_contact_preserving_trace(self):
        base=support.ProactiveCycle();base.setUp();self.addCleanup(base.tearDown)
        requested='https://alfa.it/';root='https://alfa.com/'
        pages={k.replace(support.ROOT,root):{**p,'url':p['url'].replace(support.ROOT,root),
            'html':p['html'].replace(support.ROOT,root).replace('info@alfa.example','info@alfa.com')} for k,p in base.pages.items()}
        pages[requested]={**pages[root],'redirect_chain':[{'url':requested,'status':301,'location':root}]}
        pending=qualification.evaluate({'url':requested,'text':'','original':False},None,[],'AZIENDE')
        discovery_id=memory.save_record(base.store,base.c,'AZIENDE',pending)
        # A row from another campaign must remain unchanged.
        historical_id=memory.save_record(base.store,base.c,'AZIENDE',{**pending,'url':'https://unrelated.example/'})
        base.rs.enqueue(base.c['id'],'candidate','AZIENDE',{'url':requested,'query':'fixture','proactive':True},'redirect-test')
        w=AgentCoordinator(base.store,base.c);w.initialize();task=base.rs.claim(base.c['id'],base.c['generation'])
        model=base.model
        with patch('socket.create_connection',side_effect=AssertionError('Offline only')),patch('sales.agent6.ai.infer',side_effect=model),patch('sales.agent6.proactive.CompanyWeb.get',side_effect=lambda url:pages[url]),patch('sales.commercial.browser.review',side_effect=lambda store,p,*a,**kw:{**support.browser(p),'findings':[{'code':'mobile_content','severity':'major','url':root,'viewport':390,'quote':'Synthetic measured overflow.'}]}):
            w.execute(task,lambda:None)
        with base.store.connect() as c:
            rows=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('select * from agent6_records')]
        final=next(r for r in rows if r['body'].get('website_audit'))
        self.assertEqual(final['state'],'POTENTIAL',final['body']['reason'])
        alias=next(r for r in rows if r['id']==discovery_id)
        self.assertEqual(alias['body']['canonical_record_id'],final['id'])
        self.assertEqual(alias['body']['workflow_state'],'CANONICAL_LINKED')
        self.assertEqual(api.save_contact(base.store,final['id'])['prospect_id'],api.save_contact(base.store,final['id'])['prospect_id'])
        count=api.listing(base.store,{'campaign':str(base.c['id'])})['total']
        self.assertEqual(count,2) # canonical company + unrelated untouched trace
        self.assertEqual(memory.save_record(base.store,base.c,'AGENCIES',pending),final['id'])
        with base.store.connect() as c:
            self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],1)
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')
            self.assertEqual(json.loads(c.execute('select body from agent6_records where id=?',(historical_id,)).fetchone()[0])['url'],'https://unrelated.example/')
