import contextlib
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import build
import install


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        for name, value in {'ROOT': self.home / 'installed', 'STATE': self.home / 'state',
                            'T3_HOME': self.home / 't3'}.items():
            value.mkdir()
            mocked = patch.object(install, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def stage(self, version):
        executable = install.ROOT / version / 'squashfs-root/AppRun'
        executable.parent.mkdir(parents=True)
        executable.write_text('fixture')

    def test_upgrade_retains_previous_version_and_consistent_wal_backup(self):
        self.stage('0.0.4501')
        self.stage('0.0.4502')
        userdata = install.T3_HOME / 'userdata'
        userdata.mkdir()
        with sqlite3.connect(userdata / 'state.sqlite') as database:
            database.execute('PRAGMA journal_mode=WAL')
            database.execute('CREATE TABLE messages (text TEXT)')
            database.execute("INSERT INTO messages VALUES ('saved conversation')")
            database.commit()
            with contextlib.redirect_stdout(io.StringIO()):
                install.activate('0.0.4501')
                install.activate('0.0.4502')
            backups = list((install.STATE / 'backups').glob('*/state.sqlite'))
            self.assertEqual(len(backups), 2)
            for snapshot in backups:
                with sqlite3.connect(snapshot) as backup:
                    self.assertEqual(backup.execute('SELECT text FROM messages').fetchone()[0],
                                     'saved conversation')
            versions = install.read_json(install.STATE / 'versions.json')
            self.assertEqual(versions, {'current': '0.0.4502', 'previous': '0.0.4501'})
            self.assertEqual(install.current_version(), '0.0.4502')
            with contextlib.redirect_stdout(io.StringIO()):
                install.activate(versions['previous'])
            self.assertEqual(install.current_version(), '0.0.4501')
            self.assertEqual(database.execute('SELECT count(*) FROM messages').fetchone()[0], 1)

    def test_tampered_download_leaves_current_version_untouched(self):
        self.stage('0.0.4501')
        with contextlib.redirect_stdout(io.StringIO()):
            install.activate('0.0.4501')

        def download(url, target):
            target.write_text('0' * 64 + '  T3-Code-0.0.4502-x86_64.AppImage\n'
                              if url.endswith('SHA256SUMS') else 'tampered executable')

        with patch.object(install, 'download', download), patch.object(install.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                install.install('0.0.4502')
            run.assert_not_called()
        self.assertEqual(install.current_version(), '0.0.4501')
        self.assertFalse((install.ROOT / '0.0.4502').exists())

    def test_stable_versions_order_base_updates_and_custom_revisions(self):
        versions = [build.release_version({'upstreamTag': tag, 'revision': revision})
                    for tag, revision in [('v0.0.45', 1), ('v0.0.45', 2), ('v0.0.46', 1)]]
        self.assertEqual(versions, ['0.0.4501', '0.0.4502', '0.0.4601'])
        with self.assertRaises(ValueError):
            build.release_version({'upstreamTag': 'v0.0.45', 'revision': 100})


if __name__ == '__main__':
    unittest.main()
