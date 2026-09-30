import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('autoswitch', Path(__file__).resolve().parents[1] / 'pulse_elite_autoswitch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DetectorTests(unittest.TestCase):
    def test_measured_states(self):
        for flag, expected in ((0x10, 'connected'), (0x20, 'shutdown')):
            with self.subTest(flag=flag):
                self.assertEqual(module.classify(bytes((0x82, 1, flag, 6)) + bytes(30)), expected)
        self.assertEqual(module.classify(bytes((0x82,)) + bytes(33)), 'disconnected')

    def test_unrelated_status_byte_can_change(self):
        for value in (0, 6, 255):
            self.assertEqual(module.classify(bytes((0x82, 1, 0x10, value)) + bytes(30)), 'connected')

    def test_unrecognized_and_truncated_reports_hold_output(self):
        for report in (b'', b'\x82', bytes(34), bytes((0x82, 1, 0x30)) + bytes(31),
                       bytes((0x82, 2, 0x10)) + bytes(31), bytes((0x82,)) + bytes(32) + b'\x01'):
            with self.subTest(report=report):
                self.assertEqual(module.classify(report), 'unknown')

    def test_sink_fingerprint_changes_after_server_restart(self):
        def graph(cookie):
            return json.dumps([
                {'type': 'PipeWire:Interface:Core', 'info': {'cookie': cookie}},
                {'id': 33, 'type': 'PipeWire:Interface:Node', 'info': {'props': {
                    'media.class': 'Audio/Sink', 'node.name': 'headset', 'object.serial': 55}}}])
        with patch.object(module.subprocess, 'check_output', side_effect=[graph(1), graph(2)]):
            before = module.graph_target('headset')
            after = module.graph_target('headset')
        self.assertEqual(before[0], after[0])
        self.assertNotEqual(before[1], after[1])

    def test_missing_sink_is_not_replaced_by_another_output(self):
        graph = json.dumps([{'type': 'PipeWire:Interface:Core', 'info': {'cookie': 1}}])
        with patch.object(module.subprocess, 'check_output', return_value=graph):
            with self.assertRaises(RuntimeError):
                module.graph_target('missing')


if __name__ == '__main__':
    unittest.main()
