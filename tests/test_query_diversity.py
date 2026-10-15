import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.company_research import PROFILES, company_queries
from sales.commercial_planner import EVENTS, queries
from sales.discovery_planner import Planner, query_key, searchable_query
from sales.research_store import ResearchStore
from sales.db import Store


class QueryDiversityTests(unittest.TestCase):
    def test_priority_regions_do_not_all_begin_with_the_same_sector(self):
        starts=[next(company_queries(region)) for region in ('Veneto','Lombardia','Piemonte','Toscana')]
        sectors=[next(s for s in PROFILES['b2b'][1] if q.startswith(s+' ')) for q in starts]
        self.assertEqual(len(set(sectors)),4)

    def test_event_search_explores_sectors_early_without_losing_pairs(self):
        for profile,(_,sectors) in PROFILES.items():
            for strategy,events in EVENTS.items():
                with self.subTest(profile=profile,strategy=strategy):
                    all_queries=list(queries(strategy,'Veneto',profile))
                    direct=[q for q in all_queries if not q.startswith('site:')]
                    first=[next(s for s in sectors if q.startswith(s+' ')) for q in direct[:len(sectors)]]
                    self.assertEqual(set(first),set(sectors))
                    self.assertEqual(len(direct),len(sectors)*len(events))
                    self.assertEqual(len(all_queries),len(set(all_queries)))
                    self.assertEqual(all_queries,list(queries(strategy,'Veneto',profile)))
                    self.assertTrue(any(q.startswith('site:') for q in all_queries))

    def test_resume_uses_query_memory_not_obsolete_cursor_positions(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'test.sqlite3');store.init()
            rs=ResearchStore(store);campaign=rs.create({'regions':['Veneto'],'projects':['website']})
            planner=Planner(rs)
            with store.connect() as c:
                c.execute("INSERT INTO discovery_branches(campaign_id,strategy,region,cursor) VALUES (?,'change','Veneto',999)",(campaign['id'],))
            # Old execution order differs from the new generator. Both old
            # formulations must remain visited, regardless of their new index.
            for query in ('produzione Veneto nuova linea','Veneto nuovo marchio produzione'):
                fp=planner.offer_query(campaign,'change',{'query':query,'period':'year','region':'Veneto'})
                planner.observed(campaign,{'payload':{'query_key':fp}},[],0)
            choices=['Veneto produzione nuova linea','arredamento Veneto nuova divisione','produzione nuovo marchio Veneto']
            with patch('sales.discovery_planner.variants',return_value=iter(choices)):
                self.assertEqual(planner.tick(campaign),1)
            with store.connect() as c:
                rows=c.execute('SELECT query,fingerprint FROM discovery_queries ORDER BY rowid').fetchall()
            self.assertEqual(len(rows),3)
            expected={'query':choices[1],'period':'year','page':1};expected['query']=searchable_query(expected)
            self.assertEqual(rows[-1]['fingerprint'],query_key(expected))
            planner.observed(campaign,{'payload':{'query_key':rows[-1]['fingerprint']}},[],0)
            with patch('sales.discovery_planner.variants',return_value=iter(choices)):
                self.assertEqual(planner.tick(campaign),0)
            with store.connect() as c:
                self.assertEqual(c.execute('SELECT state FROM discovery_branches').fetchone()[0],'exhausted')
                self.assertEqual(c.execute('SELECT count(*) FROM discovery_queries').fetchone()[0],3)


if __name__=='__main__':unittest.main()
