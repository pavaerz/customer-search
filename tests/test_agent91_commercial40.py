"""Saved query/request regressions, not new provider results or leads."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import commercial_policy,completion,qualification,query_pipeline
from test_agent6_campaign32 import query

SAVED=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/agent91/commercial40.json.gz').read_bytes()))
CASES={r['id']:r for r in SAVED['cases']}

def source_for(body):
    return next(d for d in body['documents'] if any(f['field']=='request' and f['quote'] in d['text'] for f in body['facts']))


class SavedCommercial40(unittest.TestCase):
    def test_ambiguous_partner_and_supplier_form_queries_stop_before_search(self):
        bad=[q for q in SAVED['queries'] if '"cerchiamo partner"' in q['query'] or '"richiesta preventivo"' in q['query']]
        self.assertEqual(len(bad),5)
        for receipt in bad:
            p=next(x['proposal'] for x in SAVED['proposals'] if x['proposal']['query']==receipt['query'])
            result= commercial_policy.assess_query(p,receipt['flow'])
            self.assertFalse(result['allowed'],receipt['query'])

    def test_original_nontechnical_invites_are_not_developer_requests(self):
        for rid in (566,657,499,738):
            body=CASES[rid]['body'];source=source_for(body)
            self.assertEqual(completion.relationship(source,body['facts']),'NONTECHNICAL_PARTNERSHIP',rid)
            # Freeze the already validated historical interpretation and test
            # the actual qualification wrapper's policy, not new AI responses.
            with patch('sales.agent6.qualification._evaluate',return_value=copy.deepcopy(body)):
                result=qualification.evaluate(source,None,[],CASES[rid]['flow'])
            self.assertEqual(result['state'],'REJECTED')
            self.assertFalse(result['completion_queue']['promising'])
            self.assertFalse(commercial_policy.investigation(result)['allowed'])
            self.assertEqual(result['budget'],body['budget'])
            from sales.agent6.commercial_view import enrich
            self.assertEqual(enrich(result)['collaboration_type'],'UNKNOWN')

    def test_accreditation_alone_is_not_assumed_incompatible_or_technical_work(self):
        body=CASES[564]['body']
        self.assertNotEqual(completion.relationship(source_for(body),body['facts']),'NONTECHNICAL_PARTNERSHIP')
        self.assertNotIn(body['state'],('VERIFIED','POTENTIAL'))


class DirectionControls(unittest.TestCase):
    def relation(self,request,text=None):
        return completion.relationship({'url':'https://fixture.example/','original':True,'text':text or request},
                                       [{'field':'request','quote':request,'original':True}])

    def test_real_technical_partners_and_direct_buyers_remain_searchable(self):
        for text in ('agenzia "cerchiamo partner tecnici" WordPress Veneto',
                     'agenzia "cerchiamo partner" "sviluppo web" Veneto',
                     'agenzia "collabora con noi" freelance frontend Veneto',
                     'azienda "cerchiamo fornitore" ecommerce Veneto',
                     'azienda "cerchiamo sviluppatore" "richiesta preventivo" freelance WordPress Veneto'):
            self.assertTrue(commercial_policy.assess_query(query(text),'AGENCIES')['allowed'],text)

    def test_each_boolean_branch_needs_its_own_direction(self):
        p=query('agenzia ("cerchiamo partner tecnici" OR "cerchiamo partner") WordPress Veneto')
        self.assertFalse(commercial_policy.assess_query(p,'AGENCIES')['allowed'])
        self.assertTrue(commercial_policy.assess_query(query('agenzia cerchiamo freelance WordPress -"richiesta preventivo"'),'AGENCIES')['allowed'])

    def test_web_development_for_franchise_hotel_or_sales_portal_is_not_rejected(self):
        for request in ('Cerchiamo uno sviluppatore WordPress freelance per il sito del nostro franchising.',
                        'Cerchiamo un web designer per il portale di accoglienza degli hotel.',
                        'Cerchiamo sviluppatori frontend per il portale dei nostri partner commerciali.'):
            self.assertEqual(self.relation(request),'INVITATION',request)

    def test_neighbouring_technical_offer_does_not_change_the_requested_role(self):
        request='Cerchiamo partner commerciali per vendere il nostro software.'
        self.assertEqual(self.relation(request,'Sviluppiamo siti WordPress.\n'+request),'NONTECHNICAL_PARTNERSHIP')
        self.assertEqual(self.relation('Cerchiamo partner per aprire il proprio negozio.'),'NONTECHNICAL_PARTNERSHIP')

    def test_two_independent_invites_stay_mixed_not_wholly_rejected_or_promoted(self):
        bad='Cerchiamo partner commerciali per vendere il nostro software.'
        good='Cerchiamo sviluppatori WordPress freelance per realizzare siti.'
        result=completion.relationship({'text':bad+'\n'+good},[{'field':'request','quote':bad},{'field':'request','quote':good}])
        self.assertEqual(result,'MIXED_INVITATIONS')

class OutcomeAdaptation(unittest.TestCase):
    def receipts(self):
        return [{**q,'campaign_id':40} for q in SAVED['queries'] if q['memory_id'] in (1751,1938,2094)]

    def test_three_real_empty_queries_count_as_one_family_despite_verb_inflection(self):
        rows=self.receipts()
        self.assertEqual(len(rows),3)
        self.assertEqual(len({query_pipeline.family(r['query']) for r in rows}),1)
        self.assertEqual(query_pipeline.adaptation(rows)[0]['reason'],'zero_results')
        self.assertEqual(query_pipeline.adaptation(rows[:2]),[])
        self.assertEqual(query_pipeline.adaptation([{**r,'technical_error':'timeout'} for r in rows]),[])
        self.assertNotEqual(query_pipeline.family(rows[0]['query']),query_pipeline.family('site:linkedin.com agenzia cercasi freelance frontend Veneto'))

    def test_queued_query_rechecks_new_outcomes_before_any_paid_search(self):
        import test_agent6_campaign32 as support
        from sales.agent6 import memory
        b=support.Campaign32Fix();b.setUp();self.addCleanup(b.tearDown)
        for n,r in enumerate(self.receipts()):memory.event(b.store,b.c,'AGENCIES','query','empty:'+str(n),r)
        p=query('site:.it Toscana agenzia "cerchiamo freelance" frontend')
        with patch('sales.agent6.coordinator.acquire',side_effect=AssertionError('Saturated query must not reach provider')):
            b.w._execute({'id':8881,'kind':'search','strategy':'AGENCIES','payload':p},lambda:None)
        with b.store.connect() as c:
            row=c.execute("select body from agent6_memory where kind='query_policy'").fetchone()
            self.assertEqual(json.loads(row[0])['reason'],'query_family_saturated')
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions').fetchone()[0],0)


if __name__=='__main__':unittest.main()
