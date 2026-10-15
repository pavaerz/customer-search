"""One local model/browser operation across HTTP handlers and research workers."""
import fcntl,os,threading,time
from contextlib import contextmanager
from .config import DATA
_gate=threading.Lock()
@contextmanager
def heavy_slot(check=lambda:None):
    while not _gate.acquire(timeout=.2):check()
    try:
        DATA.mkdir(exist_ok=True)
        with (DATA/'research-heavy.lock').open('a') as lock:
            os.chmod(lock.name,0o600)
            while True:
                check()
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:time.sleep(.1)
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
    finally:_gate.release()
