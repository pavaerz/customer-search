"""3B deterministic regression: saved historical evidence + separate synthetic examples."""
import gzip,json,unittest
from pathlib import Path
from sales.commercial.discovery import assess
from sales.commercial.indexed_jobs import parse_indexed_job,resolution,resolution_continuity
from sales.commercial.intent import classify_block,request_nature
from sales.commercial.qualification import evaluate
from sales.commercial.planner import choose,cache_decision
from sales.commercial.catalog import plan,ENGINES
from sales.commercial.geography import REGIONS
from sales.commercial.context import channels
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.coordinator import Coordinator

FOLDER=Path(__file__).parent/'fixtures/commercial3b'
with gzip.open(FOLDER/'campaign15.json.gz','rt') as f:SAVED=json.load(f)
with gzip.open(FOLDER/'campaign15-pages.json.gz','rt') as f:PAGES=json.load(f)['pages']
def revision(n):return next(r['body'] for r in SAVED['commercial_revisions'] if r['id']==n)

class Deterministic3BTests(unittest.TestCase):
    def test_saved_diegohelp_is_editorial_with_bounded_policy_proof(self):
        old=revision(760);p=PAGES[old['url']];r=evaluate('STARTUPS',old['identity'],p,old['geography'])
        self.assertEqual(r['state'],'REJECTED');self.assertEqual(r['commercial_intent']['commercial_role'],'EDITORIAL')
        self.assertEqual(r['commercial_intent']['request_nature'],'EDITORIAL_INFORMATION')
        self.assertFalse(r['verification']['request_verified']);self.assertTrue(r['verification']['extraction_complete'])
        hint=r['partner_hint'];self.assertFalse(hint['current_open_request'])
        self.assertLess(max(len(e['quote']) for e in hint['evidence']),1000)
        for e in hint['evidence']:self.assertEqual(e['quote'],channels(p)[e['channel']]['text'][e['start']:e['end']])
    def test_saved_kforge_direction_preserved(self):
        old=revision(757);r=evaluate('AGENCIES',old['identity'],PAGES[old['url']],old['geography'])
        self.assertEqual(r['state'],'REJECTED');self.assertEqual(r['commercial_intent']['commercial_role'],'PARTNERSHIP_SELLER')
    def test_saved_digisourced_does_not_request_paid_resolution(self):
        item=revision(770)['discovery'];self.assertFalse(parse_indexed_job(item)['commercial_compatibility']);self.assertIsNone(resolution(item))
        self.assertIsNotNone(resolution(revision(768)['discovery']))
    def test_synthetic_mixed_web_role_not_blacklisted_by_embedded_word(self):
        item={'title':'Frontend developer for embedded dashboards at Alfa','url':'https://linkedin.com/jobs/view/123','content':'Firmware team interface, JavaScript web UI.'}
        self.assertIsNot(parse_indexed_job(item)['commercial_compatibility'],False);self.assertIsNotNone(resolution(item))
    def test_synthetic_policies_are_not_current_requests(self):
        for text,nature in [('Collaboriamo con sviluppatori WordPress freelance quando abbiamo bisogno di competenze specifiche.','GENERAL_COLLABORATION_POLICY'),('Abbiamo collaborato con sviluppatori WordPress freelance in passato.','PAST_COLLABORATION'),('In futuro potremmo collaborare con freelance WordPress.','FUTURE_INTEREST')]:
            r=classify_block(text);self.assertEqual(request_nature(text),nature);self.assertFalse(r['buyer_evidence'])
    def test_synthetic_real_buyer_and_invitation_survive(self):
        for text in ('Cerchiamo uno sviluppatore WordPress freelance per un progetto.','Accettiamo collaborazioni continuative con sviluppatori WordPress freelance.'):
            self.assertTrue(classify_block(text)['buyer_evidence'])
    def test_synthetic_editorial_rules_not_domain_blacklist(self):
        self.assertEqual(assess({'url':'https://example.test/come-trovare-un-freelance','title':'Come trovare uno sviluppatore freelance'},'STARTUPS')['decision'],'exclude')
        self.assertEqual(assess({'url':'https://blog.diegohelp.com/jobs/wordpress','title':'Cerchiamo sviluppatore WordPress freelance'},'FREELANCE')['decision'],'admit')
    def test_saved_industrial_supplier_survives_rebuild_preflight(self):
        items=[r['body'] for r in SAVED['commercial_discovery'] if 'csi-servizi.it' in r['url']]
        self.assertTrue(items)
        for item in items:self.assertEqual(assess(item,'WEBSITE_REBUILD')['decision'],'admit')
    def test_synthetic_industrial_seller_is_not_web_supplier(self):
        item={'url':'https://factory.example/servizi/','title':'Offriamo servizi industriali e manutenzione impianti'}
        self.assertEqual(assess(item,'WEBSITE_REBUILD')['decision'],'admit')
        item['title']='Offriamo servizi di sviluppo web WordPress'
        self.assertEqual(assess(item,'WEBSITE_REBUILD')['decision'],'exclude')
    def test_resolution_requires_subject_and_role_continuity(self):
        p=resolution(revision(768)['discovery'])
        good={'url':'https://numeraway.example/careers/python','title':'NUMERAWAY cerca freelance esperti in Python'}
        self.assertEqual(resolution_continuity(p,good)['status'],'SUPPORTED')
        for bad in [dict(good,title='SuperNUMERAWAY cerca freelance Python'),dict(good,title='Altra Azienda cerca freelance Python'),dict(good,title='NUMERAWAY cerca venditore'),dict(good,url='https://leeds.jobsin-uk.com/jobs/software+engineer',title='Ultime offerte di lavoro software engineer')]:
            self.assertEqual(resolution_continuity(p,bad)['status'],'UNRESOLVED')
    def test_pdf_all_engines_still_excluded(self):
        for engine in ENGINES:
            self.assertEqual(assess({'url':'https://alfa.example/candidati.pdf','title':'Cerchiamo freelance WordPress'},engine)['reason'],'excluded_pdf')
    def test_cache_expiry_and_exploration_no_time_invention(self):
        args={'acquired_at':'2026-10-17T10:00:00+00:00','last_used_at':'2026-10-17T10:10:00+00:00','now_at':'2026-10-17T11:00:00+00:00','ttl_seconds':7200}
        self.assertEqual(cache_decision(**args)['decision'],'REUSE')
        self.assertEqual(cache_decision(**args,query_exhausted=True)['decision'],'EXPLORE_NEW_QUERY')
        args['now_at']='2026-10-17T12:00:00+00:00';self.assertEqual(cache_decision(**args)['decision'],'REFRESH')
        for invalid in (None,'bad','2026-10-18T10:00:00+00:00'):
            self.assertEqual(cache_decision(**{**args,'acquired_at':invalid})['decision'],'REFRESH')
        with self.assertRaises(ValueError):cache_decision(None,ttl_seconds=-1)

