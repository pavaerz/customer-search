"""Temporary SQLite integration; historical snapshots; no external I/O."""
import copy
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.audit_memory import reusable
from sales.commercial.coordinator import campaign_counts
from sales.commercial.presentation import lead_type
from scripts.replay_commercial3b5 import load


class Memory35(CommercialTestCase):
    def agency(self,text,url):
        return self.inspect(page('Siamo una web agency. '+text,url=url,title='Alfa Srl web agency',date=False),'AGENCIES')

    def test_generic_partner_pages_one_company_one_opportunity(self):
        ids=[]
        for path in ['/partner/','/collabora-con-noi/']:
            found=self.agency('Accettiamo collaborazioni continuative con sviluppatori WordPress freelance.','https://alfa.example'+path)
            ids.append(self.repo.save(self.c,found['identity'],found['documents'],found['result']))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(len(self.repo.get(ids[0])['revisions']),2)

    def test_distinct_explicit_jobs_not_merged(self):
        ids=[]
        for skill in ['WordPress','frontend']:
            found=self.agency('Cerchiamo sviluppatore '+skill+' freelance per questa posizione.','https://alfa.example/jobs/'+skill)
            ids.append(self.repo.save(self.c,found['identity'],found['documents'],found['result']))
        self.assertNotEqual(ids[0],ids[1])

    def test_reuse_same_campaign_documents_only_and_preserve_audit(self):
        found=self.inspect(page('Produciamo serramenti su misura.'),'WEBSITE_REBUILD')
        report={'completed':False,'outcome':'partial','resources_closed':True,'resource_requests':2,'pages':[{'url':found['result']['url'],'viewport':390,'complete':False}],'findings':[]}
        found['result']['browser']=report;found['result']['browser_outcome']='partial'
        oid=self.repo.save(self.c,found['identity'],found['documents'],found['result'])
        prior=self.repo.get(oid)['latest_revision']
        kept=reusable(self.store,found['identity'],found['documents'],self.c['id'])
        self.assertEqual(kept['reused_revision_id'],prior);self.assertFalse(kept['new_browser_execution'])
        modified=copy.deepcopy(found['documents']);modified[0]['content_hash']='changed'
        self.assertIsNone(reusable(self.store,found['identity'],modified,self.c['id']))
        self.assertIsNone(reusable(self.store,found['identity'],found['documents'],self.c['id']+1))
        self.assertIsNone(reusable(self.store,{**found['identity'],'identity_status':'unknown'},found['documents'],self.c['id']))
        found['result'].update(browser={},browser_outcome='budget_deferred',reason='Budget deferred; no new audit.')
        self.repo.save(self.c,found['identity'],found['documents'],found['result'])
        item=self.repo.get(oid);self.assertNotEqual(item['latest_revision'],prior)
        self.assertEqual(item['evidence_history']['latest_audit']['revision_id'],prior)
        totals=campaign_counts(self.store,self.c['id'])['browser_history_counts']
        self.assertEqual(totals,{'executed':1,'complete':0,'incomplete':1,'reused':0})

    def test_resume_identical_result_does_not_duplicate(self):
        f=self.agency('Accettiamo collaborazioni WordPress freelance.','https://alfa.example/partner/')
        oid=self.repo.save(self.c,f['identity'],f['documents'],f['result'])
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);resumed=self.rs.resume(self.c['id'])
        self.assertEqual(self.repo.save(resumed,f['identity'],f['documents'],f['result']),oid)
        self.assertEqual(len(self.repo.get(oid)['revisions']),1)

    def test_italiaonline_historical_subject_identity_shared(self):
        x=load();rows=[r for r in x['commercial_revisions'] if r['id'] in (895,902)]
        self.assertEqual(len(rows),2)
        opportunities={r['id']:r for r in x['opportunities']}
        self.assertEqual(len({opportunities[r['opportunity_id']]['entity_id'] for r in rows}),1)
        self.assertEqual(len({r['opportunity_id'] for r in rows}),2)  # Legacy records remain untouched.

    def test_legacy_amts_read_profile_not_commercial_lead(self):
        r=next(r for r in load()['commercial_revisions'] if r['id']==891)
        self.assertEqual(lead_type(r['body'])['type'],'DATA_QUALITY_REVIEW')

    def test_structured_multiple_employers_never_borrow_addresses(self):
        import json
        from sales.commercial.attribution import identity
        from sales.commercial.geography import locate
        jobs=[{'@type':'JobPosting','title':'WordPress freelance','hiringOrganization':{'@type':'Organization','name':n,'url':'https://'+n+'.example'},'jobLocation':{'@type':'Place','address':{'addressLocality':'Milano','addressCountry':'IT'}}} for n in ['Beta','Gamma']]
        p=page('Portale offerte',extra='<script type="application/ld+json">'+json.dumps(jobs)+'</script>')
        i=identity([p]);self.assertEqual(i['attribution']['role'],'ACTOR_UNRESOLVED');self.assertEqual(i['contacts'],[])
        self.assertEqual(locate([p],i)['locations'],[])
