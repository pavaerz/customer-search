"""Offline query repairs and paid-planning avoidance; no real search results."""
import json,unittest
from datetime import date
from unittest.mock import patch
from sales.agent6 import query_pipeline as q, memory
import test_agent6_campaign32 as support
query=support.query


class Queries(unittest.TestCase):
    def test_news_or_repaired_without_dropping_a_branch(self):
        raw={**query('Veneto site:it azienda "nuova linea prodotti" OR "nuovo showroom"'),'missing':'Verify official company and related digital gap'}
        prepared,error=q.prepare(raw,'NEWS',['Veneto'])
        self.assertIsNone(error)
        self.assertEqual(prepared['query'],'Veneto site:.it azienda ("nuova linea prodotti" OR "nuovo showroom")')
        self.assertEqual(prepared['commercial_policy']['intent'],'company_event_to_verify')
        bad=query('"nuovo showroom" Veneto OR portfolio siti web')
        self.assertIsNone(q.prepare(bad,'NEWS',['Veneto'])[0])
        for raw in ('Lombardia site:it azienda "nuova sede" OR "espansione"',
                    'Veneto site:it "lancia" OR "presenta" startup OR azienda "nuovo prodotto"'):
            proposal={**query(raw),'missing':'Verify official company and digital gap'}
            self.assertIsNotNone(q.prepare(proposal,'NEWS',['Veneto','Lombardia'])[0])

    def test_invalid_syntax_and_temporal_constraints_remain_rejected(self):
        for text in ('("nuovo showroom" Veneto','"nuovo showroom Veneto',
                     'site: "nuovo showroom" Veneto','site:localhost "nuovo showroom" Veneto',
                     'after:2026-99-01 "nuovo showroom" Veneto','foo:bar "nuovo showroom" Veneto'):
            self.assertFalse(q.normalize(text)['allowed'],text)
        self.assertIsNone(q.prepare(query('"nuovo showroom" Veneto 2024'),'NEWS',['Veneto'],today=date(2026,10,19))[0])

    def test_specific_sector_not_generic_ecommerce_company(self):
        for text in ('site:.it azienda ecommerce Veneto prodotti ufficiali','aziende prodotti Veneto sito ufficiale'):
            p={**query(text),'strategy':'official_company_sector_region'}
            self.assertEqual(q.prepare(p,'AZIENDE',['Veneto'])[1]['reason'],'specific_business_sector_missing')
        for text in ('produttore serramenti Padova sito ufficiale','azienda lavorazioni meccaniche Vicenza',
                     'produttore componenti medicali Veneto'):
            p={**query(text),'strategy':'official_company_sector_region'}
            self.assertIsNotNone(q.prepare(p,'AZIENDE',['Veneto'])[0],text)
        self.assertIsNone(q.prepare({**query('produttore serramenti Milano sito ufficiale'),'strategy':'official_company_sector_region'},'AZIENDE',['Veneto'])[0])

    def test_actual_zero_receipts_stop_regional_clones_not_other_sources(self):
        rows=[{'query':f'agenzia cerchiamo freelance WordPress {r}','results':0,'campaign_id':1} for r in ('Veneto','Lombardia','Piemonte')]
        candidate=query('agenzia cerchiamo freelance WordPress Toscana')
        self.assertEqual(q.prepare(candidate,'AGENCIES',['Toscana'],rows)[1]['reason'],'query_family_saturated')
        self.assertIsNotNone(q.prepare(candidate,'AGENCIES',['Toscana'],rows[:2])[0])
        self.assertIsNotNone(q.prepare(query('agenzia collabora con noi frontend Toscana'),'AGENCIES',['Toscana'],rows)[0])
        self.assertIsNotNone(q.prepare(candidate,'AGENCIES',['Toscana'],[{**r,'technical_error':'timeout'} for r in rows])[0])
        self.assertEqual(q.adaptation([rows[0]]*3),[])

    def test_three_portal_heavy_receipts_change_family_but_not_blacklist(self):
        rows=[{'query':f'produttore serramenti {r} sito ufficiale','results':10,
            'policy_rejections':[{'reason':'portal'}]*8} for r in ('Veneto','Lombardia','Toscana')]
        adaptation=q.adaptation(rows)
        self.assertEqual(adaptation[0]['reason'],'mostly_non_company_sources')
        self.assertFalse(adaptation[0]['permanent_blacklist'])

    def test_saved_unused_proposal_runs_without_another_ai_plan(self):
        base=support.Campaign32Fix();base.setUp();self.addCleanup(base.tearDown)
        proposal={**query('agenzia cerchiamo freelance WordPress Veneto'),'page':1,'region':'Veneto'}
        memory.event(base.store,base.c,'AGENCIES','plan','old',{'queries':[proposal],'chosen':None})
        task={'id':9876,'strategy':'AGENCIES','payload':{'round':1}}
        with patch.object(base.w,'model',side_effect=AssertionError('No new AI plan')):
            base.w.planning(task,lambda:None)
        with base.store.connect() as c:
            search=c.execute("select payload from research_tasks where kind='search'").fetchone()
            self.assertEqual(json.loads(search[0])['query'],proposal['query'])
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions').fetchone()[0],0)
        # A resumed plan task finishes its choice; it doesn't duplicate search.
        with patch.object(base.w,'model',side_effect=AssertionError('No duplicate AI')):
            base.w.planning(task,lambda:None)
        with base.store.connect() as c:self.assertEqual(c.execute("select count(*) from research_tasks where kind='search'").fetchone()[0],1)