class Planner3BTests(CommercialTestCase):
    def campaign(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create({'commercial_engines':list(ENGINES),'mode':'pilot'});w=Coordinator(self.store,self.c);w.initialize();return w
    def test_region_rotation_within_and_across_campaigns_persists(self):
        w=self.campaign();first=[]
        for i in range(3):
            p=choose(self.store,self.c['id'],'FREELANCE',plan('FREELANCE'));first.append(p)
            w.enqueue('search','FREELANCE',p,'region'+str(i))
        self.assertEqual([p['region'] for p in first],list(REGIONS[:3]));self.assertEqual(len({p['family'] for p in first}),3)
        w=self.campaign();nextp=choose(self.store,self.c['id'],'FREELANCE',plan('FREELANCE'));self.assertEqual(nextp['region'],REGIONS[0]);self.assertTrue(nextp['geographic_exploration']['not_company_evidence'])
    def test_every_region_reachable_without_query_budget_increase(self):
        w=self.campaign();regions=[]
        for i in range(20):
            if i and i%3==0:w=self.campaign()  # National coverage over consecutive Pilot quotas.
            p=choose(self.store,self.c['id'],'WEBSITE_REBUILD',plan('WEBSITE_REBUILD'));regions.append(p['region']);w.enqueue('search','WEBSITE_REBUILD',p,'all'+str(i))
        # 3B.4 balances each campaign, not a global history that pushes new pilots south.
        self.assertEqual(regions,[REGIONS[i%3] for i in range(20)])
    def test_relax_only_repeated_completed_zero_same_family(self):
        w=self.campaign();plans=plan('AGENCIES');template=plans[0]['family']
        for p in [x for x in plans if x['family']==template][:2]:
            w.enqueue('search','AGENCIES',p,'empty'+p['region'])
        with self.store.connect() as c:c.execute("UPDATE research_tasks SET state='done' WHERE campaign_id=?",(self.c['id'],))
        chosen=choose(self.store,self.c['id'],'AGENCIES',[p for p in plans if p['family']==template])
        self.assertNotIn('relaxation',chosen);self.assertEqual(chosen['family'],template)
        # 4.1 templates intentionally use fewer exact phrases. Repeated zero
        # results must still preserve the configured template, not relax it.
        self.assertIn(chosen['query'],[p['query'] for p in plans if p['family']==template])
        self.assertIn('agenzia',chosen['query']);self.assertIn('freelance',chosen['query'])
    def test_pending_empty_tasks_do_not_relax_query(self):
        w=self.campaign();plans=plan('AGENCIES');template=plans[0]['family']
        for p in [x for x in plans if x['family']==template][:2]:w.enqueue('search','AGENCIES',p,'pending'+p['region'])
        chosen=choose(self.store,self.c['id'],'AGENCIES',[p for p in plans if p['family']==template]);self.assertNotIn('relaxation',chosen)
