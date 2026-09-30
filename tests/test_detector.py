import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pulse_elite import core, cli


def audio_graph(cookie=1, fallback=True, headset=True):
    data = [{'id': 0, 'type': 'PipeWire:Interface:Core', 'info': {'cookie': cookie}}]
    for enabled, name, ident, vendor, product in ((headset, 'headset', 10, '0x054c', '0x0ecc'), (fallback, 'speakers', 20, '0x1234', '0xabcd')):
        if enabled:
            data.extend([
                {'id': ident, 'info': {'props': {'device.name': 'card.' + name, 'device.vendor.id': vendor, 'device.product.id': product}}},
                {'id': ident + 1, 'info': {'props': {'media.class': 'Audio/Sink', 'node.name': name,
                                                  'node.description': name.title(), 'device.id': ident, 'object.serial': ident + 100}}}])
    return data


def configured():
    return core.make_config('headset', 'speakers', core.sinks(audio_graph()))


class DetectorTests(unittest.TestCase):
    def test_reports_with_variable_other_bytes(self):
        for flag, expected in ((0x10, 'connected'), (0x20, 'shutdown')):
            for value in (0, 6, 255):
                self.assertEqual(core.classify(bytes((0x82, 1, flag, value)) + bytes(30)), expected)
        self.assertEqual(core.classify(bytes((0x82,)) + bytes(33)), 'disconnected')

    def test_unknown_reports_never_guess_off(self):
        for report in (b'', b'\x82', bytes(34), bytes((0x82, 1, 0x30)) + bytes(31), bytes((0x82, 2, 0x10)) + bytes(31)):
            self.assertEqual(core.classify(report), 'unknown')

    def test_debounce_and_unknown_interrupts_confirmation(self):
        r = core.Router()
        self.assertEqual([r.observe(s) for s in ['connected', 'connected', 'unknown', 'connected', 'connected', 'connected']],
                         [None, None, None, None, None, 'headset'])
        for _ in range(5):
            self.assertIsNone(r.observe('unknown'))

    def test_adapter_unplug_and_replug_sequence(self):
        r = core.Router()
        sequence = ['connected'] * 3 + ['adapter-absent'] * 3 + ['disconnected'] * 3 + ['connected'] * 3
        targets = [role for state in sequence if (role := r.observe(state))]
        self.assertEqual(targets, ['headset', 'fallback', 'fallback', 'headset'])

    def test_adapter_absent_at_startup(self):
        r = core.Router()
        self.assertEqual([r.observe('adapter-absent') for _ in range(3)], [None, None, 'fallback'])

    def test_missing_fallback_does_not_select_arbitrary_sink(self):
        r = core.Router()
        with patch.object(core, 'command') as command:
            with self.assertRaises(core.AppError):
                r.route(configured(), 'fallback', audio_graph(fallback=False))
            command.assert_not_called()
            r.route(configured(), 'fallback', audio_graph())
            command.assert_called_once_with(['wpctl', 'set-default', '21'])

    def test_server_restart_reapplies_even_if_node_id_reused(self):
        r = core.Router()
        with patch.object(core, 'command') as command:
            r.route(configured(), 'headset', audio_graph(1))
            r.route(configured(), 'headset', audio_graph(1))
            r.route(configured(), 'headset', audio_graph(2))
            self.assertEqual(command.call_count, 2)

    def test_profile_change_resolves_same_physical_device_only(self):
        choices = core.sinks(audio_graph())
        choices[1]['name'] = 'speakers.new-profile'
        self.assertEqual(core.resolve(configured(), 'fallback', choices)['name'], 'speakers.new-profile')
        choices.append(dict(choices[1], name='speakers.other-profile'))
        with self.assertRaises(core.AppError):
            core.resolve(configured(), 'fallback', choices)

    def test_dry_run_never_changes_audio(self):
        with patch.object(core, 'command') as command:
            core.Router().route(configured(), 'headset', audio_graph(), dry_run=True)
            command.assert_not_called()

    def test_same_or_unsupported_headset_rejected(self):
        choices = core.sinks(audio_graph())
        for h, f in [('headset', 'headset'), ('speakers', 'headset'), ('missing', 'speakers')]:
            with self.assertRaises(core.AppError):
                core.make_config(h, f, choices)

    def test_atomic_config_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            core.atomic_json(path, configured())
            self.assertEqual(core.load_config(path), configured())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            path.write_text('[]')
            with self.assertRaises(core.AppError):
                core.load_config(path)

    def test_noninteractive_setup_requires_explicit_fallback(self):
        with patch('sys.stdin.isatty', return_value=False):
            with self.assertRaises(core.AppError):
                cli.choose(core.sinks(audio_graph()), 'auto', None)

    def test_cli_json_error_is_parseable(self):
        output = io.StringIO()
        with patch.object(core, 'sinks', return_value=[]), contextlib.redirect_stdout(output):
            code = cli.main(['configure', '--json'])
        self.assertEqual(code, 1)
        self.assertIn('error', json.loads(output.getvalue()))

    def test_cli_config_saved_without_gui_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            with patch.object(core, 'sinks', return_value=core.sinks(audio_graph())), contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(['--config', str(path), 'configure', '--fallback', 'speakers', '--json'])
            self.assertEqual(code, 0)
            self.assertEqual(core.load_config(path)['speakers_sink'], 'speakers')

    def test_autostart_enable_does_not_start_service(self):
        with patch.object(core, 'load_config'), patch.object(core, 'service_status', return_value={}), patch.object(core, 'command') as cmd:
            core.service('enable')
            cmd.assert_called_once_with(['systemctl', '--user', 'enable', core.UNIT])

    def test_absent_adapter_closes_old_handle(self):
        a = core.Adapter()
        a.fd, a.identity = 99, ('old', 1)
        with patch('pathlib.Path.glob', return_value=[]), patch.object(core.os, 'close') as close:
            self.assertEqual(a.read(), ('adapter-absent', None))
            close.assert_called_once_with(99)


