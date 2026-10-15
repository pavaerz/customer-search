import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from sales.db import Store
from sales.research_store import ResearchStore
from sales.worker_lifecycle import pause_orphan


class WorkerLifecycleTests(unittest.TestCase):
    def test_live_parent_does_not_pause_user_campaign(self):
        rs=Mock();terminate=Mock()
        with patch('sales.worker_lifecycle.os.getppid',return_value=100):
            self.assertFalse(pause_orphan(rs,4,100,terminate))
        rs.stop.assert_not_called();terminate.assert_not_called()

    def test_orphan_is_paused_before_termination(self):
        operations=[];rs=Mock()
        rs.stop.side_effect=lambda cid:operations.append('invalidate')
        rs.paused.side_effect=lambda cid:operations.append('save_pause')
        with patch('sales.worker_lifecycle.os.getppid',return_value=1):
            self.assertTrue(pause_orphan(rs,4,100,lambda:operations.append('terminate')))
        self.assertEqual(operations,['invalidate','save_pause','terminate'])

    def test_abrupt_owner_death_pauses_real_isolated_worker_within_five_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite3');store.init();rs=ResearchStore(store);campaign=rs.create()
            pidfile=Path(tmp)/'pid'
            child="from sales.db import Store;from sales.research_store import ResearchStore;from sales.worker_lifecycle import watch_owner;from pathlib import Path;import sys,threading;watch_owner(ResearchStore(Store(Path(sys.argv[1]))),int(sys.argv[2]),int(sys.argv[3]),threading.Event())"
            owner="import os,subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3],str(os.getpid())],start_new_session=True);Path(sys.argv[4]).write_text(str(p.pid));time.sleep(30)"
            parent=subprocess.Popen([sys.executable,'-c',owner,child,str(store.path),str(campaign['id']),str(pidfile)],start_new_session=True)
            childpid=None
            try:
                deadline=time.monotonic()+3
                while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.02)
                childpid=int(pidfile.read_text());parent.kill();parent.wait()
                start=time.monotonic()
                while rs.campaign(campaign['id'])['status']!='paused' and time.monotonic()-start<5:time.sleep(.05)
                self.assertEqual(rs.campaign(campaign['id'])['status'],'paused')
                self.assertLess(time.monotonic()-start,5)
            finally:
                if parent.poll() is None:parent.kill()
                parent.wait()
                if childpid:
                    try:os.killpg(childpid,signal.SIGKILL)
                    except ProcessLookupError:pass
