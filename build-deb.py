#!/usr/bin/env python3
"""Build separate core/CLI and optional desktop packages with dpkg-deb."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from pulse_elite import __version__

ROOT = Path(__file__).resolve().parent


def put(stage, destination, source=None, text=None, mode=0o644):
    path = stage / destination
    path.parent.mkdir(parents=True, exist_ok=True)
    if source:
        shutil.copyfile(ROOT / source, path)
    else:
        path.write_text(text)
    path.chmod(mode)


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    for desktop in (False, True):
        name = 'pulse-elite-autoswitch' + ('-desktop' if desktop else '')
        with tempfile.TemporaryDirectory(prefix='pulse-elite-deb-') as temp:
            stage = Path(temp)
            depends = f'pulse-elite-autoswitch (= {__version__}), python3-gi, gir1.2-gtk-3.0' if desktop else 'python3 (>= 3.10), pipewire-bin, wireplumber, systemd, udev'
            put(stage, 'DEBIAN/control', text=f'''Package: {name}
Version: {__version__}
Section: sound
Priority: optional
Architecture: all
Maintainer: klakiti <127831506+klakiti@users.noreply.github.com>
Depends: {depends}
Homepage: https://github.com/klakiti/pulse-elite-autoswitch
Description: Automatic Sony Pulse Elite audio output switching
 {'Optional GTK desktop configuration interface.' if desktop else 'User-session daemon and CLI using PlayStation Link HID connection status.'}
''')
            modules = ['gui.py'] if desktop else ['__init__.py', 'core.py', 'daemon.py', 'cli.py']
            for module in modules:
                put(stage, 'usr/lib/pulse-elite-autoswitch/pulse_elite/' + module, 'pulse_elite/' + module)
            if desktop:
                put(stage, 'usr/share/applications/pulse-elite-autoswitch.desktop', 'packaging/pulse-elite-autoswitch.desktop')
            else:
                put(stage, 'usr/bin/pulse-elite-autoswitch', 'packaging/pulse-elite-autoswitch', mode=0o755)
                put(stage, 'usr/lib/systemd/user/pulse-elite-autoswitch.service', 'pulse-elite-autoswitch.service')
                put(stage, 'usr/lib/udev/rules.d/70-pulse-elite.rules', '70-pulse-elite.rules')
                put(stage, 'DEBIAN/postinst', text='''#!/bin/sh
set -e
if [ "$1" = configure ]; then
    if [ -d /run/udev ]; then
        udevadm control --reload-rules
        udevadm trigger --action=add --subsystem-match=hidraw
    fi
fi
exit 0
''', mode=0o755)
                put(stage, 'DEBIAN/postrm', text='''#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
    if [ -d /run/udev ]; then udevadm control --reload-rules; fi
fi
exit 0
''', mode=0o755)
            for doc in ('README.md', 'PROTOCOL.md'):
                put(stage, f'usr/share/doc/{name}/{doc}', doc)
            sums = []
            for p in sorted((stage / 'usr').rglob('*')):
                if p.is_file():
                    sums.append(hashlib.md5(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(stage)))
            put(stage, 'DEBIAN/md5sums', text='\n'.join(sums) + '\n')
            target = output / f'{name}_{__version__}_all.deb'
            subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(target)], check=True)
    files = sorted(output.glob(f'*_{__version__}_all.deb'))
    (output / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=ROOT / 'dist')
    build(p.parse_args().output.resolve())