if __name__ == '__main__':
    unittest.main()

class AdapterTests(unittest.TestCase):
    def test_permission_error_is_not_adapter_absence(self):
        from types import SimpleNamespace
        adapter = core.Adapter()
        with patch('pathlib.Path.glob', return_value=[Path('/sys/class/hidraw/hidraw1')]), \
             patch('pathlib.Path.read_text', return_value=core.HID_ID), \
             patch('pathlib.Path.stat', return_value=SimpleNamespace(st_ino=1)), \
             patch.object(core.os, 'open', side_effect=PermissionError()):
            state, error = adapter.read()
        self.assertEqual(state, 'unknown')
        self.assertIn('permissions', error)

    def test_replaced_device_reopens_handle(self):
        from types import SimpleNamespace
        def ioctl(fd, request, buffer, mutate):
            buffer[:34] = bytes((0x82,)) + bytes(33)
            return 34
        adapter = core.Adapter()
        with patch('pathlib.Path.glob', return_value=[Path('/sys/class/hidraw/hidraw1')]), \
             patch('pathlib.Path.read_text', return_value=core.HID_ID), \
             patch('pathlib.Path.stat', side_effect=[SimpleNamespace(st_ino=1), SimpleNamespace(st_ino=2)]), \
             patch.object(core.os, 'open', side_effect=[100, 101]) as open_device, \
             patch.object(core.os, 'close') as close_device, \
             patch.object(core.fcntl, 'ioctl', side_effect=ioctl):
            self.assertEqual(adapter.read()[0], 'disconnected')
            self.assertEqual(adapter.read()[0], 'disconnected')
            self.assertEqual(open_device.call_count, 2)
            close_device.assert_called_once_with(100)
            adapter.close()

class MigrationTests(unittest.TestCase):
    def test_migration_backs_up_originals_and_does_not_start_unconfigured(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            exe = home / '.local/bin/pulse-elite-autoswitch'
            unit = home / '.config/systemd/user' / core.UNIT
            packaged = home / 'packaged.service'
            packaged.write_text('ExecStart=/usr/bin/pulse-elite-autoswitch run\n')
            for path in (exe, unit):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('old pulse-elite-autoswitch setup')
            with patch.object(Path, 'home', return_value=home), \
                 patch.dict(os.environ, {'XDG_CONFIG_HOME': str(home / '.config')}), \
                 patch.object(core, 'service_status', return_value={'active': 'active', 'autostart': True}), \
                 patch.object(core, 'command') as command:
                result = core.migrate(packaged)
            self.assertFalse(exe.exists())
            self.assertFalse(unit.exists())
            self.assertEqual((Path(result['backup']) / exe.name).read_text(), 'old pulse-elite-autoswitch setup')
            self.assertEqual((Path(result['backup']) / unit.name).read_text(), 'old pulse-elite-autoswitch setup')
            self.assertFalse(result['configured'])
            calls = [c.args[0] for c in command.call_args_list]
            self.assertEqual(calls, [['systemctl','--user','disable','--now',core.UNIT], ['systemctl','--user','daemon-reload']])
