"""Optional GTK desktop UI; all configuration and control use the shared core."""
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from . import core, __version__



class Setup(Gtk.Box):
    def __init__(self, autoload=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_border_width(24)
        self.busy = False
        self.dirty = False
        self.pending = set()
        self.failed_changes = set()
        self.running = False
        self.legacy = False
        self.updating = False
        self.destroyed = False
        self.outputs = []
        self.connect('destroy', self.on_destroy)
        title = Gtk.Label(xalign=0)
        title.set_markup('<span size="xx-large" weight="bold">PS-Pulse</span>')
        self.pack_start(title, False, False, 0)
        intro = Gtk.Label(label='Your headset when connected. Your chosen output when it disconnects.', xalign=0)
        intro.set_line_wrap(True)
        self.pack_start(intro, False, False, 0)
        status_row = Gtk.Box(spacing=8)
        self.indicator = Gtk.Label()
        self.status_label = Gtk.Label(label='Disconnected', xalign=0)
        self.indicator.set_markup('<span foreground="#c01c28">●</span>')
        status_row.pack_start(self.indicator, False, False, 0)
        status_row.pack_start(self.status_label, False, False, 0)
        self.pack_start(status_row, False, False, 0)
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
        self.toggle_button = Gtk.Button(label='Enable')
        self.toggle_button.get_style_context().add_class('suggested-action')
        self.refresh_button = Gtk.Button(label='Refresh devices')
        for button in (self.toggle_button, self.refresh_button):
            buttons.pack_start(button, False, False, 0)
        self.toggle_button.connect('clicked', lambda *_: self.control())
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

    def on_close(self, *_):
        # Keep the main loop alive until queued writes finish; a daemon worker
        # otherwise disappears when the process exits.
        if self.busy or self.pending:
            self.message.set_text('Finishing the current operation. Please close again in a moment.')
            return True
        return False

    def on_destroy(self, *_):
        self.destroyed = True
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def changed(self, widget):
        if not self.updating and not self.legacy:
            self.dirty = True
            self.pending.update(self.failed_changes)
            self.failed_changes.clear()
            self.pending.add('autostart' if widget is self.autostart else 'devices')
            self.save()

    def update_controls(self):
        self.toggle_button.set_label('Disable' if self.running else 'Enable')
        self.toggle_button.set_sensitive(not self.busy and not self.legacy and
                                         (self.running or not self.dirty))
        self.refresh_button.set_sensitive(not self.busy)
        for widget in (self.headset, self.fallback, self.autostart):
            widget.set_sensitive(not self.legacy)

    def periodic(self):
        self.refresh()
        return not self.destroyed

    def job(self, function, complete, failed=None):
        if self.busy or self.destroyed:
            return
        self.busy = True
        self.update_controls()
        def worker():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, str(exc)
            def finish():
                if self.destroyed:
                    return False
                self.busy = False

                if error:
                    self.message.set_text(error)
                    if failed:
                        failed()
                else:
                    complete(value)
                self.update_controls()
                if self.pending:
                    self.save()
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
        legacy = self.legacy = state['service'].get('legacy_installation', False)
        self.migrate_button.set_visible(legacy)
        self.running = state['service']['active'] == 'active'
        connected = state.get('headset') == 'connected'
        self.status_label.set_text('Connected' if connected else 'Disconnected')
        color = '#26a269' if connected else '#c01c28'
        self.indicator.set_markup(f'<span foreground="{color}">●</span>')
        self.update_controls()
        error = state['service'].get('error') or state.get('device_error') or state.get('audio_error') or state.get('daemon', {}).get('error') or state.get('configuration_error')
        if legacy:
            error = 'Previous manual installation detected. Upgrade it before using these controls; originals will be backed up.'

        if state.get('headset') == 'unknown' and not error:
            error = 'Unable to read headset status. Connection is not confirmed.'
        if not self.dirty:
            self.message.set_text(error or '')

    def save(self):
        if self.busy or not self.pending or self.destroyed:
            return
        changes = self.pending.copy()
        self.pending.clear()
        headset, fallback = self.headset.get_active_id(), self.fallback.get_active_id()
        autostart = self.autostart.get_active()
        self.message.set_text('Saving…')
        def apply():
            if 'devices' in changes:
                core.save_selection(headset, fallback)
            if 'autostart' in changes:
                core.service('enable' if autostart else 'disable')
        def done(_):
            self.dirty = bool(self.pending)
            self.message.set_text('')
        def failed():
            self.failed_changes.update(changes)
            if self.pending:
                self.pending.update(changes)
                self.failed_changes.clear()
        self.job(apply, done, failed)

    def control(self):
        action = 'stop' if self.running else 'start'
        def done(state):
            self.running = state['active'] == 'active'
            self.update_controls()
            self.refresh()
        self.job(lambda: core.service(action), done)


def launch():
    if not Gtk.init_check()[0]:
        raise core.AppError('No graphical display. Use the CLI configure command instead.')
    window = Gtk.Window(title='PS-Pulse')
    window.set_default_size(660, 430)
    setup = Setup()
    window.add(setup)
    window.connect('delete-event', setup.on_close)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()
