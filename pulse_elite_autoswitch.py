#!/usr/bin/python3
"""Poll Sony PS Link status and switch playback outputs for the logged-in user."""
import argparse
import fcntl
import logging
import os
from pathlib import Path
import signal
import subprocess
import json
import time

HID_ID = 'HID_ID=0003:0000054C:00000ECC'
RUNNING = True


def classify(data):
    if len(data) != 34 or data[0] != 0x82:
        return 'unknown'
    if not any(data[1:]):
        return 'disconnected'
    # Observed over five on/off cycles. Other bytes include battery/status data.
    if data[1:3] == bytes((1, 0x10)):
        return 'connected'
    if data[1:3] == bytes((1, 0x20)):
        return 'shutdown'
    return 'unknown'


def discover():
    matches = []
    for path in Path('/sys/class/hidraw').glob('hidraw*'):
        try:
            if HID_ID in (path / 'device/uevent').read_text():
                matches.append(Path('/dev') / path.name)
        except FileNotFoundError:
            continue
    if len(matches) > 1:
        raise RuntimeError('Multiple matching adapters; leaving audio unchanged')
    return matches[0] if matches else None


def graph_target(name):
    graph = json.loads(subprocess.check_output(['/usr/bin/pw-dump'], timeout=5))
    cookie = next(o['info']['cookie'] for o in graph if o['type'] == 'PipeWire:Interface:Core')
    sinks = [o for o in graph if o.get('info', {}).get('props', {}).get('media.class') == 'Audio/Sink'
             and o['info']['props'].get('node.name') == name]
    if len(sinks) != 1:
        raise RuntimeError('Selected audio output is unavailable')
    node = sinks[0]
    return node['id'], (name, cookie, node['info']['props']['object.serial'])


def stop(signum, frame):
    global RUNNING
    RUNNING = False


def parse_args():
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=config_home / 'pulse-elite-autoswitch/config.json')
    parser.add_argument('--list-sinks', action='store_true', help='List playback device names and exit')
    parser.add_argument('--dry-run', action='store_true', help='Log routing decisions without changing output')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.list_sinks:
        graph = json.loads(subprocess.check_output(['/usr/bin/pw-dump'], timeout=5))
        for obj in graph:
            props = obj.get('info', {}).get('props', {})
            if props.get('media.class') == 'Audio/Sink':
                print(props.get('node.description', 'Audio output'))
                print('  ' + props['node.name'])
        return
    try:
        config = json.loads(args.config.read_text())
        headset, speakers = config['headset_sink'], config['speakers_sink']
        if not all(isinstance(name, str) and name.strip() for name in (headset, speakers)):
            raise ValueError('Sink names must be nonempty strings')
        if headset == speakers:
            raise ValueError('Headset and speaker sinks must be different')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f'Invalid configuration at {args.config}: {exc}')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    lock = open(Path(os.environ['XDG_RUNTIME_DIR']) / 'pulse-elite-autoswitch.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another autoswitch instance is already running')
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    fd = None
    opened_identity = None
    candidate, count, stable = None, 0, None
    applied = None
    next_route_check = 0
    last_error = None
    last_tick = time.clock_gettime(time.CLOCK_BOOTTIME)
    logging.info('Started; reading report 0x82 every 0.5 seconds')
    try:
        while RUNNING:
            tick = time.clock_gettime(time.CLOCK_BOOTTIME)
            if tick - last_tick > 10:
                # Resume or a stalled session: reopen and re-evaluate current state.
                if fd is not None:
                    os.close(fd)
                fd, opened_identity, applied = None, None, None
                candidate, count = None, 0
            last_tick = tick
            try:
                device = discover()
                identity = (str(device), device.stat().st_ino) if device else None
                if identity != opened_identity:
                    if fd is not None:
                        os.close(fd)
                    fd, opened_identity = None, None
                    candidate, count, applied = None, 0, None
                if device is None:
                    state = 'adapter-absent'
                else:
                    if fd is None:
                        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
                        opened_identity = identity
                    buf = bytearray(64)
                    buf[0] = 0x82
                    length = fcntl.ioctl(fd, 0xC0404807, buf, True)
                    state = classify(bytes(buf[:length]))
                last_error = None
            except (OSError, RuntimeError) as exc:
                message = str(exc)
                if message != last_error:
                    logging.warning('Cannot read headset state; keeping current output: %s', message)
                last_error = message
                if fd is not None:
                    os.close(fd)
                fd, opened_identity = None, None
                state = 'unknown'
            if candidate == state:
                count += 1
            else:
                candidate, count = state, 1
            if count >= 3:
                if stable != state:
                    logging.info('Headset state: %s', state)
                    stable = state
                    next_route_check = 0
                target = headset if state == 'connected' else speakers if state in ('shutdown', 'disconnected', 'adapter-absent') else None
                if target and time.monotonic() >= next_route_check:
                    next_route_check = time.monotonic() + 5
                    try:
                        node_id, fingerprint = graph_target(target)
                        if fingerprint != applied:
                            if not args.dry_run:
                                subprocess.run(['/usr/bin/wpctl', 'set-default', str(node_id)],
                                               check=True, capture_output=True, timeout=5)
                            applied = fingerprint
                            logging.info('%s %s', 'Would select' if args.dry_run else 'Selected',
                                         'Pulse Elite' if target == headset else 'speakers')
                    except (OSError, RuntimeError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
                        logging.warning('Audio output not ready; will retry: %s', exc)
            time.sleep(0.5)
    finally:
        if fd is not None:
            os.close(fd)
        lock.close()
        logging.info('Stopped; leaving current audio output selected')


if __name__ == '__main__':
    main()
