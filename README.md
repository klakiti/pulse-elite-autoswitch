# PS-Pulse for Linux

Automatically switch between a Sony PULSE Elite headset and a selected fallback audio output. Configure it through a desktop window or entirely from the command line.

**v0.2.1 is a first-release candidate.** The headset protocol and live routing were tested on Zorin OS 18.1 with the `054c:0ecc` PlayStation Link adapter, PipeWire 1.0.5, and WirePlumber 0.4.17. Fresh package installation, reboot/start-at-login recovery, and physical adapter unplug/replug during playback are verified on that PC. Suspend, upgrades, package removal, and additional reconnect scenarios still need end-to-end hardware acceptance tests. Automated tests cover their routing and recovery logic.

## Install with one command

On Zorin OS, Ubuntu 22.04+, Debian 12+, or a compatible apt-based distribution with PipeWire, run this in your desktop terminal:

```bash
curl -fsSL https://github.com/klakiti/pulse-elite-autoswitch/releases/download/v0.2.1/install.sh | bash
```

The installer downloads the versioned desktop and CLI packages, verifies their SHA-256 checksums, and asks for your sudo password to install them and dependencies through apt. Run it as your normal user. It reloads the user service definitions and restarts an already-running switcher after an upgrade. Existing preferences are preserved.

Then open **PS-Pulse** from the applications menu, select your fallback output, and click **Enable**. Start at login is optional. The installer does not guess your output device or enable an unconfigured service.

