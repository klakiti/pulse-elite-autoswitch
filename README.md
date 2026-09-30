# Pulse Elite AutoSwitch for Linux

Automatically switch playback between a Sony PULSE Elite headset connected through a PlayStation Link USB adapter and your speakers.

The USB adapter can remain visible to PipeWire when the headset is off. This tool reads its HID connection status and selects the appropriate PipeWire output through WirePlumber. It runs as a small systemd user service, with no third-party Python dependencies.

## Tested setup

- Zorin OS 18.1 (Ubuntu 24.04 base)
- PipeWire 1.0.5 and WirePlumber 0.4.17
- PlayStation Link adapter **USB ID `054c:0ecc`**
- PULSE Elite headset and Klipsch R-41PM USB speakers

Repeated power cycles worked, including moving an already-playing Chrome stream in both directions. Other firmware versions and adapter revisions are unverified. Suspend/resume, reboot, and hot-unplug recovery are implemented but have not yet been validated on hardware.

## Behavior

- Polls HID feature report `0x82` every 0.5 seconds using a read-only device handle.
- Requires three consecutive matching readings before acting, approximately 1–1.5 seconds after the status becomes visible.
- Connected headset: select the configured headset output.
- Observed shutdown status, fully disconnected headset, or absent adapter: select the configured speakers.
- Unknown reports or read errors: leave the current output unchanged.
- Retries unavailable outputs and detects PipeWire restarts through its server cookie.
- Rediscovers the HID device rather than assuming a permanent `/dev/hidrawN` number.
- Leaves volumes and microphone routing unchanged; does not record audio.
- A manual output choice remains until the next relevant connection change or device/server recovery.

Applications explicitly pinned to another device may not follow the default output. Ordinary Chrome playback followed it on the tested setup.

## Requirements

Python 3, PipeWire tools (`pw-dump`), WirePlumber (`wpctl`), systemd user services, and a local desktop session managed by systemd-logind. The HID access rule grants access to the active local user.

## Install

Run the user installation as your normal desktop user:

```bash
bash install.sh
~/.local/bin/pulse-elite-autoswitch --list-sinks
```

Edit `~/.config/pulse-elite-autoswitch/config.json` and replace both placeholders with the complete node names from `--list-sinks`. Use the PlayStation Link **playback output** and your preferred speaker output. Configuration follows `XDG_CONFIG_HOME` when set.

Install the device access rule using administrator privileges:

```bash
sudo install -m 0644 70-pulse-elite.rules /etc/udev/rules.d/70-pulse-elite.rules
sudo udevadm control --reload-rules
```

Unplug and reconnect the PS Link adapter so the rule takes effect. This permission is separate from the systemd user service: the daemon itself must not run as root.

Optionally check state detection before enabling routing:

```bash
~/.local/bin/pulse-elite-autoswitch --dry-run
```

Stop the dry run with Ctrl+C, then enable the service:

```bash
systemctl --user enable --now pulse-elite-autoswitch
journalctl --user -u pulse-elite-autoswitch -f
```

If upgrading the earlier machine-specific version, finish editing the configuration before restarting its already-enabled service:

```bash
systemctl --user restart pulse-elite-autoswitch
```

## Manage and troubleshoot

```bash
# Current service status
systemctl --user status pulse-elite-autoswitch

# Recent diagnostics
journalctl --user -u pulse-elite-autoswitch -n 50 --no-pager

# Pause; selected output remains unchanged
systemctl --user stop pulse-elite-autoswitch

# Disable startup and stop
systemctl --user disable --now pulse-elite-autoswitch
```

- **Permission denied:** install the udev rule, replug the adapter, and confirm your local desktop session is active.
- **Output unavailable:** rerun `--list-sinks` and check the configured node names and active audio profiles.
- **Unknown state:** the tool deliberately avoids guessing. See [PROTOCOL.md](PROTOCOL.md) for the measured report format.
- **Another instance running:** stop the service before starting a manual dry run.
- **Multiple adapters:** the tool currently refuses to choose between multiple `054c:0ecc` adapters.

To remove it, disable the service, then remove `~/.local/bin/pulse-elite-autoswitch`, `~/.config/systemd/user/pulse-elite-autoswitch.service`, and optionally its configuration directory. Run `systemctl --user daemon-reload`. To remove device permissions too, remove `/etc/udev/rules.d/70-pulse-elite.rules` with administrator privileges, reload udev rules, and replug the adapter. Adjust user configuration paths if using `XDG_CONFIG_HOME`.

## Development

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
systemd-analyze --user verify pulse-elite-autoswitch.service
udevadm verify 70-pulse-elite.rules
```

The project contains no raw captures, personal sink configuration, or adapter serial numbers. The running machine-specific installation is independent of this source checkout until explicitly updated.

## Research reference

[Jprnp/pslink-libusb](https://github.com/Jprnp/pslink-libusb) provided the lead that this adapter exposes useful HID feature reports. This implementation was written separately and the `0x82` signatures were tested directly on Linux. It does not use that project's Windows driver replacement or firmware-setting commands.
