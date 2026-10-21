"""Real C47 routing replay, no provider invocation or production writes."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as harness
import test_objective_campaign45 as capacity
import test_serper_provider as serper_harness
from sales.agent6.discovery_intent import source_issue,source_priority
from sales.agent6 import memory
from sales.serper_provider import search,search_receipt
from sales.discovery_control import measure

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign47/discovery.json').read_text())

class Routing(unittest.TestCase):
    def test_real_six_obvious_mismatches_are_routed_out_without_company_decisions(self):
        excluded=[r['body'] for r in SAVED if (source_issue(r['body']) or {}).get('reason')=='discovery_source_outside_commercial_scope']
        self.assertEqual(len(excluded),6)
        self.assertTrue(any('/wiki/2026' in r['url'] for r in excluded))
        for r in excluded:
            self.assertEqual(source_issue(r)['basis'],'search_metadata_routing_not_company_rejection')
            self.assertIsNone(source_issue(r,{'selection':'verification'}))

    def test_request_sources_and_unknown_sources_are_not_categorically_removed(self):
        for item in (
            {'url':'https://school.example/corso-web-developer/','title':'Cerchiamo un freelance per il sito del corso web developer'},
            {'url':'https://company.example/bonus-isee/','title':'Cerchiamo sviluppatore: portale bonus ISEE'},
            {'url':'https://it.wikipedia.org/wiki/Alfa_Srl','title':'Alfa Srl'},
            {'url':'https://newbrand.example/','title':''},
            {'url':'https://agency.example/careers/','title':'Collabora con noi'},
            {'url':'https://company.example/corso-italia/','title':'Apertura della sede in Corso Italia'},
        ):self.assertIsNone(source_issue(item),item)

    def test_supplier_is_deprioritized_not_rejected_and_invitation_has_precedence(self):
        p={'strategy':'freelance_role'}
        seller={'url':'https://agency.example/','title':'I nostri servizi','content':'Realizziamo siti web'}
        self.assertIsNone(source_issue(seller))
        self.assertEqual(source_priority(seller,'AGENCIES',p)['value'],-1)
        seller['content']+='; cerchiamo sviluppatori freelance.'
        self.assertEqual(source_priority(seller,'AGENCIES',p)['value'],3)
        self.assertEqual(source_priority(seller,'AZIENDE',{'strategy':'official_company_sector_region'})['value'],0)

    def test_real_discovery_exclusions_do_not_create_records_or_http_work(self):
        base=harness.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        q=harness.query('Lombardia azienda cosmetica lancia nuovo marchio vendita diretta 2026')
        task={'id':1,'kind':'search','strategy':'NEWS','payload':q}
        items=[r['body'] for r in SAVED if r['engine']=='NEWS']
        with patch('sales.agent6.research.acquire',return_value=items),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No HTTP during discovery')):
            base.w.execute(task,lambda:None)
        with base.store.connect() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            tasks=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='candidate'")]
            traces=[json.loads(r[0]) for r in db.execute("SELECT body FROM commercial_discovery WHERE decision='exclude'")]
        self.assertEqual(len(traces),4)
        excluded={r['url'] for r in traces}
        self.assertFalse(excluded & {r['url'] for r in records})
        self.assertFalse(excluded & {r['url'] for r in tasks})
        self.assertTrue(all(r['validation_status']=='PENDING' or r['validation_status']=='ACCESS_BLOCKED' for r in records))

class Priority(unittest.TestCase):
    def test_invitation_before_guide_but_never_a_saved_original(self):
        base=capacity.FirstCycleReplay();base.setUp();self.addCleanup(base.tearDown)
        base.add('candidate','AGENCIES',{'url':'https://guide.example','discovery_priority':{'value':-1}},'guide')
        invite=base.add('candidate','AGENCIES',{'url':'https://agency.example/jobs','discovery_priority':{'value':2}},'invite')
        self.assertEqual(base.choose()[0],invite)
        saved=base.add('candidate','AGENCIES',{'url':'https://original.example','original_page':{'url':'https://original.example'},'discovery_priority':{'value':-1}},'saved')
        self.assertEqual(base.choose()[0],saved)

class Receipt(unittest.TestCase):
    def test_arbitrary_echoes_are_not_persisted_and_missing_is_unknown(self):
        payload={'q':'agenzia collabora con noi','gl':'it','hl':'it','page':1,'num':10}
        raw={'searchParameters':{'q':'SECRET-RESPONSE','gl':'us','apiKey':'SECRET-KEY','page':1},'secret':'SECRET-BODY'}
        receipt=search_receipt(payload,raw)
        self.assertFalse(receipt['parameter_matches']['q'])
        self.assertFalse(receipt['parameter_matches']['gl'])
        self.assertIsNone(receipt['parameter_matches']['hl'])
        self.assertTrue(receipt['parameter_matches']['page'])
        self.assertNotIn('SECRET',json.dumps(receipt))
        self.assertFalse(search_receipt(payload,{})['provider_parameters_present'])

    def test_transport_and_cache_preserve_exact_query_echo_audit(self):
        base=serper_harness.SerperProviderTests();base.setUp();self.addCleanup(base.tearDown)
        from sales.research_store import ResearchStore
        rs=ResearchStore(base.s);c=rs.create()
        q='agenzia "collabora con noi" frontend Veneto -filetype:pdf'
        raw=copy.deepcopy(base.raw);raw['searchParameters']={'q':q,'gl':'it','hl':'it','num':10,'page':1}
        task={'strategy':'companies','kind':'search','payload':{'query':q}}
        with patch('sales.serper_provider.transport',return_value=raw) as provider:
            with measure(rs,c,task):first,hit=search(base.s,q)
            with measure(rs,c,task):second,hit2=search(base.s,q)
        self.assertEqual(provider.call_count,1)
        self.assertFalse(hit);self.assertTrue(hit2);self.assertEqual(first,second)
        self.assertTrue(first['search_receipt']['parameter_matches']['q'])
        with base.s.connect() as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT details FROM discovery_operations')]
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['search_receipt']['requested']['q']==q for r in rows))
        self.assertEqual(sum(r['network_attempted'] for r in rows),1)

    def test_mismatched_provider_query_never_becomes_cached_results(self):
        from sales.discovery_control import QueryError
        base=serper_harness.SerperProviderTests();base.setUp();self.addCleanup(base.tearDown)
        raw={**base.raw,'searchParameters':{'q':'2026'}}
        with patch('sales.serper_provider.transport',return_value=raw) as transport:
            with self.assertRaisesRegex(QueryError,'non corrisponde'):
                search(base.s,'azienda cosmetica nuovo marchio')
        self.assertEqual(transport.call_count,1)
        self.assertEqual(base.s.usage()['today']['serper'],1)
        with base.s.connect() as db:
            # No response was stored under the requested company's search key.
            self.assertFalse(db.execute("SELECT 1 FROM cache WHERE key LIKE 'serper:search:%'").fetchone())

class QueryAnchors(unittest.TestCase):
    def test_one_invitation_phrase_survives_without_stacked_exact_stack(self):
        from sales.agent6.query_pipeline import prepare
        for text,anchor in [('agenzia "collabora con noi" "frontend developer" Veneto','"collabora con noi"'),
                            ('agenzia "cerchiamo" "sviluppatore freelance" Veneto','"cerchiamo"')]:
            result,error=prepare(harness.query(text),'AGENCIES',['Veneto'],ai_first=True)
            self.assertIsNone(error)
            self.assertIn(anchor,result['query'])
            self.assertEqual(result['query'].count('"'),2)
            self.assertEqual(result['query'].replace('"',''),text.replace('"',''))
            again,error=prepare(result,'AGENCIES',['Veneto'],ai_first=True)
            self.assertIsNone(error)
            self.assertEqual(again['query_validation'],result['query_validation'])

class EmptyCycle(unittest.TestCase):
    def test_social_gets_one_recovery_after_news_repair_with_same_shared_cap(self):
        from sales.agent6 import budget
        base=capacity.FirstCycleReplay();base.setUp();self.addCleanup(base.tearDown)
        base.reserve('NEWS','plan:1','replan')
        base.add('candidate','AZIENDE',{'url':'https://original.example/'},'pending')
        memory.event(base.store,base.c,'SOCIAL','query','first-empty',{'results':0,'query':'first'})
        self.assertGreater(budget.remaining(base.store,base.c,'SOCIAL',base.cfg,'replan'),0)
        base.reserve('SOCIAL','plan:1','replan')
        self.assertEqual(budget.remaining(base.store,base.c,'SOCIAL',base.cfg,'replan'),0)
        self.assertGreater(budget.remaining(base.store,base.c,'SOCIAL',base.cfg,'verify'),0)

    def test_no_exception_for_transport_error_or_second_empty_search(self):
        from sales.agent6 import budget
        for receipts in ([{'results':0,'technical_error':'http'}],[{'results':0},{'results':0}]):
            base=capacity.FirstCycleReplay();base.setUp()
            try:
                base.reserve('NEWS','plan:1','replan')
                for i,r in enumerate(receipts):memory.event(base.store,base.c,'SOCIAL','query',str(i),r)
                self.assertEqual(budget.remaining(base.store,base.c,'SOCIAL',base.cfg,'replan'),0)
            finally:base.tearDown()
