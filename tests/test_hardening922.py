"""Local-only startup and backup regressions; never touch operational data."""
import errno
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from sales import server
from scripts.backup import backup, verify_backup
from scripts.analysis_archive import read_text
import hashlib


class StartupTests(unittest.TestCase):
    def test_occupied_port_never_initializes_or_recovers_database(self):
        with patch.object(server, 'ThreadingHTTPServer', side_effect=OSError(errno.EADDRINUSE, 'busy')), \
             patch.object(server, 'initialize_runtime') as initialize, patch.object(server, 'STORE') as store:
            with self.assertRaisesRegex(SystemExit, 'già occupata'):
                server.main()
            initialize.assert_not_called()
            store.init.assert_not_called()

    def test_initialization_failure_releases_listener(self):
        http = Mock()
        with patch.object(server, 'ThreadingHTTPServer', return_value=http), \
             patch.object(server, 'initialize_runtime', side_effect=ValueError('fixture')):
            with self.assertRaises(ValueError):
                server.main()
        http.serve_forever.assert_not_called()
        http.server_close.assert_called_once()

    def test_listener_is_owned_before_runtime_and_closed_after_serving(self):
        order = []
        http = Mock()
        http.serve_forever.side_effect = lambda: order.append('serve')
        http.server_close.side_effect = lambda: order.append('close')
        with patch.object(server, 'ThreadingHTTPServer', side_effect=lambda *a: order.append('bind') or http), \
             patch.object(server, 'initialize_runtime', side_effect=lambda: order.append('init')):
            server.main()
        self.assertEqual(order, ['bind', 'init', 'serve', 'close'])


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        self.db = self.root / 'data/sales.sqlite3'
        with sqlite3.connect(self.db) as c:
            c.execute('create table history (id integer primary key, note text)')
            c.execute("insert into history(note) values ('preserve')")
        (self.root / '.env').write_text('FIXTURE_ONLY=not-a-secret\n')
        (self.root / 'app.py').write_text('print("fixture")\n')

    def test_private_backup_and_restore_survive_later_live_changes(self):
        destination = Path(backup(self.root))
        with sqlite3.connect(self.db) as c:
            c.execute("insert into history(note) values ('later')")
        result = verify_backup(destination)
        self.assertTrue(result['verified'])
        self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
        for file in destination.iterdir():
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('select count(*) from history').fetchone()[0], 2)

    def test_links_and_environment_and_sqlite_files_are_not_followed(self):
        (self.root / 'linked-secret').symlink_to(self.root / '.env')
        (self.root / 'linked-data').symlink_to(self.root / 'data', target_is_directory=True)
        (self.root / '.venv').mkdir()
        (self.root / '.venv/ignore.txt').write_text('ignore')
        (self.root / 'other.sqlite').write_text('do not archive raw database')
        destination = Path(backup(self.root))
        with zipfile.ZipFile(destination / 'project.zip') as z:
            self.assertEqual(set(z.namelist()), {'.env', 'app.py'})

    def test_corruption_is_detected(self):
        destination = Path(backup(self.root))
        with (destination / 'sales.sqlite3').open('ab') as f:
            f.write(b'corruption')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            verify_backup(destination)

    def test_linked_database_is_not_read(self):
        real = self.root / 'other.sqlite3'
        self.db.rename(real)
        self.db.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'linked operational database'):
            backup(self.root)

    def test_restore_rejects_traversal_even_with_matching_manifest(self):
        destination = Path(backup(self.root))
        with zipfile.ZipFile(destination / 'project.zip', 'w') as z:
            z.writestr('../outside', 'fixture')
        manifest = json.loads((destination / 'manifest.json').read_text())
        manifest['files'] = {'../outside': 'invalid'}
        manifest['databases'] = {}
        (destination / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            verify_backup(destination)


class HistoricalArchiveTests(unittest.TestCase):
    def test_historical_input_remains_readable_and_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'archives').mkdir()
            payload = b'{"campaign": 30}'
            name = 'CAMPAIGN-30-METRICS.json'
            path = root / 'archives/customersearch-analysis-archive.zip'
            def write(data):
                with zipfile.ZipFile(path, 'w') as z:
                    z.writestr(name, data)
                    z.writestr('ARCHIVE-MANIFEST.json', json.dumps({'files': [
                        {'path': name, 'archived_sha256': hashlib.sha256(payload).hexdigest()}
                    ]}))
            write(payload)
            self.assertEqual(json.loads(read_text(name, root)), {'campaign': 30})
            write(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                read_text(name, root)

if __name__ == '__main__':
    unittest.main()
