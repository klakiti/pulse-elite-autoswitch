import contextlib
import io
import json
import unittest
from unittest.mock import patch
from pulse_elite import cli, core


class CliControlTests(unittest.TestCase):
    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(args)
        self.assertEqual(code, 0)
        return output.getvalue()

    def test_commands_map_to_service_actions_and_print_short_confirmations(self):
        for args, action, expected in ((['start'], 'start', 'Switching started.'),
                                       (['stop'], 'stop', 'Switching stopped.'),
                                       (['autostart', 'enable'], 'enable', 'Start at login enabled.'),
                                       (['autostart', 'disable'], 'disable', 'Start at login disabled.')):
            with patch.object(core, 'service', return_value={'active': 'active', 'unit_path': '/internal'}) as service:
                self.assertEqual(self.invoke(args).strip(), expected)
                service.assert_called_once_with(action)

    def test_json_preserves_machine_readable_service_result(self):
        with patch.object(core, 'service', return_value={'active': 'inactive'}):
            self.assertEqual(json.loads(self.invoke(['stop', '--json'])), {'active': 'inactive'})

    def test_status_omits_internal_paths_but_retains_errors(self):
        state = {'service': {'active': 'active', 'autostart': True, 'unit_path': '/internal'},
                 'headset': 'unknown', 'device_error': 'Read failed',
                 'daemon': {'error': 'Read failed', 'timestamp': 1234}}
        with patch.object(core, 'status', return_value=state):
            output = self.invoke(['status'])
        self.assertIn('Switching: running', output)
        self.assertIn('Headset: unknown', output)
        self.assertEqual(output.count('Read failed'), 1)
        self.assertNotIn('/internal', output)
        self.assertNotIn('1234', output)

    def help_output(self, args):
        output = io.StringIO()
        with patch.object(core, 'service') as service, contextlib.redirect_stdout(output):
            try:
                code = cli.main(args)
            except SystemExit as exc:
                code = exc.code
            self.assertEqual(code, 0)
            service.assert_not_called()
        return output.getvalue()

    def test_incomplete_commands_show_descriptive_help(self):
        self.assertIn('Start automatic switching', self.help_output([]))
        text = self.help_output(['autostart'])
        self.assertIn('Start switching automatically at login', text)
        self.assertIn('Do not start switching automatically at login', text)
        self.assertIn('Output to use', self.help_output(['configure', '--fallback']))

    def test_question_mark_and_standard_help_never_execute(self):
        for args in (['?'], ['-h'], ['--help'], ['start', '?'], ['start', '-h'],
                     ['autostart', '?'], ['autostart', 'enable', '?'],
                     ['autostart', 'enable', '--help'], ['--config', '/tmp/test', 'configure', '?']):
            self.assertIn('usage:', self.help_output(args))

    def test_invalid_argument_remains_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cli.main(['autostart', 'typo'])
        self.assertEqual(raised.exception.code, 2)
