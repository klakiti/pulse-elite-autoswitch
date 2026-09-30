import fcntl
import logging
from pathlib import Path
import signal
import time
from . import core


def run(path=None, dry_run=False, duration=None):
    if not dry_run:
        core.load_config(path)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    lock_name = 'pulse-elite-autoswitch-dry-run.lock' if dry_run else 'pulse-elite-autoswitch.lock'
    with (core.runtime_path() / lock_name).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise core.AppError('Another instance is already running.')
        running = [True]
        def stop(*_):
            running[0] = False
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        adapter, router = core.Adapter(), core.Router()
        start = last = time.clock_gettime(time.CLOCK_BOOTTIME)
        previous = None
        next_route = 0
        previous_config = None
        last_route_key = None
        output = None
        route_error = None
        try:
            while running[0]:
                if str(Path(__file__).resolve()).startswith("/usr/lib/pulse-elite-autoswitch/") and not Path("/usr/bin/ps-pulse").exists():
                    logging.info("Package removed; stopping")
                    break
                now = time.clock_gettime(time.CLOCK_BOOTTIME)
                if duration and now - start >= duration:
                    break
                if now - last > 10:
                    adapter.close()
                    router = core.Router()
                    next_route = 0
                last = now
                state, error = adapter.read()
                role = router.observe(state)
                try:
                    config = core.load_config(path)
                    if config != previous_config:
                        router.applied = None
                        previous_config = config
                        next_route = 0
                    if role:
                        key = (role, adapter.identity)
                        if key != last_route_key:
                            next_route = 0
                            router.applied = None
                            last_route_key = key
                        if now >= next_route:
                            next_route = now + 3
                            output = router.route(config, role, core.graph(), dry_run)
                            route_error = None
                except core.AppError as exc:
                    route_error = str(exc)
                message = (state, error, output, route_error)
                if message != previous:
                    logging.info('%s | %s | %s', state, output or 'No routing change', error or route_error or ('Dry run' if dry_run else 'Ready'))
                    previous = message
                if not dry_run:
                    core.atomic_json(core.runtime_path() / 'pulse-elite-autoswitch-status.json',
                                     {'timestamp': time.time(), 'headset': state, 'last_selected_output': output,
                                      'error': error or route_error, 'config_path': str(path or core.config_path())})
                time.sleep(0.5)
        finally:
            adapter.close()
