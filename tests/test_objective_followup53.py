"""Actual acquired JobPosting regressions; no network/model results simulated as leads."""
import gzip,json,unittest
import copy
from unittest.mock import patch
from pathlib import Path
from sales.agent6.evidence import packet,passages,job_lines
from sales.agent6.passages import bundle
from sales.commercial.inspection import document
from sales.db import digest

PAGES=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/followup53/originals.json.gz').read_bytes()))
RECEIPTS=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/followup53/receipts.json.gz').read_bytes()))

class JobConditions(unittest.TestCase):
    def test_actual_equity_conditions_and_technical_role_survive_same_budget(self):
        p=PAGES[2];pk=packet(p,document(p));u=pk['units'][0]
        before=bundle([{'id':u['id'],'url':p['url'],'text':u['text'],'original':True}],3000,compact=True)
        self.assertFalse(any('nessuno percepisce uno stipendio' in e['text'] for e in before))
        es=passages(pk,u,3000)
        self.assertLessEqual(sum(len(e['text'].encode()) for e in es),3000)
        self.assertTrue(any('nessuno percepisce uno stipendio' in e['text'] and 'chiusura del primo round' in e['text'] for e in es))
        self.assertTrue(any('React/Next, Supabase/Postgres' in e['text'] and 'Un co-founder tecnico' in e['text'] for e in es))
        self.assertTrue(any('hiringOrganization' in e['text'] and 'applicantLocationRequirements' in e['text'] for e in es))
        for e in es:
            self.assertEqual(e['text'],u['text'][e['offset']:e['offset']+len(e['text'])])
            self.assertEqual(e['hash'],digest(e['text']))
            self.assertEqual(e['document_id'],u['document_id'])

    def test_other_cards_and_synthetic_platform_summary_not_used_as_job_body(self):
        for p in PAGES:
            pk=packet(p,document(p));es=passages(pk,pk['units'][0],3000)
            text='\n'.join(e['text'] for e in es)
            self.assertNotIn('Altri annunci da vedere',text)
            self.assertNotIn('Riassunto generato automaticamente',text)
            self.assertNotIn('Closer Connecting People',text)
            self.assertNotIn('Co-Founder Tecnico per IA Gestionale Rivoluzionaria',text)

    def test_short_structured_jobs_unchanged_and_no_truncated_conditions(self):
        for p in PAGES[:2]:
            pk=packet(p,document(p));u=pk['units'][0];es=passages(pk,u,3000)
            self.assertEqual(len(es),1);self.assertEqual(es[0]['text'],u['text'])
        pk=packet(PAGES[1],document(PAGES[1]))
        self.assertIn('Non sto cercando un programmatore a cui commissionare lo sviluppo',passages(pk,pk['units'][0],3000)[0]['text'])

    def test_escaped_backslash_n_is_not_a_paragraph(self):
        raw=json.dumps({'title':'Example','description':'First literal \\n path.\nSecond paragraph.\n\nNo salary.',
                        'hiringOrganization':{'name':'Owner'}},indent=2)
        parts=[raw[a:b] for a,b in job_lines(raw)]
        self.assertTrue(any('First literal \\\\n path.' in t for t in parts))
        self.assertTrue(any(t=='Second paragraph.' for t in parts))
        self.assertTrue(any('hiringOrganization' in t and 'Owner' in t for t in parts))
        for a,b in job_lines(raw):self.assertTrue(raw[a:b].strip())

    def test_two_job_units_never_lend_conditions_to_each_other(self):
        first={'@type':'JobPosting','title':'Paid role','description':'Developer project with salary.'}
        second={'@type':'JobPosting','title':'Other role','description':'No salary. Equity only.'}
        p={'url':'https://example.org/jobs','html':'<script type="application/ld+json">'+json.dumps([first,second])+'</script>',
           'status':200,'checked_at':'2026-10-21T00:00:00+00:00','content_type':'text/html'}
        pk=packet(p,document(p));self.assertEqual(len(pk['units']),2)
        self.assertNotIn('No salary',passages(pk,pk['units'][0],3000)[0]['text'])
        self.assertIn('No salary',passages(pk,pk['units'][1],3000)[0]['text'])


