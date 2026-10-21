"""Frozen agency evidence and synthetic isolated queues; no live research."""
import copy
import json
import unittest
from unittest.mock import patch

from scripts.replay_agent91 import load, replay_case
from sales.agent6 import budget, commercial_policy, qualification, scheduling
from sales.db import now
from test_agent6 import source, output, identity
import test_agent6_campaign32 as support


class MissingChecks(unittest.TestCase):
    def test_saved_invitation_resolves_known_location_not_unknown_currentness(self):
        case=next(c for c in load()['cases'] if c['record']['id']==369)
        before=copy.deepcopy(case)
        with patch('socket.create_connection',side_effect=AssertionError('Frozen evidence only')):
            body=replay_case(case)
        self.assertEqual(case,before)
        self.assertEqual(body['missing'],['closed','publication'])
        self.assertTrue(body['collaboration_geography']['eligible'])
        self.assertTrue(body['requirement_resolution']['geography']['previously_missing'])
        self.assertEqual(body['state'],'NEEDS_REVIEW')
        self.assertEqual(body['budget']['kind'],'UNKNOWN')
        self.assertEqual(body['completion_queue']['current_availability'],'UNKNOWN')
        goal=commercial_policy.investigation(body)['goal']
        self.assertEqual(goal,'publication')
        query=commercial_policy.verification_query(body,goal)
        self.assertIn('site:kondividi.it',query)
        self.assertIn('collabora con noi',query)
        self.assertNotIn('Italy eligibility',query)

    def agency(self,request=None,extra='',missing=(),ident=True):
        request=request or 'Siamo sempre alla ricerca di professionisti freelance WordPress per web design. Remote from Italy.'
        src=source('Alfa Srl\n'+request+'\n'+extra)
        p,o=output(src,'AGENCY_PARTNERSHIP',{'entity':'Alfa Srl','request':request,
            'technical':'WordPress','contract':'freelance','geography':'Remote from Italy.'})
        a=o['analyses'][0];a['missing']=list(missing)
        return qualification.evaluate(src,a,p['evidence'],'AGENCIES',identity() if ident else {})

    def test_standing_invitation_does_not_gain_currentness_when_model_omits_missing(self):
        body=self.agency()
        self.assertEqual(body['state'],'NEEDS_REVIEW')
        self.assertIn('publication',body['missing'])

    def test_dated_invitation_can_resolve_model_missing_publication(self):
        body=self.agency(extra='Posted 2 days ago',missing=['publication'])
        self.assertNotIn('publication',body['missing'])
        self.assertEqual(body['state'],'POTENTIAL')

    def test_unverified_owner_cannot_clear_identity_or_project_checks(self):
        body=self.agency(missing=['entity','scope','feasibility'],ident=False)
        self.assertTrue({'entity','scope','feasibility'}<=set(body['missing']))
        self.assertFalse(body['identity_verified'])

    def test_webapp_scope_and_feasibility_are_still_required(self):
        request='Siamo sempre alla ricerca di professionisti freelance WordPress per una piattaforma MVP. Remote from Italy.'
        body=self.agency(request,missing=['scope','feasibility'])
        self.assertIn('feasibility',body['missing'])
        self.assertEqual(body['feasibility']['status'],'UNKNOWN')
        self.assertIn('scope',body['missing'])

    def test_closed_source_cannot_be_reopened_by_missing_reconciliation(self):
        body=self.agency(extra='Applications closed.',missing=['closed'])
        self.assertEqual(body['state'],'REJECTED')
        self.assertIn('closed_request',body['counterevidence'])

    def test_named_project_cannot_discard_scope_as_standing_partnership(self):
        body=self.agency('Cerchiamo freelance WordPress per un nuovo sito. Remote from Italy.',missing=['scope'])
        self.assertIn('scope',body['missing'])

    def test_careers_link_is_relevant_but_similar_jobs_remain_excluded(self):
        page={'url':'https://alfa.example/','html':'<a href="/collabora">Collabora con noi</a>'
            '<a href="/other">Related careers</a>'}
        links=qualification.followup_links(page)
        self.assertEqual([l['label'] for l in links],['Collabora con noi'])

    def test_unverified_domain_does_not_constrain_followup(self):
        b={'entity_name':'Alfa Srl','official_domain':'https://publisher.example/','identity_verified':False}
        self.assertEqual(commercial_policy.verification_query(b,'official_domain'),'"Alfa Srl" sito ufficiale contatti')

    def test_standing_phrase_in_other_field_does_not_validate_a_generic_request(self):
        src=source('Alfa Srl\nPosted 2 days ago\nProgetti digitali per aziende.\n'
                   'Siamo sempre alla ricerca di professionisti freelance WordPress. Remote from Italy.')
        p,o=output(src,'AGENCY_PARTNERSHIP',{'entity':'Alfa Srl','request':'Progetti digitali per aziende.',
            'technical':'Siamo sempre alla ricerca di professionisti freelance WordPress.',
            'contract':'freelance','geography':'Remote from Italy.'})
        # Exercise the gate directly: deterministic completion must not silently
        # replace this deliberately unrelated request in this unit test.
        body=qualification._evaluate(src,o['analyses'][0],p['evidence'],'AGENCIES',identity())
        self.assertIn('request',body['missing'])
        self.assertNotIn(body['state'],('POTENTIAL','VERIFIED'))


