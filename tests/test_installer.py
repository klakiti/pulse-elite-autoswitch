"""Exercise the installer without networking, sudo, or changing user services."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

INSTALLER = Path(__file__).resolve().parents[1] / 'install.sh'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        self.log = self.root / 'commands'
        version = (INSTALLER.parent / 'pulse_elite/__init__.py').read_text().split("'")[1]
        self.packages = [f'{name}_{version}_all.deb' for name in
                         ('pulse-elite-autoswitch', 'pulse-elite-autoswitch-desktop')]
        for name in self.packages:
            (self.assets / name).write_bytes(b'fixture package')
        self.manifest = ''.join(hashlib.sha256(b'fixture package').hexdigest() + '  ' + name + '\n'
                                for name in self.packages)
        (self.assets / 'SHA256SUMS').write_text(self.manifest)
        self.stub('curl', '''#!/usr/bin/env python3
import os, pathlib, shutil, sys
args=sys.argv[1:]
url=next(a for a in args if a.startswith('https://'))
shutil.copyfile(pathlib.Path(os.environ['ASSETS']) / url.rsplit('/',1)[1], args[args.index('-o')+1])
''')
        self.stub('sudo', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$COMMAND_LOG"\n')
        self.stub('systemctl', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$COMMAND_LOG"\n')
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        ASSETS=str(self.assets), COMMAND_LOG=str(self.log))

    def stub(self, name, content):
        p = self.bin / name
        p.write_text(content)
        p.chmod(0o755)

    def run_installer(self, *args):
        return subprocess.run(['bash', str(INSTALLER), *args], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_cli_download_only_has_no_system_changes(self):
        result = self.run_installer('--cli', '--download-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / self.packages[0]).exists())
        self.assertFalse((self.root / self.packages[1]).exists())
        self.assertFalse(self.log.exists())

    def test_checksum_mismatch_never_installs(self):
        (self.assets / self.packages[0]).write_bytes(b'corrupted')
        result = self.run_installer('--download-only')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / self.packages[0]).exists())
        self.assertNotIn('unbound variable', result.stderr)

    def test_missing_checksum_never_installs(self):
        (self.assets / 'SHA256SUMS').write_text('')
        result = self.run_installer('--download-only')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum missing', result.stderr)
        self.assertFalse(self.log.exists())

    @unittest.skipIf(os.geteuid() == 0, 'Installer intentionally rejects root')
    def test_install_reloads_and_restarts_existing_service(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.log.read_text()
        self.assertIn('apt-get install -y', commands)
        self.assertIn(self.packages[1], commands)
        self.assertIn('--user daemon-reload', commands)
        self.assertIn('--user restart pulse-elite-autoswitch.service', commands)
        self.assertNotIn('--user enable', commands)
