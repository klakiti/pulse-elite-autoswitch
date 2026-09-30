"""Shared configuration, device detection and routing. No GUI dependencies."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import time

UNIT = 'pulse-elite-autoswitch.service'
HID_ID = 'HID_ID=0003:0000054C:00000ECC'


class AppError(Exception):
    pass


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'pulse-elite-autoswitch/config.json'


def runtime_path():
    root = os.environ.get('XDG_RUNTIME_DIR')
    if not root:
        raise AppError('No user session runtime directory. Run in your desktop/audio user session.')
    return Path(root)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_config(path=None):
    try:
        value = json.loads(Path(path or config_path()).read_text())
    except FileNotFoundError:
        raise AppError('Not configured. Open the setup app or run: ps-pulse configure')
    except (OSError, ValueError) as exc:
        raise AppError(f'Cannot read configuration: {exc}')
    if not isinstance(value, dict):
        raise AppError('Configuration must be a JSON object.')
    for key in ('headset_sink', 'speakers_sink'):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise AppError(f'Missing device selection: {key}')
    if value['headset_sink'] == value['speakers_sink']:
        raise AppError('Headset and fallback outputs must be different.')
    return value


def command(args, check=True):
    try:
        r = subprocess.run(args, text=True, capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AppError(str(exc))
    if check and r.returncode:
        raise AppError(r.stderr.strip() or r.stdout.strip() or f'{args[0]} failed')
    return r


def graph():
    try:
        return json.loads(command(['pw-dump']).stdout)
    except ValueError as exc:
        raise AppError(f'Invalid PipeWire response: {exc}')


def sinks(data=None):
    data = graph() if data is None else data
    objects = {o['id']: o.get('info', {}).get('props', {}) for o in data}
    result = []
    for o in data:
        p = o.get('info', {}).get('props', {})
        if p.get('media.class') != 'Audio/Sink':
            continue
        d = objects.get(p.get('device.id'), {})
        result.append({'id': o['id'], 'name': p['node.name'],
                       'label': p.get('node.description', p['node.name']),
                       'serial': p.get('object.serial'),
                       'device_name': d.get('device.name'),
                       'is_headset': d.get('device.vendor.id') == '0x054c' and d.get('device.product.id') == '0x0ecc'})
    return result


def make_config(headset_name, fallback_name, available):
    by_name = {s['name']: s for s in available}
    if headset_name not in by_name or fallback_name not in by_name:
        raise AppError('Selected output is unavailable. Refresh devices and try again.')
    h, f = by_name[headset_name], by_name[fallback_name]
    if not h['is_headset']:
        raise AppError('Headset output must belong to a supported PlayStation Link adapter (054c:0ecc).')
    if h['name'] == f['name'] or f['is_headset']:
        raise AppError('Choose a fallback output that is not the PlayStation Link adapter.')
    return {'version': 1, 'headset_sink': h['name'], 'speakers_sink': f['name'],
            'headset_device': h['device_name'], 'speakers_device': f['device_name']}


def save_selection(headset, fallback, path=None):
    value = make_config(headset, fallback, sinks())
    atomic_json(path or config_path(), value)
    return value


def resolve(config, role, available):
    key = 'headset' if role == 'headset' else 'speakers'
    exact = [s for s in available if s['name'] == config[key + '_sink']]
    if len(exact) == 1:
        return exact[0]
    device = config.get(key + '_device')
    same_device = [s for s in available if device and s.get('device_name') == device]
    if len(same_device) == 1:
        return same_device[0]
    raise AppError(f'{role.capitalize()} output is unavailable or ambiguous. Waiting for it to return.')


def classify(raw):
    if len(raw) != 34 or raw[0] != 0x82:
        return 'unknown'
    if not any(raw[1:]):
        return 'disconnected'
    return {(1, 0x10): 'connected', (1, 0x30): 'connected', (1, 0x20): 'shutdown'}.get(tuple(raw[1:3]), 'unknown')


class Adapter:
    def __init__(self):
        self.fd = None
        self.identity = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
        self.fd, self.identity = None, None

    def read(self):
        try:
            matches = []
            for p in Path('/sys/class/hidraw').glob('hidraw*'):
                try:
                    if HID_ID in (p / 'device/uevent').read_text():
                        matches.append(p)
                except FileNotFoundError:
                    continue
            if not matches:
                self.close()
                return 'adapter-absent', None
            if len(matches) != 1:
                self.close()
                return 'unknown', 'Multiple PlayStation Link adapters are not supported yet.'
            device = Path('/dev') / matches[0].name
            identity = (str(device), device.stat().st_ino)
            if identity != self.identity:
                self.close()
                self.fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
                self.identity = identity
            raw = bytearray(64)
            raw[0] = 0x82
            length = fcntl.ioctl(self.fd, 0xC0404807, raw, True)
            state = classify(bytes(raw[:length]))
            return state, 'Unrecognized headset status; keeping current output.' if state == 'unknown' else None
        except PermissionError:
            self.close()
            return 'unknown', 'Cannot read adapter. Check device permissions and reconnect the USB adapter.'
        except OSError as exc:
            self.close()
            return 'unknown', f'Cannot read adapter: {exc}'


class Router:
    """Three consecutive known readings; unknown/errors never select an output."""
    def __init__(self):
        self.candidate = None
        self.count = 0
        self.state = None
        self.applied = None

    def observe(self, state):
        if state == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = state, 1
        if self.count < 3 or state == 'unknown':
            return None
        self.state = state
        return 'headset' if state == 'connected' else 'fallback' if state in ('shutdown', 'disconnected', 'adapter-absent') else None

    def route(self, config, role, data, dry_run=False):
        output = resolve(config, role, sinks(data))
        cookie = next((o.get('info', {}).get('cookie') for o in data if o.get('type') == 'PipeWire:Interface:Core'), None)
        fingerprint = (output['name'], cookie, output['serial'])
        if fingerprint == self.applied:
            return output['label']
        if not dry_run:
            command(['wpctl', 'set-default', str(output['id'])])
        self.applied = fingerprint
        return output['label']


def service_status():
    r = command(['systemctl', '--user', 'show', UNIT, '--property=ActiveState,UnitFileState,FragmentPath'], check=False)
    if r.returncode:
        return {'active': 'unavailable', 'autostart': False, 'error': r.stderr.strip()}
    fields = dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)
    unit_path = fields.get('FragmentPath', '')
    try:
        legacy = '.local/bin/pulse-elite-autoswitch' in Path(unit_path).read_text() if unit_path else False
    except OSError:
        legacy = False
    return {'legacy_installation': legacy, 'active': fields.get('ActiveState', 'unknown'),
            'autostart': fields.get('UnitFileState') == 'enabled',
            'unit_path': fields.get('FragmentPath', '')}


def service(action, path=None):
    if action in ('start', 'restart', 'enable'):
        load_config(path)
    if action == 'enable':
        # Startup policy is deliberately independent from running now.
        args = ['enable', UNIT]
    elif action == 'disable':
        args = ['disable', UNIT]
    else:
        args = [action, UNIT]
    command(['systemctl', '--user'] + args)
    return service_status()


def status(path=None):
    result = {'service': service_status()}
    try:
        result['configuration'] = load_config(path)
    except AppError as exc:
        result['configuration_error'] = str(exc)
    a = Adapter()
    try:
        result['headset'], result['device_error'] = a.read()
    finally:
        a.close()
    try:
        snapshot = json.loads((runtime_path() / 'pulse-elite-autoswitch-status.json').read_text())
        if time.time() - snapshot.get('timestamp', 0) < 10 and result['service']['active'] == 'active':
            result['daemon'] = snapshot
    except (OSError, ValueError, AppError):
        pass
    return result


def migrate(packaged_unit=None):
    packaged = Path(packaged_unit) if packaged_unit else Path('/usr/lib/systemd/user') / UNIT
    if not packaged.exists() or not any(command in packaged.read_text() for command in ('/usr/bin/ps-pulse run', '/usr/bin/pulse-elite-autoswitch run')):
        raise AppError('Install the new core package before migrating.')
    paths = [Path.home() / '.local/bin/pulse-elite-autoswitch',
             config_path().parent.parent / 'systemd/user' / UNIT]
    existing = [p for p in paths if p.exists()]
    if not existing:
        return {'message': 'No manual installation found.'}
    for p in existing:
        text = p.read_text()
        if not any(token in text for token in ('pulse-elite-autoswitch', '054C:00000ECC', '054C:00000ECC'.lower())):
            raise AppError(f'Unrecognized file; migration will not replace {p}')
    before = service_status()
    backup = config_path().parent / ('migration-backup-' + str(time.time_ns()))
    backup.mkdir(parents=True, mode=0o700)
    # Preserve both originals before making any change.
    for p in existing:
        shutil.copy2(p, backup / p.name)
    command(['systemctl', '--user', 'disable', '--now', UNIT])
    for p in existing:
        p.unlink()
    command(['systemctl', '--user', 'daemon-reload'])
    configured = False
    try:
        load_config()
        configured = True
    except AppError:
        pass
    if configured and before['autostart']:
        service('enable')
    if configured and before['active'] == 'active':
        service('start')
    return {'backup': str(backup), 'configured': configured,
            'message': 'Migration complete. Configure outputs before starting.' if not configured else 'Migration complete.'}

