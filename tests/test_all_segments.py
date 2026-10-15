import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.company_research import PROFILES,ACTIVITY,company_queries
from sales.discovery_planner import variants
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb,LocalResearcher
from sales.direct_channels import careers_links


class AllSegmentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.store.init();self.rs=ResearchStore(self.store)

    def test_default_campaign_explores_all_three_segments_early(self):
        self.assertEqual(self.rs.create()['filters']['target'],'all')
        queries=list(company_queries('Veneto','all'))
        for profile in ('b2b','retail','services'):
            self.assertTrue(any(q.startswith(PROFILES[profile][1][0]+' ') for q in queries[:3]))
        for text in ('lavorazioni meccaniche','negozio arredamento','studio tecnico'):
            self.assertTrue(ACTIVITY['all'].search(text))
        self.assertTrue(any('site:linkedin.com/jobs/view/' in q for q in variants('explicit','Veneto','all')))
        self.assertTrue(any('inurl:jobs' in q for q in variants('partner','Veneto','all')))
        self.assertTrue(any('inurl:careers' in q for q in variants('partner','Veneto','all')))

    def test_scope_upgrade_changes_only_unfinished_work(self):
        campaign=self.rs.create({'target':'b2b','regions':['Veneto'],'projects':['website']})
        for name in ('pending','done'):
            self.rs.enqueue(campaign['id'],'candidate','companies',{'url':'https://'+name+'.example/','filters':campaign['filters']})
        with self.store.connect() as c:
            c.execute("UPDATE research_tasks SET state='done' WHERE json_extract(payload,'$.url')='https://done.example/'")
        with self.assertRaises(ValueError):self.rs.include_all_segments(campaign['id'])
        self.rs.stop(campaign['id']);self.rs.paused(campaign['id'])
        updated=self.rs.include_all_segments(campaign['id'])
        self.assertEqual(updated['filters'],{'target':'all','regions':['Veneto'],'projects':['website']})
        with self.store.connect() as c:
            rows={r['state']:json.loads(r['payload']) for r in c.execute('SELECT state,payload FROM research_tasks')}
        self.assertEqual(rows['pending']['filters']['target'],'all')
        self.assertEqual(rows['done']['filters']['target'],'b2b')
        self.assertEqual(self.rs.resume(campaign['id'])['filters']['target'],'all')

    def test_official_homepage_reaches_jobs_and_specific_freelance_role(self):
        def page(url,body):
            return {'url':url,'status':200,'checked_at':now(),'html':'<title>Alfa Srl | Web Agency</title>'+body+'<footer>Alfa Srl · Via Roma 2, 35100 Padova (PD) · P.IVA 12345678901 <a href="mailto:info@alfa.example">info@alfa.example</a></footer>'}
        home='https://alfa.example/'
        pages={home:page(home,'<nav><a href="/jobs/">Jobs</a><a href="https://linkedin.com/jobs/view/test">LinkedIn</a></nav><main>Realizziamo siti web per aziende.</main>'),
               home+'jobs/':page(home+'jobs/','<main>Posizioni aperte <a href="/jobs/frontend/">Frontend freelance</a></main>'),
               home+'jobs/frontend/':page(home+'jobs/frontend/','<main>Cerchiamo frontend WordPress freelance per collaborazioni con il nostro team.</main>')}
        reads=[]
        def get(web,url,refresh=False):reads.append(url);return pages[url]
        with patch.object(ResearchWeb,'get',get),patch.object(LocalResearcher,'call',side_effect=AssertionError('No heavy inference')):
            result=triage(self.store,{'url':home,'strategy':'companies','direct_channels':True,'filters':{'target':'all','regions':['Veneto']}},lambda:None)
        self.assertEqual(result['state'],'promising')
        self.assertEqual(result['details']['collaboration']['url'],home+'jobs/frontend/')
        self.assertEqual(careers_links(pages[home]),[home+'jobs/'])
        self.assertFalse(any('linkedin.com' in url for url in reads))
        self.assertNotIn('assessment',result)


if __name__=='__main__':unittest.main()
