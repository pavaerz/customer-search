"""Manual social review is append-only, evidence-bound and offline."""
import json
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.storage import migrate
from sales.commercial.social import inspect_social

class SocialReview31Tests(CommercialTestCase):
    def social(self,official=False):
        if official:
            found=self.inspect(page('Cerchiamo sviluppatore WordPress freelance.'))
            found['result']['social']={'source':'instagram','post_url':'https://instagram.com/p/test/','accessibility':'unavailable'}
            found['result']['state']='UNVERIFIABLE'
            for doc in found['documents']:doc['official']=True
        else:
            with patch('sales.commercial.social.PublicSocialWeb.get',side_effect=ValueError('robots: accesso vietato')):
                found=inspect_social(self.store,{'url':'https://instagram.com/p/test/','social':'instagram','commercial_engine':'FREELANCE','title':'Cerchiamo sviluppatore freelance'})
        return self.repo.save(self.c,found['identity'],found['documents'],found['result'])
    def test_reviews_append_without_changing_qualification_or_history(self):
        ident=self.social();before=self.repo.get(ident)
        for status in ('interesting','unavailable','inactive','irrelevant'):
            self.repo.social_review(ident,{'status':status,'notes':'Esame manuale sintetico; attualità sconosciuta.'})
        item=self.repo.get(ident)
        self.assertEqual(item['body'],before['body']);self.assertEqual(item['revisions'],before['revisions'])
        self.assertEqual(item['state'],'UNVERIFIABLE');self.assertIsNone(item['prospect_id'])
        self.assertEqual(len(item['social_reviews']),4);self.assertEqual(item['social_review']['status'],'irrelevant')
        self.assertEqual(self.repo.listing()['items'][0]['social_review']['status'],'irrelevant')
    def test_manual_text_cannot_verify_identity_or_promote(self):
        ident=self.social()
        for state in ('identified','official_confirmed','VERIFIED'):
            with self.assertRaises(ValueError):self.repo.social_review(ident,{'status':state,'notes':'Conosco questa impresa'})
        self.assertEqual(self.repo.get(ident)['state'],'UNVERIFIABLE')
    def test_official_confirmation_requires_stored_request_proof(self):
        ident=self.social(official=True);item=self.repo.get(ident)
        self.repo.social_review(ident,{'status':'identified','notes':'Identità presente nelle prove'})
        for ids in ([],['invented-document']):
            with self.assertRaises(ValueError):self.repo.social_review(ident,{'status':'official_confirmed','notes':'Richiesta ufficiale','evidence_ids':ids})
        result=self.repo.social_review(ident,{'status':'official_confirmed','notes':'Richiesta nel documento acquisito, non garantisce che sia ancora attiva','evidence_ids':[d['id'] for d in item['documents']]})
        self.assertEqual(result['social_review']['status'],'official_confirmed');self.assertEqual(result['state'],'UNVERIFIABLE')
    def test_invalid_or_unrelated_review_is_rejected(self):
        ident=self.social()
        for request in ({'status':[],'notes':'test'},{'status':{},'notes':'test'},{'status':'interesting','notes':''},{'status':'interesting','notes':'a'*4001},{'status':'interesting','notes':2},{'status':'interesting','notes':'a','evidence_ids':'x'}):
            with self.assertRaises(ValueError):self.repo.social_review(ident,request)
        found=self.inspect(page('Cerchiamo sviluppatore WordPress freelance.'))
        other=self.repo.save(self.c,found['identity'],found['documents'],found['result'])
        with self.assertRaises(ValueError):self.repo.social_review(other,{'status':'interesting','notes':'non social'})
    def test_migration_repeatable_and_data_preserved(self):
        ident=self.social();before=self.repo.get(ident)
        for _ in range(2):migrate(self.store)
        self.assertEqual(self.repo.get(ident),before)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM research_schema WHERE version=62').fetchone()[0],1)
    def test_review_api_preserves_http_protections(self):
        import threading
        from contextlib import ExitStack
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from sales import server
        ident=self.social();http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        origin='http://127.0.0.1:'+str(http.server_port)
        with ExitStack() as stack:
            for p in (patch.object(server,'STORE',self.store),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin)):stack.enter_context(p)
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                def request(headers=None,status='interesting'):
                    h={'Origin':origin,'X-CSRF-Token':server.CSRF,'Content-Type':'application/json',**(headers or {})}
                    req=Request(origin+'/api/commercial/opportunities/'+str(ident)+'/social-review',data=json.dumps({'status':status,'notes':'Test locale'}).encode(),headers=h)
                    try:
                        with urlopen(req) as response:return response.status,json.load(response)
                    except HTTPError as exc:return exc.code,json.load(exc)
                for headers in ({'X-CSRF-Token':'bad'},{'Origin':'https://evil.example'},{'Host':'evil.example'}):self.assertEqual(request(headers)[0],403)
                self.assertEqual(request(status='VERIFIED')[0],400)
                self.assertEqual(request(status=[])[0],400)
                code,item=request();self.assertEqual(code,200);self.assertEqual(item['state'],'UNVERIFIABLE');self.assertEqual(item['social_review']['status'],'interesting')
                self.assertEqual(len(item['social_reviews']),1)
            finally:http.shutdown();http.server_close();thread.join()
    def test_explicit_workspace_reset_archives_review_before_dependencies(self):
        from sales.workspace import reset_results
        ident=self.social();self.repo.social_review(ident,{'status':'interesting','notes':'Preservare questa nota nell’archivio'})
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        result=reset_results(self.store,'temporary-test-backup')
        self.assertEqual(result['archived_rows']['commercial_social_reviews'],1)
        with self.store.connect() as c:
            saved=json.loads(c.execute("SELECT payload FROM workspace_archive WHERE source_table='commercial_social_reviews'").fetchone()[0])
            self.assertEqual(saved['notes'],'Preservare questa nota nell’archivio')
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_social_reviews').fetchone()[0],0)
            self.assertIsNone(c.execute('PRAGMA foreign_key_check').fetchone())
