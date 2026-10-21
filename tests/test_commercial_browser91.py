"""Recovery of measured viewports, never fabricated real-site success."""
import subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.commercial.browser import review
from sales.db import Store,now

class PhaseAllocation91(unittest.TestCase):
    def test_pending_read_uses_remaining_total_without_changing_explicit_limit(self):
        from sales.commercial.browser import rendering_phase_limit
        self.assertEqual(rendering_phase_limit(5000,20,120000,remaining_views=2),58750)
        self.assertEqual(rendering_phase_limit(400,20,120000,True,2),400)
        self.assertEqual(rendering_phase_limit(5000,0,120000,remaining_views=2),5000)
        for remaining in (1,100,1000,120000):
            self.assertLessEqual(rendering_phase_limit(5000,20,remaining,remaining_views=2),remaining)

    def test_saved_campaign40_reports_are_not_reclassified_as_successes(self):
        import gzip,json
        from sales.commercial.audit_policy import finish
        saved=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/agent91/browser40.json.gz').read_bytes()))
        self.assertEqual(len(saved['cases']),4)
        for case in saved['cases']:
            browser=case['browser']
            self.assertFalse(browser['completed'])
            result=finish(browser,'STANDARD',True)
            self.assertFalse(result['completed'])
            self.assertEqual(result['findings'],[])
            self.assertNotEqual(result['measurement_reliability'],'CONFIRMED')


class Readiness91(unittest.TestCase):
    def render(self,delay,*,body='',fail=False,phase_ms=400,total_seconds=8,resource_ms=2500):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db');store.init()
            html='<meta name="viewport" content="width=device-width">'+body+'<script async src="/dependency.js?delay='+str(delay)+('&fail=1' if fail else '')+'"></script>'
            page={'url':'https://fixture.example/','html':html,'status':200,'checked_at':now()}
            def launch(source,output,errors):
                return subprocess.Popen([sys.executable,'-m','browser91_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
            limits={'browser_audit_level':'STANDARD','browser_total_seconds':total_seconds,'browser_timeout_ms':1000,
                    'browser_resource_timeout_ms':resource_ms,'browser_max_resources':6}
            if phase_ms is not None:limits['browser_render_timeout_ms']=phase_ms
            with patch('sales.commercial.browser._launch_worker',launch):
                result=review(store,[page],capture=False,limits=limits)
            self.assertTrue(result['worker_reaped']);self.assertTrue(result['resources_closed'])
            self.assertEqual(result['resource_requests'],1)
            return result

    def test_late_dom_recovered_with_actual_render_measurements(self):
        r=self.render(.6)
        self.assertTrue(r['completed'],r)
        self.assertEqual({p['viewport'] for p in r['pages'] if p['complete']},{390,1366})
        self.assertTrue(any(d.get('stage')=='early' and d.get('code')=='dom_timeout' for d in r['diagnostics']))
        self.assertNotIn('dom_timeout',r['failure_codes'])

    def test_timeout_in_first_viewport_does_not_invalidate_second_measurement(self):
        r=self.render(.6,body='<main><p>Contenuto iniziale visibile e sufficientemente completo per il test.</p></main>')
        self.assertFalse(r['completed'])
        self.assertEqual([p['viewport'] for p in r['pages'] if p['complete']],[1366])
        self.assertEqual(r['findings'],[])
        self.assertTrue(r['independent_measurements'])

    def test_failed_critical_resource_still_invalidates_both_viewports(self):
        r=self.render(.1,body='<main><p>Contenuto iniziale visibile e sufficientemente completo per il test.</p></main>',fail=True)
        self.assertFalse(r['completed'])
        self.assertFalse(any(p['complete'] for p in r['pages']))
        self.assertEqual(r['findings'],[])
        self.assertEqual(r['independent_measurements'],[])

    def test_queued_resource_can_finish_beyond_old_ten_second_default(self):
        r=self.render(11,body='<main><p>Contenuto iniziale visibile e sufficientemente completo per il test.</p></main>',
                      phase_ms=None,total_seconds=30,resource_ms=15000)
        self.assertTrue(r['completed'],r)
        self.assertLess(r['elapsed_ms'],30000)
        self.assertEqual({p['viewport'] for p in r['pages'] if p['complete']},{390,1366})
        self.assertEqual(r['failure_codes'],[])


if __name__=='__main__':unittest.main()
