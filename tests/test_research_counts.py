import tempfile
import unittest
from pathlib import Path

from sales.db import Store
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_rules import qualify
from tests.test_research import sample


class ResearchCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.store.init()
        self.rs=ResearchStore(self.store);self.c=self.rs.create();self.f=Funnel(self.rs)

    def candidate(self,host,path='',group='direct',state='promising',ready=True,verified=True,publisher=False):
        identity={'name':host,'website':'https://'+host+'/','identity_status':'verified' if verified else 'unknown','group':group}
        return self.f.transition(self.c,{'url':identity['website']+path,'strategy':'companies'},state,'Fixture',
            {'identity':identity,'company_ready':ready,'publisher':publisher})

    def listing(self,**filters):
        return self.f.listing({'campaign':self.c['id'],'company_only':1,**filters})

    def test_campaign_and_cards_count_same_unique_eligible_companies(self):
        self.candidate('alfa.example','servizi');self.candidate('alfa.example','contatti')
        self.candidate('agenzia.example',group='agencies')
        self.candidate('unknown.example',verified=False)
        self.candidate('publisher.example',publisher=True)
        self.candidate('not-target.example',ready=False)
        state=self.rs.campaign(self.c['id']);cards=self.listing(state='promising')
        self.assertEqual(state['funnel']['promising'],6)  # Raw page diagnostics remain intact.
        self.assertEqual(state['promising'],2);self.assertEqual(cards['total'],2)
        self.assertEqual(cards['group_counts'],{'agencies':1,'direct':1})
        self.assertEqual(state['target_companies'],self.listing()['total'])

    def test_state_filter_does_not_resurrect_an_older_promising_page(self):
        self.candidate('alfa.example','old');self.candidate('alfa.example','review',state='rejected')
        self.assertEqual(self.listing(state='promising')['total'],0)
        self.assertEqual(self.rs.campaign(self.c['id'])['promising'],0)
        self.assertEqual(self.listing(state='rejected')['total'],1)

    def test_diagnostics_use_current_company_states_not_stale_page_states(self):
        from sales.discovery_control import diagnostics
        self.candidate('alfa.example','old')
        self.candidate('alfa.example','review',state='unverifiable')
        self.candidate('beta.example','one')
        self.candidate('beta.example','two')
        self.candidate('unknown.example',verified=False)
        self.candidate('publisher.example',publisher=True)
        with self.store.connect() as c:
            c.execute("UPDATE discovery_candidates SET details=json_set(details,'$.acquisition_provider','serper')")
        result=diagnostics(self.rs,self.c['id'])
        for section in ('strategies','providers'):
            self.assertEqual(sum(r['companies'] for r in result[section]),self.listing()['total'])
            self.assertEqual(sum(r['promising'] for r in result[section]),self.listing(state='promising')['total'])
            self.assertEqual(sum(r['unverifiable'] for r in result[section]),1)
            self.assertEqual(sum(r['qualified'] for r in result[section]),0)

    def test_category_counts_ignore_selected_group_but_respect_phase_and_campaign(self):
        self.candidate('alfa.example');self.candidate('beta.example',group='agencies')
        self.candidate('gamma.example',state='rejected')
        cards=self.listing(state='promising',group='agencies',limit=1)
        self.assertEqual(cards['total'],1);self.assertEqual(len(cards['items']),1)
        self.assertEqual(cards['group_counts'],{'agencies':1,'direct':1})
        self.assertEqual(self.listing(state='promising',offset=20)['group_counts'],cards['group_counts'])

    def test_opportunity_categories_use_same_filters_and_ignore_pagination(self):
        for index,group in enumerate(('direct','agencies')):
            args=sample();args[0].update(website=f'https://alfa{index}.example/',legal_id='IT'+str(12345678900+index),group=group)
            self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],qualify(*args))
        filters={'campaign':self.c['id'],'status':'qualified','group':'agencies'}
        data=self.rs.opportunities(filters,limit=1)
        self.assertEqual(data['total'],1);self.assertEqual(data['group_counts'],{'direct':1,'agencies':1})
        self.assertEqual(self.rs.opportunities({**filters,'project':'webapp'})['group_counts'],{})

    def test_stop_does_not_turn_an_incomplete_assessment_into_a_promising_company(self):
        args=sample();assessment=qualify(*args,limits=['Controllo non completato'])
        self.assertEqual(assessment['status'],'unverifiable')
        aid=self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],assessment)
        self.f.transition(self.c,{'url':args[0]['website']},'verifying','Nuovo controllo',{'identity':args[0],'company_ready':True},aid)
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.assertEqual(self.listing()['items'][0]['state'],'unverifiable')
        self.assertEqual(self.rs.campaign(self.c['id'])['promising'],0)


if __name__=='__main__':unittest.main()
