"""Optional GTK desktop UI; all configuration and control use the shared core."""
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from . import core, __version__

LABELS = {'connected': 'Headset connected', 'shutdown': 'Headset disconnecting',
          'disconnected': 'Headset off / disconnected', 'adapter-absent': 'USB adapter disconnected',
          'unknown': 'Cannot determine headset state'}


class Setup(Gtk.Box):
    def __init__(self, autoload=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_border_width(24)
        self.busy = False
        self.dirty = False
        self.updating = False
        self.destroyed = False
        self.outputs = []
        self.connect('destroy', self.on_destroy)
        title = Gtk.Label(xalign=0)
        title.set_markup('<span size="xx-large" weight="bold">Pulse Elite AutoSwitch</span>')
        self.pack_start(title, False, False, 0)
        intro = Gtk.Label(label='Your headset when connected. Your chosen output when it disconnects.', xalign=0)
        intro.set_line_wrap(True)
        self.pack_start(intro, False, False, 0)
        self.status_label = Gtk.Label(label='Checking devices…', xalign=0)
        self.pack_start(self.status_label, False, False, 0)
        grid = Gtk.Grid(column_spacing=16, row_spacing=14)
        self.headset = Gtk.ComboBoxText()
        self.fallback = Gtk.ComboBoxText()
        for row, (label, combo) in enumerate((('Pulse Elite output', self.headset), ('Fallback output', self.fallback))):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            combo.set_hexpand(True)
            grid.attach(combo, 1, row, 1, 1)
            combo.connect('changed', self.changed)
        self.pack_start(grid, False, False, 0)
        hint = Gtk.Label(label='The fallback is also used when the USB adapter is unplugged.', xalign=0)
        hint.set_line_wrap(True)
        self.pack_start(hint, False, False, 0)
        self.autostart = Gtk.CheckButton(label='Start automatic switching at login')
        self.autostart.connect('toggled', self.changed)
        self.pack_start(self.autostart, False, False, 0)
        buttons = Gtk.Box(spacing=8)
        self.save_button = Gtk.Button(label='Save settings')
        self.save_button.get_style_context().add_class('suggested-action')
        self.start_button = Gtk.Button(label='Start switching')
        self.pause_button = Gtk.Button(label='Pause')
        self.refresh_button = Gtk.Button(label='Refresh devices')
        for b in (self.save_button, self.start_button, self.pause_button, self.refresh_button):
            buttons.pack_start(b, False, False, 0)
        self.save_button.connect('clicked', lambda *_: self.save())
        self.start_button.connect('clicked', lambda *_: self.control('start'))
        self.pause_button.connect('clicked', lambda *_: self.control('stop'))
        self.refresh_button.connect('clicked', lambda *_: self.refresh())
        self.pack_start(buttons, False, False, 0)
        self.migrate_button = Gtk.Button(label='Upgrade previous manual setup')
        self.migrate_button.set_no_show_all(True)
        self.migrate_button.connect('clicked', lambda *_: self.job(core.migrate, lambda _: self.refresh()))
        self.pack_start(self.migrate_button, False, False, 0)
        self.message = Gtk.Label(xalign=0)
        self.message.set_line_wrap(True)
        self.message.set_selectable(True)
        self.pack_start(self.message, False, False, 0)
        footer = Gtk.Label(label=f'Version {__version__} · Volumes and microphone settings stay as you set them.', xalign=0)
        footer.set_line_wrap(True)
        self.pack_end(footer, False, False, 0)
        self.timer = GLib.timeout_add_seconds(3, self.periodic) if autoload else None
        if autoload:
            self.refresh()

    def on_destroy(self, *_):
        self.destroyed = True
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def changed(self, *_):
        if not self.updating:
            self.dirty = True

    def periodic(self):
        self.refresh()
        return not self.destroyed

    def job(self, function, complete):
        if self.busy or self.destroyed:
            return
        self.busy = True
        for b in (self.save_button, self.start_button, self.pause_button, self.refresh_button):
            b.set_sensitive(False)
        def worker():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, str(exc)
            def finish():
                if self.destroyed:
                    return False
                self.busy = False
                for b in (self.save_button, self.start_button, self.pause_button, self.refresh_button):
                    b.set_sensitive(True)
                if error:
                    self.message.set_text(error)
                else:
                    complete(value)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        def read():
            status = core.status()
            try:
                outputs = core.sinks()
            except core.AppError as exc:
                outputs = []
                status['audio_error'] = str(exc)
            return status, outputs
        self.job(read, lambda value: self.populate(*value))

    def populate(self, state, outputs):
        self.outputs = outputs
        cfg = state.get('configuration', {})
        current = (self.headset.get_active_id(), self.fallback.get_active_id())
        self.updating = True
        for combo, role, previous in ((self.headset, 'headset', current[0]), (self.fallback, 'speakers', current[1])):
            selection = previous if self.dirty else cfg.get(role + '_sink')
            choices = [s for s in outputs if s['is_headset'] == (role == 'headset')]
            combo.remove_all()
            for s in choices:
                label = s['label']
                if sum(x['label'] == label for x in choices) > 1:
                    label += ' · ' + (s['device_name'] or s['name'])
                combo.append(s['name'], label)
            if selection and selection not in [s['name'] for s in choices]:
                combo.append(selection, 'Unavailable: ' + selection)
            if selection:
                combo.set_active_id(selection)
            elif role == 'headset' and len(choices) == 1:
                combo.set_active(0)
        if not self.dirty:
            self.autostart.set_active(state['service']['autostart'])
        self.updating = False
        legacy = state['service'].get('legacy_installation', False)
        self.migrate_button.set_visible(legacy)
        running = state['service']['active'] == 'active'
        self.status_label.set_text(LABELS.get(state.get('headset'), 'Checking headset…') + '\n' +
                                   ('Automatic switching is running' if running else 'Automatic switching is paused'))
        self.start_button.set_sensitive(not running)
        self.pause_button.set_sensitive(running)
        error = state.get('device_error') or state.get('audio_error') or state.get('daemon', {}).get('error') or state.get('configuration_error')
        if legacy:
            error = 'Previous manual installation detected. Upgrade it before using these controls; originals will be backed up.'
            self.start_button.set_sensitive(False)
            self.save_button.set_sensitive(False)
        if not self.dirty:
            self.message.set_text(error or 'Ready. Choose your fallback output and save your settings.')

    def save(self):
        headset, fallback = self.headset.get_active_id(), self.fallback.get_active_id()
        autostart = self.autostart.get_active()
        def apply():
            core.save_selection(headset, fallback)
            core.service('enable' if autostart else 'disable')
        def done(_):
            self.dirty = False
            self.message.set_text('Settings saved. Use Start switching to begin, or Pause to stop.')
        self.job(apply, done)

    def control(self, action):
        if action == 'start' and self.dirty:
            self.message.set_text('Save your device selections before starting.')
            return
        self.job(lambda: core.service(action), lambda _: self.refresh())


def launch():
    if not Gtk.init_check()[0]:
        raise core.AppError('No graphical display. Use the CLI configure command instead.')
    window = Gtk.Window(title='Pulse Elite AutoSwitch')
    window.set_default_size(660, 430)
    window.add(Setup())
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()
