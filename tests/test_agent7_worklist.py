"""Read-only worklist regressions with synthetic original documents and CRM."""
import json
import unittest
from datetime import datetime,timezone
from unittest.mock import patch

import test_agent6 as original
import test_agent6_campaign32 as support
from sales.agent6 import memory,api
from sales.agent6.worklist import listing


class Worklist(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.c,self.rs=self.base.store,self.base.c,self.base.rs
        self.at=datetime(2026,10,19,14,tzinfo=timezone.utc)

    def tearDown(self):self.base.tearDown()
    def read(self,**params):return listing(self.store,params,at=self.at)
    def save(self,**kw):return memory.save_record(self.store,self.c,'AGENCIES',{**original.evaluated(),**kw})
    def next(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create(self.base.filters)

    def test_across_campaigns_deduplicates_request_not_distinct_roles(self):
        self.save();self.next();self.save()
        self.save(url='https://alfa.example/second-role')
        result=self.read()
        self.assertEqual(result['total'],2)
        self.assertEqual(sorted(len(r['worklist']['campaigns']) for r in result['items']),[1,2])
        self.assertTrue(all(r['worklist']['request'] and r['worklist']['contacts'] for r in result['items']))

    def test_latest_original_closed_request_supersedes_verified(self):
        self.save();self.next();self.save(state='REJECTED',counterevidence=['closed_request'])
        self.assertEqual(self.read()['total'],0)
        self.assertEqual(self.read(view='all')['total'],0)

    def test_weak_new_snippet_never_destroys_original(self):
        first=self.save();self.next();self.save(original=False,state='DISCOVERED',identity_verified=False,entity_key=None)
        r=self.read()['items'][0]
        self.assertEqual(r['id'],first);self.assertEqual(r['state'],'VERIFIED')

    def test_old_proofs_become_review_without_historical_rewrite(self):
        rid=self.save();before=api.dossier(self.store,rid)
        result=listing(self.store,{'view':'review'},at=datetime(2026,12,1,tzinfo=timezone.utc))
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['saved_state'],'VERIFIED')
        self.assertEqual(result['items'][0]['state'],'NEEDS_REVIEW')
        self.assertEqual(api.dossier(self.store,rid),before)

    def test_snippets_and_unprocessed_urls_are_not_ready_clients(self):
        self.save(state='DISCOVERED',original=False,facts=[],workflow_state='SCREENING_PENDING')
        self.assertEqual(self.read(view='all')['total'],0)
        self.save(state='DISCOVERED',original=False,workflow_state='ORIGINAL_READ_PENDING')
        self.assertEqual(self.read(view='new')['total'],1)
        self.assertEqual(self.read()['total'],0)

    def test_manual_deletion_survives_interesting_feedback_and_campaigns(self):
        rid=self.save();self.next();second=self.save()
        memory.feedback(self.store,rid,'not_interesting');memory.feedback(self.store,second,'interesting')
        self.assertEqual(self.read()['total'],0);self.assertEqual(self.read(view='excluded')['total'],1)
        memory.feedback(self.store,rid,'restore')
        self.assertEqual(self.read()['total'],1)

    def test_contacted_is_green_category_and_not_ready_for_new_outreach(self):
        rid=self.save();memory.feedback(self.store,rid,'contacted')
        self.assertEqual(self.read()['total'],0)
        r=self.read(view='contacted')['items'][0]
        self.assertEqual(r['feedback'],'contacted');self.assertEqual(r['state'],'VERIFIED')
        self.assertIn('risposta',r['worklist']['next_action'])

    def test_crm_reply_overrides_earlier_contact_and_preserves_notes(self):
        rid=self.save();pid=api.save_contact(self.store,rid)['prospect_id'];memory.feedback(self.store,rid,'contacted')
        with self.store.connect() as c:
            c.execute("UPDATE prospects SET stage='replied',notes='Manual business notes',updated_at='2099-01-01T00:00:00+00:00' WHERE id=?",(pid,))
        r=self.read(view='replied')['items'][0]
        self.assertEqual(r['worklist']['crm_id'],pid);self.assertEqual(self.read()['total'],0)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT notes FROM prospects WHERE id=?',(pid,)).fetchone()[0],'Manual business notes')

    def test_contact_for_one_request_does_not_invent_contact_for_another(self):
        first=self.save();second=self.save(url='https://alfa.example/other-role')
        memory.feedback(self.store,first,'contacted')
        self.assertEqual(self.read(view='contacted')['total'],1)
        review=self.read(view='review')['items'][0]
        self.assertEqual(review['id'],second);self.assertIsNone(review['feedback'])
        self.assertIn('altra richiesta',review['worklist']['warning'])
        self.assertEqual(self.read()['total'],0)

    def test_do_not_contact_overrides_ready_and_crm_stage(self):
        rid=self.save();pid=api.save_contact(self.store,rid)['prospect_id']
        with self.store.connect() as c:c.execute('UPDATE companies SET do_not_contact=1')
        self.assertEqual(self.read()['total'],0)
        self.assertTrue(self.read(view='excluded')['items'][0]['worklist']['excluded'])

    def test_filters_counts_and_pages_agree(self):
        for i in range(4):self.save(url=f'https://alfa.example/role-{i}')
        first=self.read(limit=2);second=self.read(limit=2,offset=2)
        self.assertEqual(first['total'],4);self.assertEqual(first['counts']['ready'],4)
        self.assertTrue({r['id'] for r in first['items']}.isdisjoint(r['id'] for r in second['items']))
        self.assertEqual(self.read(q='Alfa')['total'],4);self.assertEqual(self.read(flow='NEWS')['total'],0)
        with self.assertRaises(ValueError):self.read(view='invented')

    def test_read_has_no_writes_no_network_and_no_new_campaign(self):
        self.save()
        with self.store.connect() as c:before='\n'.join(c.iterdump())
        with patch('socket.create_connection',side_effect=AssertionError('Worklist must not access network')):
            self.assertEqual(self.read()['total'],1)
        with self.store.connect() as c:self.assertEqual('\n'.join(c.iterdump()),before)


if __name__=='__main__':unittest.main()
