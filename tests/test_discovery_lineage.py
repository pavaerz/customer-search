import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_analysis import resolve_publisher, LocalResearcher
from sales.research_discovery import search
from sales.discovery_planner import Planner
from sales.discovery_relevance import alternative_query, utility_link, subject_exclusion
from sales.prospect_scope import apply_scope


class DiscoveryLineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.store.init()
        self.store.configure({'provider':'serper'})
        self.rs=ResearchStore(self.store);self.c=self.rs.create({'regions':['Veneto']})

    def test_sharing_control_is_never_resolved_as_article_company(self):
        page={'url':'https://news.example/alfa','status':200,'checked_at':now(),
              'html':'<title>Alfa Srl investe</title><article><h1>Alfa Srl investe</h1>'
              '<div class="td-post-content"><a href="https://api.whatsapp.com/send?text=nuova-linea">WhatsApp</a>'
              '<p>Alfa Srl inaugura una nuova linea di prodotti per i mercati esteri.</p></div></article>'}
        with patch.object(LocalResearcher,'call',return_value={'companies':[]}):
            result=resolve_publisher(self.store,page,{'strategy':'change'},lambda:None)
        self.assertFalse(any(x.get('subject')=='WhatsApp' for x in result['discovered']+result['resolve_queries']))
        self.assertTrue(all('whatsapp' not in x['url'] for x in result['discovered']))

    def test_platform_filter_does_not_exclude_company_using_whatsapp(self):
        for url in ('https://api.whatsapp.com/send','https://wa.me/123','https://t.me/share/url','https://linkedin.com/company/alfa'):
            self.assertTrue(utility_link(url))
        self.assertFalse(utility_link('https://alfa.example/contatti?canale=whatsapp'))
        self.assertFalse(utility_link('https://whatsapp.com.example/'))
        self.assertIsNone(subject_exclusion('Alfa Srl',[{'text':'Alfa Srl usa WhatsApp per i contatti.'}]))
        self.assertIsNotNone(subject_exclusion('WhatsApp'))

    def test_real_company_link_survives_alongside_sharing_widget(self):
        page={'url':'https://news.example/alfa','status':200,'checked_at':now(),
              'html':'<title>Alfa Srl apre un nuovo mercato</title><p>'
              '<a href="https://alfa.example/">Alfa Srl</a> inaugura una nuova linea di prodotti.</p>'
              '<a href="https://api.whatsapp.com/send">WhatsApp</a>'}
        with patch.object(LocalResearcher,'call',side_effect=AssertionError('Linked company needs no model')):
            result=resolve_publisher(self.store,page,{'strategy':'change'},lambda:None)
        self.assertEqual([x['subject'] for x in result['discovered']],['Alfa Srl'])

    def test_model_cannot_promote_platform_name_to_company(self):
        quote='WhatsApp: condividi la notizia della nuova linea di prodotti.'
        page={'url':'https://news.example/notizia','status':200,'checked_at':now(),
              'html':'<title>Nuova linea di prodotti</title><p>'+quote+'</p>'}
        with patch.object(LocalResearcher,'call',return_value={'companies':[{'name':'WhatsApp','quote':quote}]}):
            result=resolve_publisher(self.store,page,{'strategy':'change'},lambda:None)
        self.assertFalse(result['discovered']);self.assertFalse(result['resolve_queries'])
        self.assertEqual(result['excluded_names'][0]['name'],'WhatsApp')

    def test_alternative_marker_survives_search_results_and_stops_recursion(self):
        payload=alternative_query({'url':'https://alfa.example/','subject':'Alfa Srl',
            'company_host':'alfa.example','root_query_key':'original'})
        result={'results':[{'url':'https://directory.example/alfa','title':'Alfa Srl','content':'Alfa Srl a Padova'}]}
        with patch('sales.serper_provider.search',return_value=(result,False)):
            search(self.rs,self.c,{'strategy':'change','payload':payload},lambda:None)
        with self.store.connect() as c:
            child=json.loads(c.execute("SELECT payload FROM discovery_frontier WHERE kind='candidate'").fetchone()[0])
        self.assertEqual(child['alternative_source'],'https://alfa.example/')
        self.assertEqual(child['root_query_key'],'original')
        self.assertIsNone(alternative_query(child))

    def test_sibling_errors_do_not_create_multiple_alternative_searches(self):
        base={'subject':'Alfa Srl','company_host':'alfa.example','root_query_key':'original'}
        a=alternative_query({**base,'url':'https://alfa.example/'})
        b=alternative_query({**base,'url':'https://directory.example/alfa'})
        planner=Planner(self.rs)
        self.assertTrue(planner.offer_query(self.c,'change',a))
        self.assertIsNone(planner.offer_query(self.c,'change',b))
        self.assertTrue(planner.offer_query(self.c,'change',{**b,'root_query_key':'new-independent-evidence'}))

    def test_legacy_platform_tasks_retired_without_deleting_history(self):
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://other.example/whatsapp','subject':'WhatsApp'})
        self.rs.enqueue(self.c['id'],'candidate','companies',{'url':'https://alfa.example/'})
        self.assertEqual(apply_scope(self.rs,self.c),1)
        with self.store.connect() as c:
            rows=c.execute('SELECT state,payload FROM research_tasks ORDER BY id').fetchall()
        self.assertEqual([r['state'] for r in rows],['superseded','pending'])


if __name__=='__main__':unittest.main()