class CompletionQueue(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp();self.addCleanup(self.base.tearDown)
        self.store,self.rs,self.c=self.base.store,self.base.rs,self.base.c

    def add(self,kind,flow,payload):
        self.rs.enqueue(self.c['id'],kind,flow,payload)

    def test_targeted_search_and_screen_hold_replanning_without_changing_accounting(self):
        for kind,payload in [('search',{'selection':'verification'}),
                             ('agent_screen',{'parent':{'selection':'verification'}})]:
            with self.subTest(kind=kind):
                self.add(kind,'AGENCIES',payload)
                with self.store.connect() as c:
                    hold=scheduling.planning_hold(c,self.c,'AZIENDE',now())
                    self.assertEqual(hold['flows'],['AGENCIES'])
                    cfg=self.c['filters']['commercial']['ai']
                    self.assertEqual(budget.available(c,self.c,'AGENCIES',cfg,'replan',[]),0)
                    self.assertGreater(budget.available(c,self.c,'AGENCIES',cfg,'screen',[]),0)
                    _,trace=scheduling.choose(c,self.c,now())
                    self.assertTrue(trace['completion_path']);self.assertEqual(trace['stage'],'screen')
                    c.execute("UPDATE research_tasks SET state='done'")
                self.assertEqual(budget.stage_for('batch:followup',support.screen_payload()),'screen')

    def test_original_precedes_unrelated_plan_even_when_other_flow_has_fewer_turns(self):
        self.add('candidate','AGENCIES',{'original_page':{'url':'https://alfa.example/'}})
        self.add('agent_plan','STARTUPS',{'round':1})
        with self.store.connect() as c:
            c.execute("UPDATE research_tasks SET attempts=9 WHERE strategy='AGENCIES'")
            _,trace=scheduling.choose(c,self.c,now())
        self.assertEqual(trace['flow'],'AGENCIES');self.assertTrue(trace['original_saved'])

    def test_atomic_reservation_defers_plan_but_records_followup_screen_as_screen(self):
        self.add('search','AGENCIES',{'selection':'verification'})
        with patch('socket.create_connection',side_effect=AssertionError('Offline only')):
            blocked=self.base.call('AGENCIES','plan:1',support.plan_payload('AGENCIES',1))
            self.assertEqual(blocked['error'],'capacity_reserved_for_pending_work')
            screen=self.base.call('AGENCIES','batch:followup',support.screen_payload())
            self.assertEqual(screen['status'],'completed')
        with self.store.connect() as c:
            calls=c.execute('SELECT body FROM commercial_ai_executions WHERE attempt=1').fetchall()
            self.assertEqual(len(calls),1)
            self.assertEqual(json.loads(calls[0][0])['stage'],'screen')

    def test_delayed_failed_or_budget_blocked_followup_does_not_hold_planning(self):
        self.add('search','AGENCIES',{'selection':'verification'})
        with self.store.connect() as c:
            c.execute("UPDATE research_tasks SET available_at='2999-01-01'")
            self.assertIsNone(scheduling.planning_hold(c,self.c,'AZIENDE',now()))
            c.execute("UPDATE research_tasks SET state='failed',available_at=?",(now(),))
            self.assertIsNone(scheduling.planning_hold(c,self.c,'AZIENDE',now()))
            c.execute("UPDATE research_tasks SET state='pending'")
            cfg={**self.c['filters']['commercial']['ai'],'max_calls_per_engine':0}
            self.assertEqual(scheduling.pending_verification(c,self.c,cfg,[],now()),[])

    def test_saved_agency_queues_one_targeted_currentness_check_and_stop_preserves_it(self):
        body=replay_case(next(c for c in load()['cases'] if c['record']['id']==369))
        with patch('socket.create_connection',side_effect=AssertionError('Queue only')):
            for _ in range(2):self.base.w.investigate('AGENCIES',body,{'depth':0})
        with self.store.connect() as c:
            rows=c.execute("SELECT payload FROM research_tasks WHERE kind='search'").fetchall()
            self.assertEqual(len(rows),1);p=json.loads(rows[0][0])
            self.assertEqual(p['missing'],'publication');self.assertIn('site:kondividi.it',p['query'])
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions').fetchone()[0],0)
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.assertIsNone(self.rs.claim(self.c['id'],self.c['generation']))
        resumed=self.rs.resume(self.c['id']);task=self.rs.claim(resumed['id'],resumed['generation'])
        self.assertEqual(task['payload']['missing'],'publication')


if __name__=='__main__':unittest.main()
