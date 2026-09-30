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

    def test_configuration_refresh_and_distinct_adapter_message(self):
        self.ui.populate(self.state,self.outputs)
        self.assertEqual(self.ui.fallback.get_active_id(),'speakers')
        self.assertIn('USB adapter disconnected',self.ui.status_label.get_text())
        self.assertFalse(self.ui.dirty)

    def test_ui_saves_through_same_backend_as_cli(self):
        self.ui.populate(self.state,self.outputs)
        self.ui.job = lambda fn, done: done(fn())
        with patch.object(core,'save_selection') as save, patch.object(core,'service') as service:
            self.ui.save()
        save.assert_called_once_with('headset','speakers')
        service.assert_called_once_with('disable')

    def test_pending_user_edits_are_not_replaced_by_periodic_refresh(self):
        self.ui.populate(self.state,self.outputs)
        self.ui.autostart.set_active(True)
        self.ui.populate(self.state,self.outputs)
        self.assertTrue(self.ui.autostart.get_active())
        self.assertTrue(self.ui.dirty)
