import os
import unittest
from unittest.mock import patch
from pulse_elite import core

try:
    from pulse_elite.gui import Gtk, Setup
    DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')) and Gtk.init_check()[0]
except ImportError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, 'GTK/display unavailable; core and CLI remain testable')
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.ui = Setup(autoload=False)
        self.outputs = [dict(id=10, name='headset', label='Pulse Elite', device_name='sony', is_headset=True),
                        dict(id=20, name='speakers', label='Speakers', device_name='speaker-card', is_headset=False)]
        self.state = {'headset':'adapter-absent', 'service':{'active':'inactive','autostart':False},
                      'configuration':{'headset_sink':'headset','speakers_sink':'speakers'}}

    def tearDown(self):
        self.ui.destroy()

    def immediate_jobs(self):
        self.ui.job = lambda fn, done, failed=None: done(fn())

    def test_binary_connection_indicator(self):
        for state in ('disconnected', 'shutdown', 'adapter-absent', 'unknown', 'connected'):
            self.state['headset'] = state
            self.ui.populate(self.state, self.outputs)
            connected = state == 'connected'
            self.assertEqual(self.ui.status_label.get_text(), 'Connected' if connected else 'Disconnected')
            self.assertIn('#26a269' if connected else '#c01c28', self.ui.indicator.get_label())
        self.assertFalse(self.ui.dirty)

    def test_refresh_does_not_write_settings(self):
        with patch.object(core, 'save_selection') as save, patch.object(core, 'service') as service:
            self.ui.populate(self.state, self.outputs)
        save.assert_not_called()
        service.assert_not_called()

    def test_device_selection_saves_immediately(self):
        self.outputs.append(dict(id=30, name='other', label='Other', device_name='other-card', is_headset=False))
        self.ui.populate(self.state, self.outputs)
        self.immediate_jobs()
        with patch.object(core, 'save_selection') as save, patch.object(core, 'service') as service:
            self.ui.fallback.set_active_id('other')
        save.assert_called_once_with('headset', 'other')
        service.assert_not_called()
        self.assertFalse(self.ui.dirty)

    def test_login_preference_saves_without_revalidating_missing_devices(self):
        self.ui.populate(self.state, self.outputs)
        self.immediate_jobs()
        with patch.object(core, 'save_selection') as save, patch.object(core, 'service') as service:
            self.ui.autostart.set_active(True)
        save.assert_not_called()
        service.assert_called_once_with('enable')

    def test_edits_during_refresh_are_preserved_and_saved(self):
        self.ui.populate(self.state, self.outputs)
        self.ui.busy = True
        self.ui.autostart.set_active(True)
        self.ui.populate(self.state, self.outputs)
        self.assertTrue(self.ui.autostart.get_active())
        self.assertTrue(self.ui.dirty)
        self.ui.busy = False
        self.immediate_jobs()
        with patch.object(core, 'service') as service:
            self.ui.save()
        service.assert_called_once_with('enable')
        self.assertFalse(self.ui.dirty)

    def test_enable_disable_controls_running_service(self):
        self.immediate_jobs()
        self.ui.refresh = lambda: None
        for active, label, action, result in (('inactive', 'Enable', 'start', 'active'),
                                            ('active', 'Disable', 'stop', 'inactive')):
            self.state['service']['active'] = active
            self.ui.populate(self.state, self.outputs)
            self.assertEqual(self.ui.toggle_button.get_label(), label)
            with patch.object(core, 'service', return_value={'active': result}) as service:
                self.ui.control()
            service.assert_called_once_with(action)

    def drain_jobs(self):
        import time
        from pulse_elite.gui import GLib
        deadline = time.monotonic() + 3
        while self.ui.busy and time.monotonic() < deadline:
            while GLib.MainContext.default().iteration(False):
                pass
            time.sleep(0.005)
        self.assertFalse(self.ui.busy)

    def test_async_refresh_flushes_latest_edit(self):
        import threading
        ready = threading.Event()
        self.ui.populate(self.state, self.outputs)
        with patch.object(core, 'service') as service:
            self.ui.job(lambda: ready.wait(2), lambda _: self.ui.populate(self.state, self.outputs))
            self.ui.autostart.set_active(True)
            self.ui.autostart.set_active(False)
            self.ui.autostart.set_active(True)
            ready.set()
            self.drain_jobs()
        service.assert_called_once_with('enable')
        self.assertTrue(self.ui.autostart.get_active())
        self.assertFalse(self.ui.dirty)

    def test_failed_save_is_visible_and_retryable(self):
        self.ui.populate(self.state, self.outputs)
        with patch.object(core, 'service', side_effect=core.AppError('Cannot save login preference')):
            self.ui.autostart.set_active(True)
            self.drain_jobs()
        self.assertTrue(self.ui.dirty)
        self.assertIn('Cannot save', self.ui.message.get_text())
        self.assertFalse(self.ui.toggle_button.get_sensitive())
        with patch.object(core, 'service') as service:
            self.ui.autostart.set_active(False)
            self.drain_jobs()
        service.assert_called_once_with('disable')
        self.assertFalse(self.ui.dirty)

    def test_close_waits_for_pending_settings_write(self):
        self.ui.busy = True
        self.assertTrue(self.ui.on_close())
        self.ui.busy = False
        self.ui.pending.add('devices')
        self.assertTrue(self.ui.on_close())
        self.ui.pending.clear()
        self.assertFalse(self.ui.on_close())
