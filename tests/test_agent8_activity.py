"""Observed pages and verified entities, distinct from stored URL/record totals."""
import copy,unittest
from sales.agent6.activity import measures


def row(rid,url='https://alfa.example/',**extra):
    b={'url':url,'original':True,'identity_verified':True,'official_domain':'https://alfa.example/',
        'access':{'content_read':True},'documents':[],**extra}
    return {'id':rid,'request_key':str(rid),'campaign_id':1,'state':'NEEDS_REVIEW','body':b}


class Activity(unittest.TestCase):
    def test_repeated_pages_and_multiple_requests_are_not_new_companies(self):
        rows=[row(1),row(2),row(3,url='https://alfa.example/jobs')]
        result=measures(rows)
        self.assertEqual(result['original_pages_read'],2)
        self.assertEqual(result['identified_companies'],1)
        self.assertEqual(result['sites_with_audit'],0)
    def test_challenge_and_unknown_legacy_access_are_not_originals_read(self):
        legacy=row(2);legacy['body'].pop('access')
        rows=[row(1,identity_verified=False,access={'content_read':False}),legacy]
        before=copy.deepcopy(rows);result=measures(rows)
        self.assertEqual(result['original_pages_read'],0)
        self.assertEqual(result['original_records_without_access_status'],1)
        self.assertEqual(before,rows)
    def test_audit_counts_only_read_pages_and_distinct_official_site(self):
        audit={'pages':[{'url':'https://alfa.example/','access':{'content_read':True}},
                         {'url':'https://alfa.example/contact','access':{'content_read':True}},
                         {'url':'https://alfa.example/catalog','access':{'content_read':False}}],
               'browser_status':'PARTIAL'}
        first=row(1,website_audit=audit);second=row(2,website_audit=audit)
        first['state']='POTENTIAL';second['state']='VERIFIED'
        result=measures([first,second])
        self.assertEqual(result['original_pages_read'],2);self.assertEqual(result['sites_with_audit'],1)
        self.assertEqual(result['sites_with_completed_browser'],0);self.assertEqual(result['qualified_companies'],1)
        audit['browser_status']='COMPLETE'
        self.assertEqual(measures([first,second])['sites_with_completed_browser'],1)
    def test_unverified_social_domain_never_counts_as_identified_company(self):
        for host in ('linkedin.com','bsky.app','mastodon.social'):
            with self.subTest(host=host):
                b=row(1,url='https://'+host+'/posts/a',official_domain='https://'+host+'/',identity_verified=True)
                self.assertEqual(measures([b])['identified_companies'],0)

    def test_planning_and_screening_are_not_counted_as_original_verification(self):
        tasks=[{'kind':'agent_plan','state':'working','n':2},{'kind':'agent_screen','state':'working','n':3},
               {'kind':'candidate','state':'working','n':1},{'kind':'candidate','state':'pending','n':4},
               {'kind':'candidate','state':'failed','n':5}]
        result=measures([],tasks)
        self.assertEqual(result['active_verification_tasks'],1)
        self.assertEqual(result['pending_verification_tasks'],4)


if __name__=='__main__':unittest.main()
