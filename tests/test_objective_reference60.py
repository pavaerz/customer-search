"""C55 actual SERP; positive boundary cases are explicitly synthetic."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6.social_seeds import recovery_query,reference_token,links_post
from sales.agent6.social_reference_alignment import assess
from sales.agent6 import decision,memory
import test_ai_first as h

FIX=json.loads((Path(__file__).parent/'fixtures/ai_first/reference60/campaign55.json').read_text())
POST=FIX['social_url'];ITEMS=FIX['results']

class Reference(unittest.TestCase):
 def test_identifier_query_retains_post_identity_and_no_bare_protocol(self):
  p=recovery_query(POST+'?igsh=discard')
  self.assertEqual(p['query'],'"DOgt6CDCGfj" -site:instagram.com')
  self.assertEqual(p['social_origin']['url'],POST)
  self.assertFalse(p['social_origin']['original_read'])
  self.assertEqual(p['selection'],'verification')

 def test_synthetic_linkedin_post_job_and_feed_use_supplied_identifiers(self):
  for url,token in [('https://linkedin.com/posts/alfa-activity-12345678901234-abc','12345678901234'),
    ('https://linkedin.com/feed/update/urn:li:ugcPost:12345678901234','12345678901234'),
    ('https://linkedin.com/feed/update/urn:li:share:12345678901234','12345678901234'),
    ('https://linkedin.com/jobs/view/123456789','123456789'),
    ('https://instagram.com/reel/Test_code-1','Test_code-1')]:
   self.assertEqual(reference_token(url),token)
   self.assertIn('"'+token+'"',recovery_query(url)['query'])
  self.assertEqual(reference_token('https://linkedin.com/posts/alfa'),'linkedin.com/posts/alfa/')
  self.assertIsNone(reference_token('https://linkedin.com/posts/'+'a'*300))

 def test_real_c55_drift_is_held_without_blacklisting_or_negative_decisions(self):
  before=copy.deepcopy(ITEMS);r=assess(ITEMS,recovery_query(POST))
  self.assertEqual(r['code'],'social_reference_protocol_drift')
  self.assertEqual(set(r['held_urls']),{x['url'] for x in ITEMS})
  self.assertEqual(ITEMS,before)
  self.assertIsNone(assess(ITEMS,{'strategy':'explicit_complete_project'}))
  self.assertIsNone(assess(ITEMS,{'social_origin':{'url':'https://evil.example/post'}}))

 def test_synthetic_reference_anchor_is_never_replaced_by_metadata_qualification(self):
  rows=copy.deepcopy(ITEMS)
  rows[0]['content']+=' Il post DOgt6CDCGfj annuncia una collaborazione.'
  self.assertIsNone(assess(rows,recovery_query(POST)))
  pg={'url':'https://employer.example/jobs','html':'<p>DOgt6CDCGfj</p>'}
  self.assertFalse(links_post(pg,POST))
  pg['html']='<a href="'+POST+'">Fonte</a>'
  self.assertTrue(links_post(pg,POST))

 def test_synthetic_missing_metadata_and_mixed_results_preserve_original_reading(self):
  rows=[{'url':'https://employer.example/'+str(i),'title':'Alfa '+str(i)} for i in range(4)]
  self.assertIsNone(assess(rows,recovery_query(POST)))
  self.assertIsNone(assess(ITEMS[:2],recovery_query(POST)))
  self.assertIsNone(assess(ITEMS[:2]+rows,recovery_query(POST)))
  invitation={'url':'https://employer.example/careers','title':'HTTPS developers freelance',
    'content':'Cerchiamo sviluppatori frontend per progetti HTTPS con certificati TLS.'}
  self.assertIsNone(assess([invitation]*4,recovery_query(POST)))

class Pipeline(unittest.TestCase):
 def test_real_serp_does_not_create_candidates_or_consume_reads_ai(self):
  b=h.IntegratedPath();b.setUp();self.addCleanup(b.tearDown)
  body=decision.base({'url':POST,'title':'Post non consultabile','original':False},'SOCIAL')
  body.update(state='UNVERIFIABLE',validation_status='ACCESS_BLOCKED',
              social_source={'url':POST,'original_read':False})
  memory.save_record(b.store,b.c,'SOCIAL',body)
  with b.store.connect() as db:before=list(db.execute('SELECT id,body FROM agent6_records'))
  p=recovery_query(POST)
  # Also protect resumed old URL queries: no rewrite of historical task data.
  p['query']='"'+POST+'" -site:instagram.com'
  with patch('sales.agent6.research.acquire',return_value=ITEMS),patch(
       'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No download')),patch(
       'sales.agent6.ai.infer',side_effect=AssertionError('No AI')):
   b.w.execute({'id':1,'kind':'search','strategy':'SOCIAL','payload':p},lambda:None)
  with b.store.connect() as db:
   self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
   self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
   after=list(db.execute('SELECT id,body FROM agent6_records'))
   self.assertEqual([tuple(r) for r in before],[tuple(r) for r in after])
   records=[json.loads(r[0]) for r in db.execute("SELECT body FROM agent6_memory WHERE kind='query'")]
   self.assertEqual(records[0]['results'],10);self.assertEqual(records[0]['new_urls'],0)
   self.assertEqual(records[0]['discovery_alignment']['code'],'social_reference_protocol_drift')
   feedback=[json.loads(r[0]) for r in db.execute("SELECT body FROM agent6_memory WHERE kind='plan_feedback'")]
   self.assertEqual(feedback[0]['code'],'social_reference_protocol_drift')
