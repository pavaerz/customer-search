"""Five historical agency leads: reading/recovery evidence, not current clients."""
import copy,hashlib,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import commercial_policy,passages,grounding,schema,qualification

SAVED=json.loads((Path(__file__).parent/'fixtures/agent8/agencies-campaign37.json').read_text())['cases']


class AgencyRegressions(unittest.TestCase):
    def test_printed_vat_is_identity_not_freelance_contract(self):
        source={'url':'https://alfa.example/jobs','checked_at':'2026-10-19T12:00:00+00:00','original':True}
        for text,external,employee in [
            ('Partita IVA: 12345678901',False,False),
            ('Full-time employee only.\nPartita IVA: 12345678901',False,True),
            ('Cerchiamo un professionista con partita IVA per un nuovo sito.',True,False),
            ('Not a full-time employee. Freelance contract.',True,False)]:
            with self.subTest(text=text):
                result=qualification.objective({**source,'text':text})
                self.assertEqual(result['external'],external);self.assertEqual(result['employee'],employee)

    def test_saved_invitations_are_eligible_for_original_read_not_auto_promotion(self):
        for case in SAVED:
            with self.subTest(domain=case['domain']):
                if case['domain']=='adriasonline.it':continue # Original-only recovery below.
                b=case['record']
                self.assertTrue(commercial_policy.investigation(b,initial=True)['allowed'])
                self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))
                self.assertTrue(all(not f.get('original') for f in b['facts']))
    def test_adrias_original_retains_frontend_invitation_when_entity_is_invalid(self):
        case=next(c for c in SAVED if c['domain']=='adriasonline.it');d=case['original']
        self.assertEqual(hashlib.sha256(d['text'].encode()).hexdigest(),d['sha256_text'])
        ev=grounding.attach(passages.bundle([{'id':'r1',**d}]))
        p={'task':schema.READ,'result_ids':['r1'],'evidence':ev,'recover_fields':True}
        anchors=[s for e in ev for s in e['segments']]
        request=next(s for s in anchors if s['text']=='Cerchiamo un collaboratore freelance per ampliamento organico')
        role=next(s for s in anchors if s['text']=='Frontend Developer / Freelance')
        technology=next(s for s in anchors if 'Conoscenza del CMS WordPress' in s['text'])
        ref=lambda s:{'segment_id':s['segment_id']}
        raw={'analyses':[{'result_id':'r1','kind':'AGENCY_PARTNERSHIP','kind_ref':ref(request),
            'facts':[{'field':'entity','ref':ref(role)},{'field':'request','ref':ref(request)},
                     {'field':'technical','ref':ref(technology)},{'field':'contract','ref':ref(request)}],
            'hypothesis':'Historical invitation; ownership and currentness need new verification.','missing':[]}]}
        value,errors=schema.validate_response(raw,p);a=value['analyses'][0]
        self.assertTrue(any(e['field']=='entity' for e in errors))
        self.assertIn('request',[f['field'] for f in a['facts']]);self.assertNotIn('entity',[f['field'] for f in a['facts']])
        b=qualification.evaluate(d,a,ev,'AGENCIES')
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertFalse(b['identity_verified'])
        self.assertEqual(b['budget']['kind'],'UNKNOWN');self.assertIn('entity',b['missing'])
        self.assertTrue(any('WordPress' in f['quote'] for f in b['facts']))
    def test_indexed_dates_do_not_make_historical_invitations_current(self):
        for case in SAVED:
            r=case['receipt'];g=qualification.objective({'url':r['url'],'text':r['content'],
                'original':False,'checked_at':r['timestamp']})
            self.assertEqual(g['freshness']['status'],'UNKNOWN');self.assertEqual(g['budget']['kind'],'UNKNOWN')

    def test_employee_only_original_overrules_freelance_search_hint_end_to_end(self):
        from test_agent7_multiflow import FiveFlowCycle
        from sales.agent6.api import preview
        from sales.commercial.coordinator import run_campaign
        for flow in ('AGENCIES','STARTUPS'):
            with self.subTest(flow=flow):
                base=FiveFlowCycle();base.setUp()
                try:
                    base.rs.stop(base.c['id']);base.rs.paused(base.c['id'])
                    f=copy.deepcopy(base.fixture.filters);f['commercial_engines']=[flow]
                    f['deep_plan_token']=preview(base.store,f)['approval_token'];campaign=base.rs.create(f)
                    url=base.urls[flow];name=base.names[flow]
                    # Indexed copy still invites freelancers. Only the saved
                    # original establishes today's exclusive employment terms.
                    base.pages[url]=base.page(url,name,[name,'Posted 2 days ago',
                        'We are looking for a WordPress developer. Full-time employee only. Remote from Italy.'])
                    with patch('socket.create_connection',side_effect=AssertionError('Offline only')),patch('sales.agent6.ai.infer',side_effect=base.model),patch('sales.agent6.coordinator.acquire',side_effect=base.search),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=base.read):
                        run_campaign(base.store,campaign,lambda:None,lambda _:None)
                    with base.store.connect() as c:
                        records=[json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(campaign['id'],))]
                    original=next(r for r in records if r['original'])
                    self.assertEqual(original['state'],'REJECTED',[(r['url'],r['state'],r.get('reason'),r.get('counterevidence')) for r in records])
                    self.assertIn('employee_job',original['counterevidence'])
                    self.assertFalse(any(r['state'] in ('VERIFIED','POTENTIAL') for r in records))
                finally:base.tearDown()


if __name__=='__main__':unittest.main()
