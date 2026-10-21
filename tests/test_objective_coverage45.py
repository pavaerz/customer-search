"""Saved Rechsteiner evidence + offline transport/UI doubles, not new AI results."""
import copy
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import decision, memory
from sales.agent6.verification_coverage import context, apply
from sales.agent6.semantics import decision_metadata

REAL=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign45/partial-browser.json').read_text())['body']
QUESTION='Verificare il percorso di prenotazione su telefono.'


class CoverageContract(unittest.TestCase):
    def test_real_saved_case_is_unfinished_not_a_negative_company(self):
        before=copy.deepcopy(REAL)
        result=apply(REAL,context(True,QUESTION,REAL['website_audit']))
        self.assertEqual(REAL,before)
        self.assertEqual(result['decision'],'NOT_INTERESTING')  # Original AI unchanged.
        self.assertEqual(result['ai_decision'],REAL['ai_decision'])
        self.assertEqual(result['state'],'UNVERIFIABLE')
        self.assertEqual(result['workflow_state'],'VERIFICATION_INCOMPLETE')
        self.assertFalse(decision_metadata(result)['negative_feedback_reliable'])
        view=decision.enrich(result)
        self.assertEqual(view['commercial_alignment']['COMMERCIAL_INTEREST'],'UNKNOWN')
        self.assertFalse(view['commercial_alignment']['READY_FOR_OUTREACH'])
        self.assertFalse(view['completion_queue']['promising'])

    def test_unread_booking_link_and_zero_viewports_are_explicit(self):
        coverage=context(True,QUESTION,REAL['website_audit'])
        self.assertEqual(coverage['browser_status'],'PARTIAL')
        self.assertEqual(coverage['completed_viewports'],[])
        self.assertTrue(coverage['external_solutions'])
        self.assertTrue(all(not s['content_read'] and s['adequacy']=='UNKNOWN' for s in coverage['external_solutions']))
        self.assertIn('responsive',coverage['unmeasured_controls'])
        self.assertIn('form_delivery',coverage['unmeasured_controls'])

    def test_independent_exclusions_and_small_tasks_keep_their_meaning(self):
        coverage=context(True,QUESTION,REAL['website_audit'])
        variants=[{'commercial_exclusions':['PA']},{'suppressed':True},
                  {'facts':[{'field':'closed','quote':'Chiusa'}]}]
        for intent in ('EMPLOYEE_ONLY','SUPPLYING_SERVICES','TRAINING','COMPLETED_PROJECT'):
            variants.append({'commercial_assessment':{**REAL['commercial_assessment'],'intent':intent}})
        variants.append({'commercial_assessment':{**REAL['commercial_assessment'],'scope':'SMALL_TASK'}})
        for change in variants:
            result=apply({**REAL,**change},coverage)
            self.assertFalse(result.get('verification_hold'),change)
            self.assertEqual(result['state'],'REJECTED')

    def test_valid_independent_positive_and_complete_browser_not_reclassified(self):
        for body,coverage in (
            ({**REAL,'decision':'INTERESTING','state':'POTENTIAL'},context(True,QUESTION,REAL['website_audit'])),
            (REAL,context(True,QUESTION,{'browser_status':'COMPLETE'})),
            (REAL,context(False,QUESTION,REAL['website_audit'])),
        ):
            result=apply(body,coverage)
            self.assertEqual(result['state'],body['state'])
            self.assertFalse(result.get('verification_hold'))

    def test_historical_enrichment_does_not_apply_new_hold(self):
        result=decision.enrich(REAL)
        self.assertEqual(result['state'],'REJECTED')
        self.assertFalse(result.get('verification_hold'))

    def test_missing_browser_execution_is_not_a_clean_inspection(self):
        result=apply(REAL,context(True,QUESTION,None))
        self.assertTrue(result['verification_hold'])
        self.assertEqual(result['verification_coverage']['browser_status'],'NOT_EXECUTED')

    def test_notice_escapes_source_text_and_retains_raw_ai_reason(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/worklist.js','utf8');
const start=source.indexOf('function agentCommercialAssessment('),end=source.indexOf('\nconst agent8CorrectionOptions',start);
const ctx={esc:s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'),link:()=>''};
vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
const html=ctx.agentCommercialAssessment({verification_hold:true,
 commercial_assessment:{intent:'COMPANY_ACTIVITY',scope:'UNKNOWN',existing_solution:'NOT_CHECKED',interpretation:'HTML letto'},
 verification_coverage:{question:'Prenotazione <img>'},ai_decision:{reason:'Ipotesi <script>'}});
assert(html.includes('Verifica non conclusa'));assert(html.includes('Interpretazione AI precedente'));
assert(!html.includes('<img>'));assert(!html.includes('<script>'));
for(const name of ['static/agent6.js','static/worklist.js']) {
 const s=fs.readFileSync(name,'utf8');assert(s.includes("b.verification_hold?'Verifica non conclusa'"));
}
'''
        subprocess.run(['node'],input=script,text=True,check=True,capture_output=True)


class PipelineCoverage(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath();self.base.setUp()

    def tearDown(self):self.base.tearDown()

    def test_held_case_visible_for_review_and_manual_exclusion_preserved(self):
        from sales.agent6.worklist import listing
        b=self.base
        body=apply({**decision.base({'url':REAL['url']},'AZIENDE'),**copy.deepcopy(REAL)},
                   context(True,QUESTION,REAL['website_audit']))
        rid=memory.save_record(b.store,b.c,'AZIENDE',body)
        result=listing(b.store,{'view':'review'})
        self.assertTrue(any(r['id']==rid for r in result['items']))
        self.assertEqual(listing(b.store,{'view':'ready'})['total'],0)
        # A human exclusion remains authoritative; no technical hold restores it.
        memory.feedback(b.store,rid,'not_interesting','Fuori dal mio target')
        self.assertEqual(listing(b.store,{'view':'review'})['total'],0)
        self.assertEqual(listing(b.store,{'view':'excluded'})['total'],1)

    def test_requested_partial_browser_reaches_ai_and_saved_state(self):
        b=self.base;captured=[]
        page={'url':'https://alfa.example/collabora','status':200,'checked_at':harness.DATE,
              'content_type':'text/html','html':'<html><title>Alfa Srl</title><body>'+''.join('<p>'+line+'</p>' for line in harness.TEXT.splitlines())+'</body></html>'}
        identity={'identity_status':'verified','name':'Alfa Srl','website':page['url'],'contacts':[]}
        p={'url':page['url'],'title':'Alfa','query':'Alfa sito ufficiale','strategy':'official_company_sector_region',
           'original_page':page,'browser_requested':True,'research_question':QUESTION,'depth':1}
        b.w.enqueue('candidate','AGENCIES',p,'coverage-test')
        with b.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='coverage-test'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        def provider(payload,cfg,check):
            captured.append(payload)
            out=harness.response(payload)
            out.update(decision='NOT_INTERESTING',relationship='BUSINESS_SIGNAL',currentness='CURRENT_OBSERVATION',
                       reason='Nessuna lacuna dimostrata.',action={'type':'STOP','query':'','link_id':'','question':''})
            out['assessment'].update(intent='COMPANY_ACTIVITY',scope='UNKNOWN',existing_solution='NOT_CHECKED')
            return {'output':out,'usage':{'input_tokens':100,'output_tokens':100}}
        with patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Use saved original')),patch(
                'sales.agent6.research.identity_from',return_value=identity),patch(
                'sales.agent6.research.locate',return_value={'eligible':True,'regions':['Veneto'],'remote_italy':False}),patch(
                'sales.commercial.browser.review',return_value={'completed':False,'pages':[{'url':page['url'],'complete':False,'viewport':390}],'limits':['timeout']}),patch(
                'sales.agent6.ai.infer',side_effect=provider):
            b.w.execute(task,lambda:None)
        self.assertEqual(len(captured),1)
        self.assertEqual(captured[0]['verification_coverage']['browser_status'],'PARTIAL')
        with b.store.connect() as db:
            saved=json.loads(db.execute('SELECT body FROM agent6_records').fetchone()[0])
        self.assertEqual(saved['ai_status'],'completed')
        self.assertEqual(saved['state'],'UNVERIFIABLE')
        self.assertTrue(saved['verification_hold'])
        self.assertEqual(saved['ai_decision']['reason'],'Nessuna lacuna dimostrata.')

    def test_completed_later_check_replaces_hold_without_changing_previous_revision(self):
        b=self.base
        original={**decision.base({'url':REAL['url']},'AZIENDE'),**copy.deepcopy(REAL)}
        held=apply(original,context(True,QUESTION,REAL['website_audit']))
        rid=memory.save_record(b.store,b.c,'AZIENDE',held)
        completed=apply(original,context(True,QUESTION,{'browser_status':'COMPLETE'}))
        self.assertEqual(memory.save_record(b.store,b.c,'AZIENDE',completed),rid)
        with b.store.connect() as db:
            record=json.loads(db.execute('SELECT body FROM agent6_records WHERE id=?',(rid,)).fetchone()[0])
            revisions=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_record_revisions WHERE record_id=? ORDER BY id',(rid,))]
        self.assertEqual(record['state'],'REJECTED')
        self.assertFalse(record.get('verification_hold'))
        self.assertTrue(revisions[0]['verification_hold'])
        self.assertEqual(len(revisions),2)
