import copy
import tempfile
import unittest
from pathlib import Path

from sales.db import Store
from sales.research_store import ResearchStore
from sales.research_rules import qualify
from sales.research_quality import proposed_reviews,ranked_quality
from sales.research_api import quality_report
from sales.discovery_control import diagnostics
from sales.research_funnel import Funnel
from test_research import sample


class RankedQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'test.sqlite3');self.store.init()
        self.rs=ResearchStore(self.store);self.c=self.rs.create();self.ids=[]
    def tearDown(self):self.temp.cleanup()
    def add(self,index,score=85,status='qualified'):
        args=copy.deepcopy(sample());identity=args[0]
        identity.update(name='Alfa '+str(index),website=f'https://alfa{index}.example/',legal_id='IT'+str(index).zfill(11))
        assessment=qualify(*args);assessment.update(score=score,status=status)
        aid=self.rs.save(self.c['id'],self.c['generation'],None,identity,args[1],assessment)
        Funnel(self.rs).transition(self.c,{'url':identity['website'],'strategy':'change','provider':'serper'},status,'Esito di prova',{'identity':identity,'acquisition_provider':'serper'},assessment_id=aid)
        self.ids.append(aid);return aid
    def test_false_positive_remains_in_top_ten_after_demotion(self):
        ids=[self.add(i,100-i) for i in range(10)]
        for aid in ids:self.rs.review(aid,'false_positive' if aid==ids[0] else 'confirmed','Revisione manuale del campione')
        report=quality_report(self.store)
        self.assertEqual(report['precision_at_10'],90)
        self.assertIsNone(report['precision_at_20'])
        self.assertEqual(report['ranked_samples']['10']['assessment_ids'],ids)
        self.assertEqual(report['ranked_samples']['10']['false_positives'],1)
        strategy=next(g for g in diagnostics(self.rs,self.c['id'])['strategies'] if g['name']=='change')
        self.assertEqual(strategy['precision_at_10'],90)
        # The latest manual correction supersedes the old review, without
        # creating another company in the denominator.
        self.rs.review(ids[0],'confirmed','Nuova revisione con prove aggiornate')
        self.assertEqual(quality_report(self.store)['precision_at_10'],100)
    def test_missing_top_review_cannot_be_replaced_by_lower_ranked_confirmation(self):
        for i in range(20):
            aid=self.add(i,100-i)
            if i!=0:self.rs.review(aid,'confirmed','Revisione manuale del campione')
        report=quality_report(self.store)
        self.assertIsNone(report['precision_at_10']);self.assertIsNone(report['precision_at_20'])
        self.assertEqual(report['ranked_samples']['10']['reviewed'],9)
        self.rs.review(self.ids[0],'confirmed','Revisione manuale completata')
        self.assertEqual(quality_report(self.store)['precision_at_20'],100)
    def test_only_proposed_companies_enter_ranked_precision_and_campaigns_are_separate(self):
        aid=self.add(0,status='needs_review');self.rs.review(aid,'false_positive','Non era una proposta qualificata')
        self.assertEqual(proposed_reviews(self.store,self.c['id']),[])
        self.assertEqual(quality_report(self.store)['false_positives'],0)
        self.add(1)
        self.assertEqual(proposed_reviews(self.store,self.c['id']+1),[])
    def test_duplicate_dossiers_and_nonconfirmation_verdicts_do_not_fill_the_sample(self):
        rows=[{'id':i,'entity_id':i//2,'score':90,'verdict':'confirmed'} for i in range(20)]
        self.assertEqual(ranked_quality(rows)['ranked_samples']['10']['available'],10)
        rows[-1]['verdict']='missed_opportunity'
        result=ranked_quality(rows)
        self.assertIsNone(result['precision_at_10'])
        self.assertEqual(result['ranked_samples']['10']['reviewed'],9)


if __name__=='__main__':unittest.main()
