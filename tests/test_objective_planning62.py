"""Search expression vs eligibility: no paid discovery or synthetic leads."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import strategies,memory
from sales.agent6.query_pipeline import prepare
import test_ai_first as h

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/planning62/campaign55-plans.json').read_text())

class Planning(unittest.TestCase):
    def test_planning_uses_its_own_shorter_contract_without_losing_safety(self):
        from sales.agent6 import schema
        from sales.commercial.ai_tasks import system_for
        prompt=system_for(schema.PLAN)
        self.assertNotIn('SCREEN/READ:',prompt)
        self.assertIn('untrusted data',prompt);self.assertIn('No messages',prompt)
        self.assertIn('falsifiable hypothesis',prompt)
        self.assertGreater(len(schema.SYSTEM)-len(prompt),1000)
        self.assertEqual(system_for(schema.READ),schema.SYSTEM)

    def test_original_page_diagnostic_query_is_allowed_without_region(self):
        q=h.query('"lavora con noi" "freelance" "frontend"')
        p,error=prepare(q,'AGENCIES',['Veneto','Lombardia'],ai_first=True)
        self.assertIsNone(error)
        self.assertNotIn('Veneto',p['query'])
        self.assertEqual(p['commercial_policy']['intents'],['request_or_invitation_to_verify'])
        self.assertNotIn('qualified',p)

    def test_company_territory_requirement_and_negative_queries_stay(self):
        for q,flow in [(h.query('servizi sviluppo siti web'),'AGENCIES'),
                       (h.query('tempo indeterminato frontend solo dipendenti'),'AGENCIES'),
                       ({**h.query('torrefazione vendita caffè sito ufficiale'),'strategy':'official_company_sector_region'},'AZIENDE')]:
            self.assertIsNotNone(prepare(q,flow,['Veneto'],ai_first=True)[1])

    def test_existing_five_channel_plans_remain_research_not_qualification(self):
        seen=set()
        for row in SAVED:
            for q in row['plan']['queries']:
                p,error=prepare(q,row['flow'],['Veneto','Lombardia','Piemonte','Toscana'],ai_first=True)
                self.assertIsNone(error,(row['flow'],error))
                self.assertEqual(p['commercial_policy']['basis'],'search_direction_only_originals_still_required')
                seen.add(row['flow'])
        self.assertEqual(seen,{'AZIENDE','AGENCIES','SOCIAL','STARTUPS','NEWS'})

    def test_first_ai_agency_plan_gets_career_brief_without_changing_region_filters(self):
        b=h.IntegratedPath();b.setUp();self.addCleanup(b.tearDown)
        before=copy.deepcopy(b.c['filters']);seen=[]
        plan={'decision':'search','reason':'Synthetic planner response using the real diagnostic query',
              'queries':[h.query('"lavora con noi" freelance frontend')]}
        def provider(p,cfg,check):seen.append(copy.deepcopy(p));return {'output':plan,'usage':{}}
        with patch('sales.agent6.ai.infer',side_effect=provider),patch('sales.agent6.research.acquire',side_effect=AssertionError('No search')):
            b.w.planning({'id':6200,'strategy':'AGENCIES','payload':{'round':0}},lambda:None)
        self.assertEqual(len(seen),1)
        self.assertIn('original careers/join pages',seen[0]['channel_strategy']['source_strategy'])
        self.assertNotIn('focus_region',seen[0]['channel_strategy'])
        self.assertEqual(seen[0]['regions'],before['regions'])
        self.assertEqual(b.c['filters'],before)
        with b.store.connect() as db:
            tasks=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='search'")]
            self.assertEqual(db.execute('SELECT count(*) FROM agent6_records').fetchone()[0],0)
        self.assertEqual(len(tasks),1);self.assertEqual(tasks[0]['query'],'"lavora con noi" freelance frontend')

    def test_paid_unknown_and_social_restrictions_remain_in_channel_briefs(self):
        for flow in ('AGENCIES','SOCIAL','STARTUPS'):
            b=strategies.brief(flow,['Veneto'],0)
            self.assertNotIn('focus_region',b)
            self.assertEqual(b['eligibility_focus_region'],'Veneto')
            self.assertIn('not mandatory',b['geography_instruction'])
        self.assertIn('Do not automate login',strategies.brief('SOCIAL',['Veneto'],0)['query_constraints'])
        self.assertIn('paid work, equity-only and unknown',strategies.brief('STARTUPS',['Veneto'],0)['goal'])
