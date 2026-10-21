"""Offline source-install smoke test in a disposable copy, using installed Python deps."""
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='customersearch-install-') as tmp:
        root = Path(tmp)
        for directory in ('sales', 'static', 'scripts'):
            shutil.copytree(ROOT / directory, root / directory,
                            ignore=shutil.ignore_patterns('__pycache__'))
        for source in ROOT.glob('*.py'):
            shutil.copy2(source, root / source.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {k: v for k, v in os.environ.items()
               if not any(word in k.upper() for word in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET'))}
        env.update(PORT=str(port), PYTHONPATH=str(ROOT / 'tests/offline_guard'),
                   PYTHONDONTWRITEBYTECODE='1')
        log = root / 'startup.log'
        with log.open('w') as output:
            process = subprocess.Popen([sys.executable, '-B', 'app.py'], cwd=root,
                                       env=env, stdout=output, stderr=output)
        origin = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError('Disposable backend failed to start:\n' + log.read_text())
                try:
                    with urlopen(origin + '/api/state', timeout=1) as response:
                        state = json.load(response)
                    break
                except (OSError, HTTPError):
                    time.sleep(.1)
            else:
                raise AssertionError('Disposable backend startup timeout')
            with urlopen(origin + '/', timeout=2) as response:
                assert response.status == 200
                assert b'<html' in response.read().lower()
            with urlopen(origin + '/api/agent6/worklist?view=ready', timeout=2) as response:
                assert response.status == 200
            for request in (
                Request(origin + '/api/state', headers={'Host': 'evil.example'}),
                Request(origin + '/api/settings', data=b'{}',
                        headers={'Origin': origin, 'Content-Type': 'application/json'}),
            ):
                try:
                    urlopen(request, timeout=2)
                except HTTPError as exc:
                    assert exc.code == 403
                else:
                    raise AssertionError('API security check failed')
            assert state['campaign'] is None
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise AssertionError('Disposable backend failed to terminate gracefully')
        db = sqlite3.connect((root / 'data/sales.sqlite3').as_uri() + '?mode=ro', uri=True)
        try:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute('SELECT count(*) FROM campaigns').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM prospects').fetchone()[0] == 0
        finally:
            db.close()
        print(json.dumps({'fresh_source_copy': True, 'fresh_database': True,
                          'existing_python_dependencies': True, 'dependency_download_tested': False,
                          'entrypoint': 'app.py', 'state_and_worklist_api': True,
                          'host_csrf_enforced': True, 'graceful_shutdown': True,
                          'sqlite_integrity': 'ok', 'campaigns_created': 0,
                          'production_writes': 0, 'external_calls': 0}))


if __name__ == '__main__':
    main()