For CLI only, append `-s -- --cli` to `bash` in the command above. To download and verify packages without installing them, use `bash -s -- --download-only`. You can inspect [the installer](https://github.com/klakiti/pulse-elite-autoswitch/releases/download/v0.2.1/install.sh) before running it. Other Linux package managers are not supported yet.

### Install packages manually

The core package contains the daemon and CLI; the optional desktop package adds a GTK 3 setup window. No Python packages from pip are required.

From the directory containing the built packages:

```bash
# Desktop UI plus CLI
sudo apt install ./ps-pulse_0.2.1_all.deb ./ps-pulse-desktop_0.2.1_all.deb

# Or just the core/CLI
sudo apt install ./ps-pulse_0.2.1_all.deb
```

Installation registers the user service and adapter permissions. It does not choose an output or start routing automatically. If device access is unavailable afterward, unplug and reconnect the adapter while logged into your local desktop session.

### Upgrading the earlier manual installation

The previous `~/.local/bin` script and user unit override the packaged versions. After installing the package, open the desktop app and choose **Upgrade previous manual setup**, or run:

```bash
/usr/bin/ps-pulse migrate
```

Migration backs up recognized old files under the user's configuration directory before retiring them. With no saved configuration, switching pauses until you select outputs and start it. Existing valid configuration and enabled/running service preferences are retained where possible. Migration does not remove unrelated files or the existing local udev rule.

## Desktop setup

Open **PS-Pulse** from the applications menu, or run:

```bash
/usr/bin/ps-pulse gui
```

1. Confirm the detected PlayStation Link playback output.
2. Select a fallback output, such as speakers or monitor audio.
3. Choose whether to start at login. Device selections and the login preference save immediately.
4. Click **Enable** to start routing or **Disable** to stop it without changing the login preference.

The headset indicator is green when Connected and red when Disconnected (including an unplugged adapter). Read errors appear separately; an unconfirmed connection displays Disconnected.

Read errors appear below the controls. Configuration changes from the CLI appear on refresh; pending desktop edits are preserved while saving.

## CLI setup and controls

```bash
ps-pulse devices
ps-pulse configure                 # interactive terminal picker
ps-pulse configure --fallback 'EXACT_NODE_NAME' --json
ps-pulse show-config --json
ps-pulse status --json
ps-pulse start                     # start now
ps-pulse stop                     # stop now; retain login preference
ps-pulse autostart enable                    # enable start-at-login only
ps-pulse autostart disable                   # disable start-at-login only
ps-pulse dry-run --duration 30      # no routing changes
```

`configure` automatically selects the single supported headset output. Use `--headset NODE_NAME` if explicit selection is needed. A noninteractive caller must supply `--fallback`; `devices --json` provides machine-readable choices. Device names are arguments, never shell commands.

The CLI has no GTK or display-server dependency. It still needs the correct user's PipeWire session, systemd user manager, and HID permissions. Arbitrary SSH sessions are not guaranteed audio/device access.

Configuration is stored at `$XDG_CONFIG_HOME/pulse-elite-autoswitch/config.json`, defaulting to `~/.config/pulse-elite-autoswitch/config.json`. Both interfaces use the same validation and atomic writes. Node names and physical device names are saved, not transient IDs. If a profile changes, a unique output on the same physical device can be used; ambiguous alternatives require selection again.

For foreground experiments, put `--config /path/to/config.json` before the subcommand. Service controls and the desktop UI always use the standard per-user configuration.

Exit codes: `0` success, `1` operational/configuration error, `2` argument syntax error, `130` interrupted CLI input. Read-only `status` reports detected problems in its JSON fields; successfully obtaining that status returns `0`. JSON-capable commands return operational errors as `{"error": "..."}` with exit code `1`.

## Routing behavior

- Poll HID report `0x82` every half-second; confirm three readings before switching.
- Connected headset: select Pulse Elite.
- Headset shutdown, headset disconnected, or **USB adapter removed**: select the configured fallback.
- Reconnected adapter: rediscover it; switch to the headset only after confirming connection and output availability.
- Unknown status or permission/read error: keep the current output.
- Missing fallback: report it and retry when it returns, without deliberately selecting an arbitrary replacement. PipeWire may apply its own fallback policy.
- Preserve microphone routing and volume settings.
- Detect PipeWire restart and changed output IDs; retry routing without restarting the app.
- A manual output change is respected until the next relevant headset/adapter transition or recovery.

Applications pinned to a specific output may not follow the default. Existing Chrome playback did follow it during hardware testing. Multiple supported adapters at once are not supported yet. See [PROTOCOL.md](PROTOCOL.md) for evidence and firmware limitations.

## Troubleshooting and removal

```bash
systemctl --user status pulse-elite-autoswitch.service
journalctl --user -u pulse-elite-autoswitch.service -n 50 --no-pager
ps-pulse devices --json
```

For permission errors, check that your local login session is active and reconnect the USB adapter. For unavailable outputs, refresh devices and save a new selection. For a duplicate instance, stop the older service or use the migration command.

To remove:

```bash
ps-pulse autostart disable
ps-pulse stop
sudo apt remove ps-pulse-desktop ps-pulse
systemctl --user daemon-reload
```

Configuration and migration backups are preserved. Delete them explicitly only if no longer needed. A previous manually installed `/etc/udev/rules.d/70-pulse-elite.rules` is also preserved; remove it separately if you no longer want its permissions. Reconnect the adapter after changing rules.

## Build and test

```bash
python3 -m unittest discover -s tests -v
python3 build-deb.py
# Outputs: dist/*.deb and dist/SHA256SUMS
```

Build requires `dpkg-deb` and Python 3.10+. GUI tests run when GTK 3 and a display are available; they are skipped in core-only environments. The build does not install packages or change the running service. Package files and personal configuration are excluded from Git.

Work is developed on feature branches and submitted through pull requests. Do not merge the v0.1 candidate until package installation and hardware acceptance checks pass. See [TESTING.md](TESTING.md) and [ROADMAP.md](ROADMAP.md).

## Research reference

[Jprnp/pslink-libusb](https://github.com/Jprnp/pslink-libusb) provided the lead that this adapter exposes HID status reports. The Linux implementation was written separately and validated against local device reports; it does not use Windows driver replacements or send device-setting reports.

### Upgrading from Pulse Elite AutoSwitch

The `ps-pulse` and `ps-pulse-desktop` packages replace the old packages through apt. The existing configuration directory, internal module path, and systemd service name are retained to preserve device settings and login preferences. The desktop launcher is now PS-Pulse. CLI service controls are `ps-pulse start`, `ps-pulse stop`, and `ps-pulse autostart enable|disable`. Normal controls print a short confirmation; add `--json` for diagnostics or scripts. `ps-pulse status --json` includes the full service and detector details.

### Contextual command help

The desktop package includes the full CLI. Run `ps-pulse` by itself to list commands and descriptions. Incomplete commands such as `ps-pulse autostart` show the available next arguments. You can also request contextual help explicitly:

```bash
ps-pulse '?'
ps-pulse autostart '?'
ps-pulse configure '?'
ps-pulse autostart enable --help
```

Quote `?` to prevent shell wildcard expansion. This is help after pressing Enter, rather than a separate interactive shell. Help never starts or stops the service. Existing `-h` and `--help` remain available; invalid arguments still produce an error.
