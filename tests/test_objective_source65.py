"""Campaign 58 originals and unchanged response; network/AI transport mocked."""
import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_ai_first as h
from scripts.run_objective_validation_sol import SOL_CONFIG
from sales.agent6 import evidence, decision, budget
from sales.agent6.source_context import editorial
from sales.agent6.discovery_intent import assess
from sales.agent6.commercial_policy import assess_query
from sales.commercial.inspection import document
from sales.commercial.municipalities import resolve_address_quotation
from sales.agent6.subject_geography import validate as validate_geography

FIXTURE = Path(__file__).parent / 'fixtures/ai_first/source65'


def page(rid):
    return next(r['page'] for r in json.loads(gzip.decompress((FIXTURE/'originals.json.gz').read_bytes())) if r['record_id']==rid)


def capture(rid, output=None):
    base=h.IntegratedPath();base.setUp()
    try:
        base.c['filters']['commercial']['ai'].update(SOL_CONFIG)
        base.c['filters']['commercial']['ai']['provider']='MOCK'
        original=page(rid);flow='STARTUPS' if rid==1877 else 'NEWS'
        base.w.enqueue('candidate',flow,{'url':original['url'],'original_page':original},'source65')
        with base.store.connect() as c:
            row=c.execute("SELECT * FROM research_tasks WHERE fingerprint='source65'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        seen=[]
        def infer(p,c,check):
            seen.append(copy.deepcopy(p));return {'output':output or {},'usage':{}}
        with patch('sales.agent6.ai.infer',side_effect=infer),patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Offline original only')):
            base.w.execute(task,lambda:None)
        with base.store.connect() as c:
            records=[json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records')]
            tasks=[json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE fingerprint!='source65'")]
        return seen,records,tasks
    finally:base.tearDown()


class SavedContent(unittest.TestCase):
    def test_actual_article_survives_layout_sidebar_flags(self):
        original=page(1882);doc=document(original);p=evidence.packet(original,doc)
        proofs=evidence.passages(p,p['units'][0],3000,source_content=True)
        text='\n'.join(e['text'] for e in proofs)
        self.assertIn('Il 2026 si apre con una nuova inaugurazione per Latteria Soligo',text)
        self.assertIn('San Donà di Piave',text)
        self.assertNotIn('Direttore Sergio',text)
        for e in proofs:self.assertEqual(doc['text'][e['offset']:e['offset']+len(e['text'])],e['text'])
        self.assertLessEqual(sum(len(e['text'].encode()) for e in proofs),3000)

    def test_actual_unowned_public_proposal_gets_main_content_without_article_schema(self):
        original=page(1877);p=evidence.packet(original,document(original))
        self.assertFalse(p['editorial_metadata'])
        self.assertTrue(editorial(p,p['units'][0],'STARTUPS',False))
        proofs=evidence.passages(p,p['units'][0],3000,source_content=True)
        text='\n'.join(e['text'] for e in proofs)
        self.assertIn('Startup UK offre piattaforma DPP',text)
        self.assertIn('Richiesti partner per piloti',text)
        self.assertIn('offre piattaforma',text)  # Supplier direction survives.
        self.assertNotIn('Strategia di Specializzazione',text)
        self.assertNotIn('PMI cipriota',text)  # Related proposals are not this subject.

    def test_real_worker_delivers_both_main_contents_after_input_compaction(self):
        from sales.commercial.token_count import estimate
        for rid,needle in ((1882,'Latteria Soligo'),(1877,'Startup UK offre piattaforma DPP')):
            seen,records,_=capture(rid)
            self.assertEqual(len(seen),1)
            self.assertIn(needle,'\n'.join(e['text'] for e in seen[0]['evidence']))
            self.assertLessEqual(estimate(seen[0],SOL_CONFIG)['tokens'],SOL_CONFIG['max_input_tokens'])
            self.assertFalse(any(b.get('decision')=='INTERESTING' for b in records))

    def test_synthetic_layout_exception_does_not_include_actual_sidebar_or_comments(self):
        html='<main><div class="cs-site-content cs-sidebar-enabled cs-sidebar-right"><div class="entry-content"><p>Company Delta opens a workshop.</p><aside class="sidebar-right"><p>Wrong Company.</p></aside><div class="comments"><p>Wrong commenter.</p></div></div></div></main>'
        original={**page(1882),'html':html};p=evidence.packet(original,document(original))
        text='\n'.join(e['text'] for e in evidence.passages(p,p['units'][0],3000,source_content=True))
        self.assertIn('Company Delta',text)
        self.assertNotIn('Wrong',text)


class QueryDirections(unittest.TestCase):
    def check(self,query,flow):
        proposal={**h.query(query),'strategy':'external_technical_partner'}
        return assess(proposal,flow,['Veneto']),assess_query(proposal,flow,['Veneto'])

    def test_actual_rejected_directions_pass_both_query_layers(self):
        for query,flow in [('"unisciti al team" sviluppatore partita IVA','AGENCIES'),
                           ('site:cofounderslab.com "looking for" technical cofounder','STARTUPS')]:
            for result in self.check(query,flow):self.assertTrue(result['allowed'],result)
        self.assertEqual(self.check('looking for technical cofounder','STARTUPS')[1]['intent'],'entrepreneurial_opportunity')

    def test_generic_founders_courses_sales_and_employee_only_are_not_new_exceptions(self):
        for query,flow in [('looking for cofounder','STARTUPS'),('unisciti al team calcio','AGENCIES'),
                           ('cerchiamo partner commerciale ecommerce','STARTUPS'),
                           ('sviluppatore solo dipendenti','AGENCIES')]:
            self.assertFalse(all(r['allowed'] for r in self.check(query,flow)),query)
        for result in self.check('(looking for technical cofounder OR startup innovative)','STARTUPS'):
            self.assertFalse(result['allowed'])


class CitedLocation(unittest.TestCase):
    def test_actual_street_clause_resolves_without_borrowing_publisher_location(self):
        quote=next(line for line in document(page(1885))['text'].splitlines() if line.startswith('Sabato 7 dicembre'))
        found=resolve_address_quotation(quote)
        self.assertEqual(found['city'],'Bassano del Grappa')
        self.assertEqual(found['region'],'Veneto')
        self.assertIn(found['literal_address'],quote)
        validate_geography({'subject_geography':{'status':'IN_TARGET','region':'Veneto','fact_indices':[0],'reason':'Cited store address'}},
                           [{'field':'geography','quote':quote}],{'allowed_regions':['Veneto']})

    def test_arbitrary_mentions_unknown_or_multiple_addresses_do_not_resolve(self):
        for quote in ('Il sindaco di Bassano del Grappa inaugura lo stabilimento.',
                      'Serviamo clienti a Bassano del Grappa.',
                      'via della Pace 39, a Inventopoli.',
                      'via Roma 1, a Bassano del Grappa. Via Verdi 4, a Milano.',
                      'via Roma 1, a Bassano del Grappa. Via Verdi 4, a Inventopoli.'):
            self.assertIsNone(resolve_address_quotation(quote),quote)

    def test_actual_unchanged_model_response_can_request_the_official_site(self):
        out=json.loads((FIXTURE/'san-rocco-response.json').read_text())['output']
        seen,records,tasks=capture(1885,out)
        self.assertEqual(len(seen),1)
        result,errors=decision.validate(copy.deepcopy(out),seen[0])
        self.assertEqual(errors,[])
        self.assertEqual(result['decision'],'NEEDS_RESEARCH')
        self.assertEqual(result['compensation'],'UNKNOWN')
        self.assertEqual(result['currentness'],'STALE')
        self.assertTrue(any(b.get('decision')=='NEEDS_RESEARCH' for b in records),records)
        self.assertFalse(any(decision.projection(b)['READY_FOR_OUTREACH'] for b in records))
        self.assertTrue(tasks,'A bounded original-site follow-up must remain possible.')


class DeferredCapacity(unittest.TestCase):
    def setUp(self):
        self.base=h.IntegratedPath();self.base.setUp()
        self.addCleanup(self.base.tearDown)
        self.saved=json.loads((FIXTURE/'queue.json').read_text())
        self.campaign={**self.base.c,'filters':self.saved['filters']}
        self.db=self.enterContext(self.base.store.connect())
        self.db.execute('DELETE FROM research_tasks')
        self.db.execute('DELETE FROM commercial_engine_runs')
        for row in self.saved['runs']:
            self.db.execute('INSERT INTO commercial_engine_runs(campaign_id,engine,state) VALUES(?,?,?)',
                            (self.campaign['id'],row['engine'],row['state']))
        for n,row in enumerate(self.saved['tasks']):
            self.db.execute('''INSERT INTO research_tasks
                (campaign_id,kind,strategy,payload,fingerprint,state,available_at,created_at,updated_at)
                VALUES(?,?,?,'{}',?,?,?,?,?)''',
                (self.campaign['id'],row['kind'],row['strategy'],str(n),row['state'],row['available_at'],
                 self.saved['timestamp'],self.saved['timestamp']))

    def capacity(self,timestamp=None,rows=None):
        with patch('sales.agent6.budget.now',return_value=timestamp or self.saved['timestamp']):
            return budget.available(self.db,self.campaign,'NEWS',self.saved['config'],'verify',
                                    self.saved['ledger'] if rows is None else rows)

    def test_real_final_queue_leaves_last_slot_available_before_future_retry(self):
        self.assertEqual(len(self.saved['ledger']),19)
        self.assertEqual(self.capacity(),1)
        self.assertEqual(self.capacity('2026-10-21T03:22:00+00:00'),0)

    def test_running_work_remains_protected_even_with_future_timestamp(self):
        self.db.execute("UPDATE research_tasks SET state='working' WHERE state='pending'")
        self.assertEqual(self.capacity(),0)

    def test_future_screening_does_not_hold_capacity_but_due_screening_does(self):
        self.db.execute("UPDATE research_tasks SET kind='agent_screen' WHERE state='pending'")
        self.assertEqual(self.capacity(),1)
        self.assertEqual(self.capacity('2026-10-21T03:22:00+00:00'),0)

    def test_releasing_reservation_cannot_bypass_shared_or_flow_or_cost_limits(self):
        rows=self.saved['ledger']+[self.saved['ledger'][-1]]
        self.assertEqual(self.capacity(rows=rows),0)
        self.saved['config']['max_calls_per_engine']=5  # NEWS has already used five.
        self.assertEqual(self.capacity(),0)
        self.saved['config']['max_calls_per_engine']=8
        self.saved['config']['max_estimated_cost']=0
        self.assertEqual(self.capacity(),0)


if __name__=='__main__':unittest.main()
