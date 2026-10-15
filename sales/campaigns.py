"""HTTP-side supervisor. Workers do not run in request threads."""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from .config import ROOT
from .db import now
from .research_store import ResearchStore,migrate

class CampaignManager:
    _workers={};_lock=threading.RLock()
    def __init__(self,store):self.store=store;self.rs=ResearchStore(store)
    @property
    def key(self):return str(self.store.path.resolve())
    def launch(self,campaign):
        with self._lock:
            logdir=self.store.path.parent/'research-logs';logdir.mkdir(exist_ok=True,mode=0o700)
            logfile=logdir/f"campaign-{campaign['id']}.log"
            with logfile.open('ab') as log:
                p=subprocess.Popen([sys.executable,'-m','sales.research_worker','--db',str(self.store.path.resolve()),'--campaign',str(campaign['id']),'--generation',campaign['generation'],'--parent-pid',str(os.getpid())],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
            logfile.chmod(0o600);self._workers[self.key]=p
            with self.store.connect() as c:c.execute('UPDATE campaigns SET worker_pid=? WHERE id=?',(p.pid,campaign['id']))
        return self.rs.campaign(campaign['id'])
    def start(self,filters=None,target=50):
        with self._lock:
            campaign=self.rs.create(filters,target)
            try:return self.launch(campaign)
            except Exception:
                self.rs.finish(campaign['id'],campaign['generation'],'error','Impossibile avviare il coordinatore');raise
    def resume(self,cid):
        campaign=self.rs.resume(cid)
        try:return self.launch(campaign)
        except Exception:
            self.rs.finish(cid,campaign['generation'],'error','Impossibile riprendere il coordinatore');raise
    def stop(self,cid):
        campaign=self.rs.stop(cid)
        if campaign['status']!='stopping':return campaign
        with self._lock:
            p=self._workers.get(self.key)
            if p and p.poll() is None:
                # Generation was invalidated transactionally before terminating the process.
                try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait(timeout=1)
                except ProcessLookupError:pass
                # The parent can exit before a browser child; stop the residual owned group too.
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            elif campaign.get('worker_pid'):
                # A second supervisor (or recovered HTTP server) can stop the persisted worker.
                pid=campaign['worker_pid']
                try:
                    cmd=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=1).stdout
                    if 'sales.research_worker' in cmd and self.key in cmd and '--campaign '+str(cid)+' ' in cmd:
                        os.killpg(pid,signal.SIGTERM)
                        deadline=time.monotonic()+1.5
                        while time.monotonic()<deadline:
                            try:os.kill(pid,0)
                            except ProcessLookupError:break
                            time.sleep(.05)
                        try:os.killpg(pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                except (ProcessLookupError,OSError,subprocess.TimeoutExpired):pass
            self.rs.paused(cid)
        return self.rs.campaign(cid)
    def state(self):
        campaign=self.rs.campaign()
        p=self._workers.get(self.key)
        if campaign and campaign['running'] and p and p.poll() is not None:
            self.rs.finish(campaign['id'],campaign['generation'],'error','Il coordinatore si è interrotto. Puoi riprendere dai controlli salvati.')
            campaign=self.rs.campaign()
        return campaign
    def recover(self):
        # Called only on server startup, not when a worker opens the database.
        with self.store.connect() as c:
            rows=[dict(r) for r in c.execute("SELECT * FROM campaigns WHERE status IN ('running','waiting','stopping')")]
        for r in rows:
            pid=r['worker_pid']
            if pid:
                try:
                    cmd=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=2).stdout
                    if 'sales.research_worker' in cmd and str(self.store.path.resolve()) in cmd and '--campaign '+str(r['id'])+' ' in cmd:
                        os.killpg(pid,signal.SIGTERM);time.sleep(.1)
                        try:os.killpg(pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                except (ProcessLookupError,OSError,subprocess.TimeoutExpired):pass
            self.rs.stop(r['id']);self.rs.paused(r['id'])
    def close(self):
        campaign=self.rs.campaign()
        if campaign and campaign['running']:self.stop(campaign['id'])
