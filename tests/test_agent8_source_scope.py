"""Saved Campaign 37 text + explicitly synthetic transport: no live requests."""
import json,unittest
from html import escape
from pathlib import Path
from unittest.mock import patch
import test_agent6_campaign32 as support
from sales.agent6 import source_scope,qualification,passages
from sales.agent6.coordinator import AgentCoordinator
from sales.db import digest

FIXTURE=Path(__file__).parent/'fixtures/agent8/mrw-campaign37.json'


class SourceScope(unittest.TestCase):
    def test_real_saved_thread_does_not_borrow_neighbouring_requests(self):
        doc=json.loads(FIXTURE.read_text());self.assertEqual(digest(doc['text']),doc['text_hash'])
        scope=source_scope.text_scope(doc['text'])
        self.assertEqual(scope['boundary'],'Discussioni simili')
        self.assertEqual(scope['text'],doc['text'][:scope['selected_ranges'][0][1]])
        self.assertIn('cerchiamo esperto',scope['text'].lower())
        self.assertNotIn('Ricerchiamo collaboratori per incremento fanpage',scope['text'])
        fresh=qualification.temporal(scope['text'],doc['checked_at'],True)
        self.assertEqual(fresh['status'],'STALE');self.assertEqual(fresh['published_at'],'2006-03-24')
        source={'id':'r1','text':scope['text'],'url':doc['url'],'original':True,'checked_at':doc['checked_at'],'document_id':doc['text_hash']}
        for e in passages.bundle([source]):
            self.assertEqual(e['text'],doc['text'][e['offset']:e['offset']+len(e['text'])])
            self.assertNotIn('Discussioni simili',e['text'])

    def test_related_words_in_a_sentence_are_not_a_boundary(self):
        text='La nostra piattaforma include annunci simili e ci serve un frontend freelance.\nScrivici.'
        self.assertEqual(source_scope.text_scope(text)['text'],text)
        html='<p>Related jobs is the name of our project</p><a href="/apply">Apply now</a>'
        self.assertEqual(source_scope.main_html(html),html)

    def test_only_primary_application_links_survive_italian_related_heading(self):
        html='<a href="/apply">Candidati</a><h2><span>Discussioni simili</span></h2><a href="/other">Candidati</a>'
        self.assertEqual(qualification.followup_links({'html':html,'url':'https://forum.example/thread','checked_at':'2026-10-19'}),[{'url':'/apply','label':'Candidati'}])

    def test_unlabelled_or_future_date_does_not_become_recent_demand(self):
        for text in ('Copyright 19 Ott 2026','Aggiornato il 19 Ott 2026','Pubblicato il 31 Feb 2026','Pubblicato il 19 Ott 2027'):
            self.assertNotEqual(qualification.temporal(text,'2026-10-19',True)['status'],'RECENT')

    def test_saved_old_thread_is_stopped_before_ai_without_rewriting_history(self):
        base=support.Campaign32Fix();base.setUp()
        try:
            doc=json.loads(FIXTURE.read_text())
            page={'url':doc['url'],'checked_at':doc['checked_at'],'status':200,
                'html':'<html data-template="thread_view"><title>'+escape(doc['title'])+'</title><pre>'+escape(doc['text'])+'</pre></html>'}
            task={'strategy':'AGENCIES','payload':{'url':doc['url'],'original_page':page,'query':'cerchiamo collaboratori frontend','strategy':'external'}}
            worker=AgentCoordinator(base.store,base.c)
            with patch('sales.agent6.ai.infer',side_effect=AssertionError('Stale original requires no paid inference')),patch('sales.research_analysis.CompanyWeb.get',side_effect=AssertionError('Saved original must not refetch')):
                worker.reading(task,lambda:None)
            with base.store.connect() as c:
                rows=c.execute('SELECT state,body FROM agent6_records').fetchall()
                self.assertEqual(len(rows),1);self.assertEqual(rows[0]['state'],'REJECTED')
                b=json.loads(rows[0]['body']);self.assertIn('stale_request',b['counterevidence'])
                self.assertEqual(b['source_scope']['boundary'],'Discussioni simili')
                self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        finally:base.tearDown()


if __name__=='__main__':unittest.main()
