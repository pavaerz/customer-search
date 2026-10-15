import json,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from sales import server
from sales.db import Store,now
from sales.engines import EngineManager
class HttpTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.temp.name)/'test.db');cls.store.init()
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.port=cls.http.server_port;cls.origin='http://127.0.0.1:'+str(cls.port)
  cls.patches=[patch.object(server,'STORE',cls.store),patch.object(server,'MANAGER',EngineManager(cls.store)),patch.object(server,'PORT',cls.port),patch.object(server,'ORIGIN',cls.origin)]
  for p in cls.patches:p.start()
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
  cid=cls.store.company('https://example.org','Test locale')
  sid=cls.store.source({'url':'https://example.org/jobs'},cid);eid=cls.store.add_evidence(cid,sid,'A','request','Annuncio','Cerchiamo WordPress freelance')
  cls.ident=cls.store.prospect(cid,'A','Collaborazione','WordPress',49,{},'Richiesta esplicita','Da verificare',[],[eid])[0]
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.thread.join()
  for p in cls.patches:p.stop()
  cls.temp.cleanup()
 def request(self,path,body=None,headers=None):
  h={'Origin':self.origin,'X-CSRF-Token':server.CSRF,'Content-Type':'application/json'};h.update(headers or {})
  req=Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
  try:
   with urlopen(req) as r:return r.status,json.load(r)
  except HTTPError as e:return e.code,json.load(e)
 def test_state_no_secret(self):
  code,body=self.request('/api/state');self.assertEqual(code,200);self.assertNotIn('TAVILY_API_KEY',json.dumps(body));self.assertIn('csrf',body)
 def test_csrf_and_host(self):
  self.assertEqual(self.request('/api/settings',{},headers={'X-CSRF-Token':'bad'})[0],403)
  self.assertEqual(self.request('/api/state',headers={'Host':'evil.test'})[0],403)
 def test_dismiss_and_restore_routes(self):
  base='/api/prospects/'+str(self.ident)
  code,item=self.request(base+'/dismiss',{});self.assertEqual(code,200);self.assertTrue(item['dismissed_at'])
  try:
   for action in ('update','draft','audit','compose','confirm'):
    self.assertEqual(self.request(base+'/'+action,{})[0],400)
   self.assertTrue(next(i for i in self.request('/api/state')[1]['items'] if i['id']==self.ident)['dismissed_at'])
  finally:
   code,item=self.request(base+'/restore',{});self.assertEqual(code,200);self.assertIsNone(item['dismissed_at'])
 def test_no_auto_send_route(self):self.assertEqual(self.request('/api/send',{})[0],404)
 def test_search_trial_secret_and_authorization(self):
  from sales.search_trial import key_path
  code,body=self.request('/api/search-trial');self.assertEqual(code,200)
  self.assertEqual(self.request('/api/search-trial/start',{})[0],400)
  self.assertEqual(self.request('/api/search-trial/key',{'key':'fixture-private-key'},headers={'X-CSRF-Token':'bad'})[0],403)
  code,body=self.request('/api/search-trial/key',{'key':'fixture-private-key'})
  self.assertEqual(code,200);self.assertTrue(body['configured']);self.assertNotIn('fixture-private-key',json.dumps(body))
  self.assertEqual(self.request('/data/'+key_path(self.store).name)[0],404)
  self.assertEqual(self.request('/api/state')[1]['settings']['provider'],'searxng')
 def test_blocked_compose_and_confirm(self):
  base='/api/prospects/'+str(self.ident)
  self.assertEqual(self.request(base+'/compose',{'recipient':'a@example.org'})[0],400)
  self.assertEqual(self.request(base+'/confirm',{'confirmed':True})[0],400)
 def test_draft_edit_and_manual_compose(self):
  base='/api/prospects/'+str(self.ident)
  self.store.update(self.ident,{'contact_basis':'request'})
  self.assertEqual(self.request(base+'/draft',{})[0],200)
  code,body=self.request(base+'/compose',{'recipient':'a@example.org','confirmed':True});self.assertEqual(code,200);self.assertTrue(body['url'].startswith('https://mail.google.com/'))
  self.assertEqual(self.store.detail(self.ident)['stage'],'review')
 def test_no_backup_or_secret_download(self):
  self.assertEqual(self.request('/.env')[0],404);self.assertEqual(self.request('/data/sales.sqlite3')[0],404)
 def test_campaign_lifecycle_and_filters(self):
  from sales.campaigns import CampaignManager
  from sales.research_store import ResearchStore
  from sales.research_rules import qualify
  from test_research import sample
  with patch.object(CampaignManager,'launch',lambda manager,c:manager.rs.campaign(c['id'])):
   self.assertEqual(self.request('/api/campaigns',{'target':51})[0],400)
   code,campaign=self.request('/api/campaigns',{'target':50,'filters':{'regions':['Veneto']}});self.assertEqual(code,200)
   try:
    self.assertEqual(self.request('/api/campaigns',{})[0],400)
    args=sample();aid=ResearchStore(self.store).save(campaign['id'],campaign['generation'],None,args[0],args[1],qualify(*args))
    code,results=self.request('/api/opportunities?status=qualified&project=website&region=Veneto&limit=1');self.assertEqual(code,200);self.assertEqual(results['total'],1)
    self.assertEqual(self.request('/api/opportunities/'+str(aid))[1]['assessment']['budget'],None)
    self.assertEqual(self.request('/api/opportunities/'+str(aid)+'/review',{'verdict':'confirmed','reason':'Fonte originale verificata'})[0],200)
    self.assertEqual(self.request('/api/campaigns/'+str(campaign['id'])+'/stop',{})[1]['status'],'paused')
    self.assertEqual(self.request('/api/campaigns/'+str(campaign['id'])+'/resume',{})[1]['status'],'running')
   finally:CampaignManager(self.store).stop(campaign['id'])
 def test_cloud_model_setting_rejected(self):
  self.assertEqual(self.request('/api/settings',{'ollama_model':'some-model:cloud'})[0],400)
 def test_grant_profile_and_answer_protections(self):
  self.assertEqual(self.request('/api/grants/profile',{'activity':'Siti web'},headers={'X-CSRF-Token':'bad'})[0],403)
  code,p=self.request('/api/grants/profile',{'activity':'Siti web','tax_regime':'forfettario'});self.assertEqual(code,200)
  self.assertEqual(self.request('/api/grants/profile')[1]['profile']['tax_regime'],'forfettario')
  self.assertEqual(self.request('/api/grants/answers',{'answers':{'f'*64:'yes'}})[0],400)
  self.assertEqual(self.request('/api/grants/profile',{'facts':[]})[0],400)

if __name__=='__main__':unittest.main()
