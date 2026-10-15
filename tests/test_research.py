import copy,json,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now,digest
from sales.research_rules import qualify,validate_signals,region_of
from sales.research_store import ResearchStore,migrate
from sales.research_analysis import schema_check,PROPOSAL_SCHEMA,select_pages,correlated_documents
from sales.research_api import quality_report
from sales.campaigns import CampaignManager


def sample():
    identity={'name':'Laboratorio Alfa Srl','website':'https://alfa.example/','legal_id':'IT12345678901','region':'Veneto','identity_status':'verified','group':'direct','contacts':[{'type':'email','value':'info@alfa.example','url':'https://alfa.example/contatti','basis':'Pagina ufficiale','checked_at':now()}]}
    texts=['Cerchiamo un fornitore per il rifacimento completo del nostro sito aziendale. La richiesta di offerta è attualmente aperta.','I prodotti vengono distribuiti dal laboratorio ai rivenditori autorizzati.']
    docs=[{'id':digest(t),'content_hash':digest(t),'url':'https://alfa.example/'+str(i),'text':t,'title':'Alfa','published_at':now()[:10],'checked_at':now(),'official':True,'status':200} for i,t in enumerate(texts)]
    signals,_=validate_signals([{'document_id':docs[0]['id'],'kind':'request','quote':texts[0]}],docs)
    ids=[s['id'] for s in signals]
    proposal={'project':'website','why':'Richiesta documentata di rifacimento completo.','why_now':'Richiesta attuale.','proposal':'Sito aziendale completo','scope':'full_project','feasibility':'bounded','critical_unknowns':[],'objections':[],'support_ids':ids,'checked_sections':['identity','offer','contact','solutions']}
    review={'status':'supported','support_ids':ids,'existing_solution_checked':True,'small_fix_sufficient':False}
    return identity,docs,signals,proposal,review

