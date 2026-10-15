import copy
from datetime import datetime,timezone,timedelta
import unittest
from sales.company_investigation import plan,topic_links
from sales.company_research import research_tasks,company_verification
from sales.research_analysis import select_pages


class CompanyInvestigationTests(unittest.TestCase):
    def test_article_publication_date_does_not_borrow_related_article_dates(self):
        from sales.research_analysis import document
        from sales.db import now
        page={'url':'https://alfa.example/news/event','status':200,'checked_at':now(),
              'html':'<h1>Nuovo marchio</h1><time itemprop="datePublished" datetime="2026-10-08">8 ottobre</time><aside><time datetime="2025-01-15">Articolo correlato</time></aside>'}
        self.assertEqual(document(page)['published_at'],'2026-10-08')
        page['html']+='<time itemprop="datePublished" datetime="2026-10-07">Altra notizia</time>'
        self.assertIsNone(document(page)['published_at'])
    def test_linked_company_brand_is_checked_as_existing_solution(self):
        from sales.company_investigation import linked_brand_solutions
        identity={'name':'AG Metal','website':'https://ag-metal.example/','identity_status':'verified'}
        page={'url':identity['website'],'html':'<nav><a href="https://brand.example/">AG Metal Design</a><a href="https://other.example/">Other Design</a><a href="https://facebook.com/agmetal">AG Metal Design</a></nav>','status':200}
        self.assertEqual(linked_brand_solutions([page],identity),['https://brand.example/'])
        self.assertEqual(linked_brand_solutions([{**page,'url':'https://publisher.example/'}],identity),[])
        self.assertEqual(linked_brand_solutions([page],{**identity,'identity_status':'unknown'}),[])
    def setUp(self):
        self.identity={'name':'Alfa Srl','website':'https://alfa.example/','identity_status':'verified','region':'Veneto'}
        self.quote='Alfa Srl presenta una nuova divisione dedicata ai componenti modulari.'
        self.doc={'id':'event','text':self.quote,'research_text':self.quote,'official':False,
                  'scoped_to_subject':'Alfa Srl','url':'https://news.example/alfa',
                  'published_at':datetime.now(timezone.utc).isoformat()}
    def test_original_event_generates_factual_and_counterproof_questions(self):
        result=plan(self.identity,[self.doc])
        self.assertEqual(len(result),1);p=result[0]
        self.assertEqual(p['status'],'hypothesis');self.assertEqual(p['quote'],self.quote)
        self.assertEqual(p['document_id'],'event');self.assertTrue(p['countercheck'])
        self.assertTrue(all(q.startswith('site:alfa.example ') for q in p['queries']))
        self.assertIn('componenti modulari',p['queries'][0])
        self.assertNotIn('budget',p)
    def test_unknown_identity_other_subject_or_unscoped_article_cannot_seed(self):
        self.assertFalse(plan({**self.identity,'identity_status':'unknown'},[self.doc]))
        for value in (None,'Beta Srl'):
            self.assertFalse(plan(self.identity,[{**self.doc,'scoped_to_subject':value}]))
    def test_unknown_old_future_dates_and_invented_excerpt_cannot_seed(self):
        for date in (None,'not-a-date',(datetime.now(timezone.utc)-timedelta(days=181)).isoformat(),(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()):
            self.assertFalse(plan(self.identity,[{**self.doc,'published_at':date}]))
        self.assertFalse(plan(self.identity,[{**self.doc,'text':'Il fatto non è nella fonte.'}]))
    def test_republication_does_not_multiply_questions(self):
        self.assertEqual(len(plan(self.identity,[self.doc,{**self.doc,'id':'copy','url':'https://copy.example/'}])),1)
    def test_actual_link_to_named_offer_is_read_even_without_generic_url_keywords(self):
        quote='Alfa Essentials: la nuova divisione dedicata a prodotti modulari'
        doc={**self.doc,'text':quote,'research_text':quote,'official':True,'url':'https://alfa.example/news/novita'}
        questions=plan(self.identity,[doc]);self.assertEqual(questions[0]['named_topic'],'Alfa Essentials')
        page={'url':doc['url'],'html':'<title>Novità</title><main><a href="/essentials/">Alfa Essentials</a><a href="https://other.example/">Altro fornitore</a></main>'}
        self.assertEqual(topic_links([page],questions),['https://alfa.example/essentials/'])
        self.assertEqual(topic_links([{**page,'url':'https://other.example/'}],questions),[])
    def test_section_selection_uses_visible_label_not_only_opaque_path(self):
        links=[{'url':'https://alfa.example/contatti/','label':'Contatti'},
               {'url':'https://alfa.example/essentials/','label':'Prodotti Essentials'},
               {'url':'https://alfa.example/x/','label':'Catalogo'}]
        chosen=select_pages(links)
        self.assertIn(links[1]['url'],chosen);self.assertIn(links[2]['url'],chosen)
        self.assertEqual(select_pages(['https://alfa.example/contatti/']),['https://alfa.example/contatti/'])
    def test_source_units_do_not_bridge_removed_navigation(self):
        from sales.claim_selection import grounded_units,materialize
        from sales.research_rules import validate_signals
        first='Alfa Srl presenta una nuova divisione per i mercati esteri.'
        second='Il catalogo aggiornato è disponibile nella pagina dedicata.'
        text=first+'\n'+second;original=first+'\nNavigazione e cookie\n'+second
        units=grounded_units('doc',text,original)
        self.assertEqual([u['text'] for u in units],[first,second])
        claims,errors=materialize('doc',text,units,{'claims':[{'unit_id':u['id'],'kind':'business'} for u in units]})
        self.assertEqual(errors,[])
        _,invalid=validate_signals(claims,[{'id':'doc','text':original,'url':'https://alfa.example/','checked_at':datetime.now(timezone.utc).isoformat()}])
        self.assertEqual(invalid,[])
    def test_followups_preserve_editorial_event_instead_of_overwriting_with_company_description(self):
        plans=plan(self.identity,[self.doc]);own={**self.doc,'id':'own','official':True,'url':self.identity['website'],'text':'Produciamo componenti industriali.'}
        result={'details':{'identity':self.identity,'company_ready':True,'company_documents':[own],'origin_documents':[self.doc],
                           'target_quote':'Produciamo componenti industriali.','research_links':['https://alfa.example/prodotti'],
                           'investigation_plan':plans}}
        before=copy.deepcopy(result)
        children,queries=research_tasks({'filters':{},'root_query_key':'root'},result)
        self.assertEqual(len(queries),2)
        for item in children+queries:
            self.assertIn(self.doc,item['source_documents'])
            self.assertNotIn('subject_quote',item)
            self.assertEqual(item['root_query_key'],'root')
        self.assertEqual(queries[0]['investigation_question'],plans[0])
        self.assertEqual(company_verification({},result)['investigation_plan'],plans)
        self.assertEqual(result,before)
        result['details']['investigation_links']={plans[0]['id']:['https://alfa.example/essentials/']}
        children,queries=research_tasks({},result)
        self.assertEqual(children[0]['url'],'https://alfa.example/essentials/')
        self.assertEqual(len(queries),1)
        self.assertEqual(queries[0]['query'],plans[0]['queries'][1])
