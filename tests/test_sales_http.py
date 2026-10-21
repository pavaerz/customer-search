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
 def test_company_dossier_corrections_use_existing_security_without_promotion(self):
  from sales.research_store import ResearchStore
  from sales.agent6 import memory
  from test_agent6 import evaluated
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(Path(tmp)/'corrections.db');store.init()
   campaign=ResearchStore(store).create({'agent_version':'6.0','commercial_engines':['AGENCIES'],'commercial':{'ai':{'enabled':True,'provider':'MOCK'}}})
   rid=memory.save_record(store,campaign,'AGENCIES',{**evaluated(),'state':'NEEDS_REVIEW'})
   with patch.object(server,'STORE',store):
    url=f'/api/agent6/records/{rid}/corrections';payload={'changes':{'priority':'high'},'note':'Revisione manuale delle prove.'}
    self.assertEqual(self.request(url,payload,{'X-CSRF-Token':''})[0],403)
    self.assertEqual(self.request(url,payload,{'Origin':'https://untrusted.example'})[0],403)
    self.assertEqual(self.request(url,payload,{'Host':'untrusted.example'})[0],403)
    self.assertEqual(self.request(url,{'changes':{'state':'VERIFIED'},'note':'No'})[0],400)
    self.assertEqual(self.request(url,payload)[0],200)
    code,body=self.request(f'/api/agent6/records/{rid}')
    self.assertEqual(code,200);self.assertEqual(body['state'],'NEEDS_REVIEW')
    self.assertEqual(body['manual_corrections']['priority']['value'],'high')
    self.assertEqual(len(body['company_dossier']['signals']),1)
    code,body=self.request('/api/agent6/worklist?view=review&group=company')
    self.assertEqual(code,200);self.assertEqual(body['count_unit'],'companies')
    self.assertEqual(self.request('/api/agent6/worklist?group=invalid')[0],400)
    with store.connect() as c:
     self.assertEqual(c.execute('SELECT count(*) FROM agent8_annotations').fetchone()[0],1)
     self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
     self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)
 def test_worklist_is_read_only_and_validates_filters_and_host(self):
  with self.store.connect() as c:before=c.execute('SELECT count(*) FROM campaigns').fetchone()[0]
  code,body=self.request('/api/agent6/worklist?view=ready')
  self.assertEqual(code,200);self.assertEqual(body['mode'],'WORKLIST');self.assertIn('counts',body)
  self.assertEqual(self.request('/api/agent6/worklist?view=not_a_view')[0],400)
  self.assertEqual(self.request('/api/agent6/worklist?flow=not_a_flow')[0],400)
  self.assertEqual(self.request('/api/agent6/worklist',headers={'Host':'evil.test'})[0],403)
  with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM campaigns').fetchone()[0],before)
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
 def test_commercial_routes_share_csrf_and_manual_crm(self):
  from sales.research_store import ResearchStore
  from sales.commercial.storage import Opportunities
  from sales.commercial.inspection import inspect
  from test_commercial_engines import page
  rs=ResearchStore(self.store);campaign=rs.create({'commercial_engines':['FREELANCE']})
  try:
   with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:page('Cerchiamo WordPress freelance.',url=url)):
    found=inspect(self.store,{'commercial_engine':'FREELANCE','url':'https://alfa.example/jobs'})
   ident=Opportunities(self.store).save(campaign,found['identity'],found['documents'],found['result']);base='/api/commercial/opportunities/'+str(ident)
   self.assertEqual(self.request('/api/commercial/catalog')[0],200)
   self.assertEqual(self.request(base)[1]['body']['compensation']['amount'],None)
   self.assertEqual(self.request('/api/commercial/opportunities?engine=FREELANCE&state=VERIFIED')[1]['total'],1)
   self.assertEqual(self.request(base+'/action',{'action':'save'},headers={'X-CSRF-Token':'bad'})[0],403)
   code,item=self.request(base+'/action',{'action':'save'});self.assertEqual(code,200);self.assertIsNotNone(item['prospect_id'])
   self.assertEqual(self.request('/api/prospects/'+str(item['prospect_id']))[0],200)
   self.assertEqual(self.request(base+'/action',{'action':'send'})[0],400)
   self.assertEqual(self.request(base+'/action',{'action':'discard'})[0],200)
   self.assertEqual(self.request('/api/commercial/opportunities?engine=FREELANCE')[1]['total'],0)
  finally:rs.stop(campaign['id']);rs.paused(campaign['id'])
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
   self.assertEqual(self.request('/api/campaigns',{'target':50,'filters':{'regions':['Veneto']}})[0],400)
   # Historical data remain readable/resumable, but the public creation route
   # cannot silently launch the retired decision path for a new campaign.
   campaign=ResearchStore(self.store).create({'regions':['Veneto']})
   try:
    self.assertEqual(self.request('/api/campaigns',{})[0],400)
    args=sample();aid=ResearchStore(self.store).save(campaign['id'],campaign['generation'],None,args[0],args[1],qualify(*args))
    code,results=self.request('/api/opportunities?status=qualified&project=website&region=Veneto&limit=1');self.assertEqual(code,200);self.assertEqual(results['total'],1)
    self.assertEqual(self.request('/api/opportunities/'+str(aid))[1]['assessment']['budget'],None)
    self.assertEqual(self.request('/api/opportunities/'+str(aid)+'/review',{'verdict':'confirmed','reason':'Fonte originale verificata'})[0],200)
    self.assertEqual(self.request('/api/campaigns/'+str(campaign['id'])+'/stop',{})[1]['status'],'paused')
    self.assertEqual(self.request('/api/campaigns/'+str(campaign['id'])+'/resume',{})[1]['status'],'running')
   finally:CampaignManager(self.store).stop(campaign['id'])
 def test_new_campaign_uses_only_ai_first_without_launching_worker(self):
  from sales.campaigns import CampaignManager
  with patch.object(CampaignManager,'launch',lambda manager,c:manager.rs.campaign(c['id'])):
   code,campaign=self.request('/api/campaigns',{'filters':{'agent_version':'6.0','commercial_engines':['AGENCIES'],'regions':['Veneto'],'commercial':{'ai':{'enabled':True,'provider':'MOCK'}}}})
   self.assertEqual(code,200)
   try:self.assertEqual(campaign['filters']['decision_engine'],'ai_first_1')
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