class QualificationTest(unittest.TestCase):
    def evaluate(self,mutate=None):
        args=sample()
        if mutate:mutate(*args)
        return qualify(*args)
    def test_explicit_request_all_gates(self):
        a=self.evaluate();self.assertEqual(a['status'],'qualified');self.assertEqual(a['score'],85);self.assertIsNone(a['budget']);self.assertEqual(a['score_detail']['Compatibilità economica documentata']['points'],0)
    def test_identity_missing(self):self.assertEqual(self.evaluate(lambda i,*_:i.update(identity_status='unknown'))['status'],'unverifiable')
    def test_unknown_geography(self):self.assertNotEqual(self.evaluate(lambda i,*_:i.update(region=None))['status'],'qualified')
    def test_unknown_budget_never_internal_floor(self):self.assertIsNone(self.evaluate()['budget'])
    def test_small_fix(self):self.assertNotEqual(self.evaluate(lambda i,d,s,p,v:v.update(small_fix_sufficient=True))['status'],'qualified')
    def test_existing_solution_unknown(self):self.assertNotEqual(self.evaluate(lambda i,d,s,p,v:v.update(existing_solution_checked=False))['status'],'qualified')
    def test_critical_webapp(self):
        def change(i,d,s,p,v):p.update(project='webapp',critical_unknowns=['Integrazione ERP e ruoli di accesso da chiarire'])
        self.assertNotEqual(self.evaluate(change)['status'],'qualified')
    def test_missing_contact(self):self.assertNotEqual(self.evaluate(lambda i,*_:i.update(contacts=[]))['status'],'qualified')
    def test_incomplete_check(self):
        self.assertEqual(qualify(*sample(),limits=['Pagina shop non accessibile'])['status'],'unverifiable')
    def test_generic_and_employee_requests(self):
        for quote in ['Cerchiamo sviluppatore WordPress freelance per collaborazioni future.','Cerchiamo un dipendente a tempo indeterminato per un nuovo sito aziendale.']:
            args=sample();args[2][0]['quote']=quote
            self.assertNotEqual(qualify(*args)['status'],'qualified')
    def test_relocation_slow_old_site_not_enough(self):
        for kind,quote in [('event','Abbiamo aperto una nuova sede a Padova.'),('gap','Il sito ha un punteggio Lighthouse di 30/100.'),('gap','Il design del sito risale al 2010 ed è vecchio.')]:
            args=sample();args[2][0].update(kind=kind,quote=quote)
            self.assertNotEqual(qualify(*args)['status'],'qualified')
    def test_future_and_old_dates(self):
        for date in ['2030-01-01','2000-01-01',None]:
            args=sample();args[2][0]['published_at']=date
            self.assertNotEqual(qualify(*args)['status'],'qualified')
    def test_completed_contradiction(self):
        args=sample();args[2].append({**args[2][0],'id':'counter','kind':'counterevidence','event_key':'counter','quote':'Il fornitore già selezionato ha concluso il progetto.'})
        self.assertNotEqual(qualify(*args)['status'],'qualified')
    def test_fabricated_quote_or_id_rejected(self):
        _,docs,*_=sample()
        signals,invalid=validate_signals([{'document_id':docs[0]['id'],'kind':'gap','quote':'Non abbiamo alcun sito web e vogliamo comprarlo.'},{'document_id':'inventato','kind':'event','quote':docs[0]['text']}],docs)
        self.assertEqual(signals,[]);self.assertEqual(len(invalid),2)
    def test_republication_not_independent(self):
        _,docs,*_=sample();docs.append({**docs[0],'id':'mirror','url':'https://news.example/reprint','official':False})
        signals,invalid=validate_signals([{'document_id':d['id'],'kind':'event','quote':docs[0]['text']} for d in [docs[0],docs[2]]],docs)
        self.assertEqual(len(signals),1);self.assertEqual(invalid,[])
    def test_budget_wrong_subject_or_low(self):
        for quote,expected in [('Il budget del nostro cliente finale è di 10000 euro.',None),('Il budget del progetto è di 500 euro.',500),('Budget per il progetto: €500.',500),('Il budget va da 500 a 5000 euro.',500)]:
            args=sample();sig={**args[2][0],'id':'budget','kind':'budget','quote':quote,'event_key':'budget'};args[2].append(sig);args[3]['budget_signal_id']='budget'
            result=qualify(*args);self.assertEqual(result['budget'],expected)
            if expected:self.assertEqual(result['status'],'rejected')
    def test_schema_forbids_additional_fields(self):
        self.assertFalse(schema_check({'project':'website','send_email':True},PROPOSAL_SCHEMA))
    def test_geography(self):
        self.assertEqual(region_of('Via Roma 12, 35100 Padova'),'Veneto');self.assertIsNone(region_of('Via Firenze 1, 80100 Napoli')) # street name is not a region
    def test_pages_prioritize_contact_over_products(self):
        links=['https://alfa.example/prodotti/'+str(i) for i in range(80)]+['https://alfa.example/contatti','https://alfa.example/shop','https://alfa.example/chi-siamo']
        chosen=select_pages(links);self.assertIn(links[-3],chosen);self.assertIn(links[-2],chosen);self.assertLess(len(chosen),20)