class ActualValidation(unittest.TestCase):
    def test_real_country_property_accepted_without_changing_model_decisions(self):
        from sales.agent6.decision import validate
        for i in (1,2):
            p=RECEIPTS['inputs'][i]['payload'];raw=RECEIPTS['answers'][i]['model_output']
            o,_=validate(raw,p)
            self.assertEqual(o['decision'],'NOT_INTERESTING')
            self.assertEqual(o['subject_geography']['status'],'REMOTE_ITALY')
        self.assertEqual(o['compensation'],'EQUITY_ONLY')

    def test_old_request_still_invalid_but_not_offered_in_new_schema(self):
        from sales.agent6.decision import validate
        from sales.commercial.ai_tasks import request_schema
        p=RECEIPTS['inputs'][0]['payload']
        with self.assertRaisesRegex(ValueError,'unproven_request_currentness'):
            validate(RECEIPTS['answers'][0]['model_output'],p)
        self.assertNotIn('RECENT_REQUEST',request_schema(p)['properties']['currentness']['enum'])
        for dates in ([],[{'role':'modified_at','value':p['observed_at'][:10]}],
                      [{'role':'published_at','value':'2027-01-01'}]):
            self.assertNotIn('RECENT_REQUEST',request_schema({**p,'dates':dates})['properties']['currentness']['enum'])
        q={**p,'dates':[{'role':'published_at','value':p['observed_at'][:10]}]}
        self.assertIn('RECENT_REQUEST',request_schema(q)['properties']['currentness']['enum'])
        q['dates'].append({'role':'expires_at','value':'2020-01-01'})
        self.assertNotIn('RECENT_REQUEST',request_schema(q)['properties']['currentness']['enum'])

    def test_structured_country_requires_job_property_and_cited_same_document(self):
        from sales.agent6.subject_geography import structured_remote
        from sales.agent6.decision import validate
        from sales.agent6.schema import quote
        from sales.agent6.grounding import resolve
        p=RECEIPTS['inputs'][1]['payload'];o,_=validate(RECEIPTS['answers'][1]['model_output'],p)
        allfacts=[{'field':f['field'],**quote(resolve({'segment_id':f['segment_id']},p['evidence']),p['evidence'])} for f in o['facts']]
        facts=[allfacts[i] for i in o['subject_geography']['fact_indices']]
        self.assertTrue(structured_remote(facts,p))
        for metadata in ({},{'origin':'page'}):
            self.assertFalse(structured_remote(facts,{**p,'metadata':metadata}))
        for field in ('document_id','url'):
            altered=copy.deepcopy(facts);altered[-1][field]='another-source'
            self.assertFalse(structured_remote(altered,p))
        self.assertFalse(structured_remote(facts[:1],p))
        self.assertFalse(structured_remote(facts,{**p,'unit_id':'another-job'}))
        # A name=IT under a hiringOrganization is not applicant eligibility.
        changed=copy.deepcopy(p)
        for e in changed['evidence']:
            e['text']=e['text'].replace('applicantLocationRequirements','hiringOrganization')
        self.assertFalse(structured_remote(facts,changed))

    def test_hiring_address_and_uncited_italian_alternative_cannot_authorize_remote(self):
        from sales.agent6.subject_geography import structured_remote
        text='  "jobLocationType": "TELECOMMUTE",\n  "hiringOrganization": {"addressCountry":"IT"},\n  "applicantLocationRequirements": [{"@type":"Country","name":"DE"},{"@type":"Country","name":"IT"}]'
        def fact(fragment):
            a=text.index(fragment);return {'quote':fragment,'url':'https://example.org/job',
                'document_id':'d','document_start':a,'document_end':a+len(fragment)}
        p={'metadata':{'origin':'JobPosting'},'unit_id':'u','evidence':[{'text':text,'url':'https://example.org/job','document_id':'d','unit_id':'u','original':True}]}
        remote=fact('"jobLocationType": "TELECOMMUTE"')
        self.assertFalse(structured_remote([remote,fact('"addressCountry":"IT"')],p))
        self.assertFalse(structured_remote([remote,fact('"name":"DE"')],p))
        self.assertTrue(structured_remote([remote,fact('"name":"IT"')],p))


