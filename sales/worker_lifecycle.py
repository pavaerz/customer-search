"""Stop owned research work if the HTTP supervisor disappears abruptly."""
import os
import signal


def pause_orphan(rs, cid, owner_pid, terminate):
    if not owner_pid or os.getppid()==owner_pid:return False
    rs.stop(cid);rs.paused(cid)
    terminate()
    return True


def watch_owner(rs, cid, owner_pid, finished):
    def terminate():
        # Production workers own their process group. Never kill a caller's group.
        if os.getpgrp()==os.getpid():os.killpg(os.getpid(),signal.SIGTERM)
        else:os.kill(os.getpid(),signal.SIGTERM)
    while not finished.wait(1):
        if pause_orphan(rs,cid,owner_pid,terminate):return