class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'sales.sqlite3');self.store.init();self.rs=ResearchStore(self.store);self.c=self.rs.create();self.args=sample()
    def tearDown(self):self.tmp.cleanup()
    def save(self,args=None):
        args=args or self.args
        return self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],qualify(*args))
    def test_migration_repeat_preserves_rows(self):
        self.save()
        with self.store.connect() as c:before=[tuple(r) for r in c.execute('SELECT * FROM prospects')]
        migrate(self.store);migrate(self.store)
        with self.store.connect() as c:self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM prospects')]);self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_one_company_not_one_signal(self):
        self.save();args=sample();args[1][1]['id']='different';self.save(args)
        self.assertEqual(self.rs.campaign()['qualified'],1)
    def test_crm_bridge_drafts_and_manual_category(self):
        ident=self.save();opp=self.rs.opportunity(ident);self.assertTrue(opp['company_id'])
        from sales.intelligence import communication
        item=self.store.company_list()[0];self.assertIn('Fonte:',communication(item,self.store.settings())['email'])
        self.store.classify_contact(item['company_id'],'agencies','Correzione manuale',manual=True)
        self.assertEqual(self.rs.opportunities({'group':'agencies'})['total'],1)
    def test_stop_refuses_late_promotion(self):
        self.rs.stop(self.c['id']);self.assertIsNone(self.save());self.assertEqual(self.rs.campaign()['qualified'],0)
    def test_new_campaign_can_complete_prior_technical_or_partial_review(self):
        for status in ('unverifiable','needs_review'):
            with self.subTest(previous=status):
                args=sample()
                args[0]['website']='https://'+status+'.example/'
                args[0]['legal_id']='IT'+('11111111111' if status=='unverifiable' else '22222222222')
                partial=copy.deepcopy(args);partial[3]['checked_sections'].remove('solutions')
                old=qualify(*args,limits=['Shop non accessibile']) if status=='unverifiable' else qualify(*partial)
                self.assertEqual(old['status'],status)
                first=self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],old)
                self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create()
                second=self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],qualify(*args))
                self.assertEqual(self.rs.opportunity(first)['assessment']['status'],status)
                self.assertEqual(self.rs.opportunity(second)['assessment']['status'],'qualified')
    def test_resume_requeues_only_unfinished(self):
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://alfa.example/'},'one');task=self.rs.claim(self.c['id'],self.c['generation'])
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);fresh=self.rs.resume(self.c['id']);self.assertNotEqual(fresh['generation'],self.c['generation'])
        self.assertEqual(self.rs.claim(fresh['id'],fresh['generation'])['id'],task['id']);self.assertFalse(self.rs.enqueue(fresh['id'],'candidate','change',{},'one'))
    def test_one_campaign_only(self):
        with self.assertRaises(ValueError):self.rs.create()
    def test_contact_and_deletion_suppression(self):
        ident=self.save();item=self.store.company_list()[0];self.store.set_dismissed(item['id'],True)
        self.assertTrue(self.rs.suppressed(self.args[0]));self.assertEqual(self.rs.opportunities({'status':'qualified'})['total'],0)
        self.store.set_dismissed(item['id'],False);self.store.update_company(item['id'],{'stage':'contacted'})
        self.assertTrue(self.rs.suppressed(self.args[0]));self.assertEqual(self.rs.opportunities({'stage':'contacted'})['total'],1)
    def test_homonymous_different_legal_identity(self):
        first=self.rs.entity(self.args[0]);other={**self.args[0],'website':'https://another.example','legal_id':'IT55555555555'}
        self.assertNotEqual(first,self.rs.entity(other))
    def test_unknown_identity_becomes_verified_without_duplicate(self):
        unverified={**self.args[0],'identity_status':'unknown','legal_id':None}
        first=self.rs.entity(unverified)
        self.assertEqual(first,self.rs.entity(self.args[0]))
        other={**self.args[0],'website':'https://another.example'}
        self.assertEqual(first,self.rs.entity(other))
    def test_failed_fetch_does_not_erase_verified_identity(self):
        eid=self.rs.entity(self.args[0]);self.rs.entity({'name':'https://alfa.example/','website':'https://alfa.example/','identity_status':'unknown','contacts':[]})
        with self.store.connect() as c:r=c.execute('SELECT * FROM research_entities WHERE id=?',(eid,)).fetchone()
        self.assertEqual(r['name'],self.args[0]['name']);self.assertEqual(r['identity_status'],'verified')
    def test_reconciliation_retains_assessment_ids(self):
        from sales.research_store import reconcile_entities
        aid=self.save()
        with self.store.connect() as c:
            eid=c.execute("INSERT INTO research_entities(identity_key,name,website,identity_status,details,created_at,updated_at) VALUES ('domain:alfa.example','Provvisoria','https://alfa.example/','unknown','{}',?,?)",(now(),now())).lastrowid
            second=c.execute("INSERT INTO research_assessments(campaign_id,entity_id,status,score,body,evidence_fingerprint,created_at) VALUES (?,?,'unverifiable',0,'{}','provisional',?)",(self.c['id'],eid,now())).lastrowid
        self.assertEqual(reconcile_entities(self.store),1)
        with self.store.connect() as c:
            self.assertEqual({r[0] for r in c.execute('SELECT id FROM research_assessments')},{aid,second})
            self.assertEqual(c.execute('SELECT count(DISTINCT entity_id) FROM research_assessments').fetchone()[0],1)
    def test_same_legal_identity_different_domain(self):
        first=self.rs.entity(self.args[0]);other={**self.args[0],'website':'https://another.example'}
        self.assertEqual(first,self.rs.entity(other))
    def test_correlated_documents_use_verified_identity(self):
        self.save();docs=correlated_documents(self.store,self.args[0],[]);self.assertEqual(len(docs),1)
        other={**self.args[0],'website':'https://another.example','legal_id':'IT55555555555'}
        self.assertEqual(correlated_documents(self.store,other,[]),[])
    def test_quality_denominator_only_proposed(self):
        aid=self.save();self.rs.review(aid,'confirmed','Richiesta verificata nelle fonti')
        args=sample();args[0].update(website='https://other.example',legal_id='IT55555555555');args[3]['scope']='unknown';bid=self.save(args);self.rs.review(bid,'confirmed','Scarto corretto nelle fonti')
        report=quality_report(self.store);self.assertEqual(report['confirmed'],1);self.assertEqual(report['reviewed'],2);self.assertFalse(report['sufficient'])
    def test_same_signal_not_reproposed(self):
        first_campaign=self.c['id'];self.save();self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create();self.save()
        self.assertEqual(self.rs.campaign()['qualified'],0)
        self.assertEqual(self.rs.opportunities({'status':'qualified','campaign':first_campaign})['total'],1)
        self.assertEqual(self.rs.opportunities({'status':'qualified','campaign':self.c['id']})['total'],0)
        self.assertEqual(self.rs.opportunities({'status':'qualified'})['total'],1)
    def test_stop_owned_worker_under_five_seconds(self):
        import subprocess,sys
        worker=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
        manager=CampaignManager(self.store);manager._workers[manager.key]=worker
        try:
            before=time.monotonic();result=manager.stop(self.c['id']);self.assertLess(time.monotonic()-before,5);self.assertEqual(result['status'],'paused');self.assertIsNotNone(worker.poll())
        finally:
            if worker.poll() is None:worker.kill()
            worker.wait();manager._workers.pop(manager.key,None)

class OwnedChildrenTest(unittest.TestCase):
 def test_stop_also_kills_child_ignoring_term(self):
  import os,subprocess,sys
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(Path(tmp)/'db.sqlite3');store.init();campaign=ResearchStore(store).create();pidfile=Path(tmp)/'child.pid'
   child_code='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'
   parent_code='import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,"-c",sys.argv[2]]);Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)'
   worker=subprocess.Popen([sys.executable,'-c',parent_code,str(pidfile),child_code],start_new_session=True)
   manager=CampaignManager(store);manager._workers[manager.key]=worker
   try:
    for _ in range(40):
     if pidfile.exists():break
     time.sleep(.05)
    self.assertTrue(pidfile.exists());child=int(pidfile.read_text());time.sleep(.1)
    manager.stop(campaign['id']);time.sleep(.1)
    state=subprocess.run(['ps','-p',str(child),'-o','stat='],capture_output=True,text=True).stdout.strip()
    self.assertTrue(not state or state.startswith('Z'),state)
   finally:
    try:os.killpg(worker.pid,9)
    except ProcessLookupError:pass
    worker.wait();manager._workers.pop(manager.key,None)

if __name__=='__main__':unittest.main()