class SubjectLookupContext(unittest.TestCase):
    def test_search_action_propagates_owner_context_through_discovery_queue(self):
        import test_ai_first as h
        b=h.IntegratedPath();b.setUp()
        try:
            b.c['filters']['commercial']['ai']['max_input_tokens']=20480
            page={'url':'https://alfa.example/collabora','html':'<html><title>Alfa Srl</title><body>'+''.join('<p>'+t+'</p>' for t in h.TEXT.splitlines())+'</body></html>',
                  'status':200,'checked_at':h.DATE,'content_type':'text/html'}
            b.w.enqueue('candidate','AGENCIES',{'url':page['url'],'original_page':page,'depth':0},'first')
            def task(key):
                with b.store.connect() as db:r=db.execute('SELECT * FROM research_tasks WHERE fingerprint=?',(key,)).fetchone()
                return {**dict(r),'payload':json.loads(r['payload'])}
            def provider(p,c,g):
                out=h.response(p);out['decision']='NEEDS_RESEARCH'
                out['action']={'type':'SEARCH_SUBJECT','query':'"Alfa Srl" freelance WordPress','link_id':'',
                               'question':'La collaborazione risulta aperta anche sul sito attuale?'}
                return {'output':out,'usage':{'input_tokens':100,'output_tokens':100}}
            identity={'identity_status':'verified','name':'Alfa Srl','website':page['url'],'contacts':[]}
            with patch('sales.agent6.ai.infer',side_effect=provider),patch('sales.agent6.research.identity_from',return_value=identity):
                b.w.execute(task('first'),lambda:None)
            with b.store.connect() as db:r=db.execute("SELECT * FROM research_tasks WHERE kind='search'").fetchone()
            self.assertIsNotNone(r)
            search={**dict(r),'payload':json.loads(r['payload'])};parent=search['payload']['research_parent']
            self.assertEqual(parent['lookup_domain'],'alfa.example');self.assertNotIn('link_url',parent)
            self.assertEqual(search['payload']['subject_lookup_context']['purpose'],'verify_external_collaboration')
            with patch('sales.agent6.research.acquire',return_value=[{'url':'https://alfa.example/careers','title':'Alfa Srl careers','content':'Official careers'}]):
                b.w.execute(search,lambda:None)
            with b.store.connect() as db:
                candidates=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='candidate'")]
            found=next(p for p in candidates if p['url']=='https://alfa.example/careers')
            self.assertEqual(found['research_parent'],parent)
        finally:b.tearDown()

    def capture(self,domain='sinfonialab.it',name='Sinfonia sc'):
        import test_ai_first as h
        from test_objective_source53 import PAGES as saved
        old=saved[0];pk=packet(old,document(old))
        page=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/followup53/sinfonia-page.json.gz').read_bytes()))
        b=h.IntegratedPath();b.setUp()
        try:
            b.c['filters']['commercial']['ai']['max_input_tokens']=20480
            data={'url':page['url'],'original_page':page,'depth':1,'query':'Sinfonia sc freelance',
                  'research_parent':{'url':old['url'],'title':pk['title'],'unit':pk['units'][0],
                  'packet':{k:pk[k] for k in ('document_id','final_url','observed_at')},
                  'entity_name':name,'lookup_domain':domain,'provenance':'verified_owner_subject_lookup'}}
            b.w.enqueue('candidate','AGENCIES',data,'lookup')
            with b.store.connect() as db:
                r=db.execute("SELECT * FROM research_tasks WHERE fingerprint='lookup'").fetchone()
                task={**dict(r),'payload':json.loads(r['payload'])}
            seen=[]
            def provider(p,c,g):seen.append(copy.deepcopy(p));return {'output':{},'usage':{}}
            with patch('sales.agent6.ai.infer',side_effect=provider),patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No network')):
                b.w.execute(task,lambda:None)
            self.assertEqual(len(seen),1)
            return seen[0],old,page
        finally:b.tearDown()

    def test_verified_subject_search_keeps_two_originals_without_inventing_a_link(self):
        p,old,new=self.capture()
        self.assertTrue(any(e['url']==old['url'] for e in p['evidence']))
        self.assertTrue(any(e['url']==new['url'] for e in p['evidence']))
        self.assertEqual(len({e['unit_id'] for e in p['evidence']}),1)
        self.assertGreater(len({e['document_id'] for e in p['evidence']}),1)

    def test_another_domain_or_owner_cannot_borrow_the_original_request(self):
        for domain,name in [('publisher.example','Sinfonia sc'),('sinfonialab.it','Unrelated Srl')]:
            p,old,new=self.capture(domain,name)
            self.assertFalse(any(e['url']==old['url'] for e in p['evidence']))
            self.assertTrue(any(e['url']==new['url'] for e in p['evidence']))
