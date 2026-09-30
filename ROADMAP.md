# Next milestone: installable app with device selection

## Goal

Turn the working Pulse Elite automatic output switcher into an installable Linux package. Users should be able to select which playback device is used when the Pulse Elite is disconnected, through either a desktop UI or a fully functional CLI, without editing Python code or manually editing configuration files.

Both interfaces are first-release requirements. They must share the same configuration, validation, and service-control logic; neither should depend on the other being open.

The existing private repository is the continuation point. A v0.1 candidate now implements the shared core, CLI, GTK desktop window, migration helper, and separate Debian packages on a feature branch. See TESTING.md for the hardware/package acceptance checks still required before merging or releasing.

## Proposed first release

Start with a `.deb` package for the tested Zorin/Ubuntu environment. Keep the routing engine separate from the setup interface so other Linux packaging formats can follow later.

A small setup window launched from the applications menu should:

1. Detect the supported PlayStation Link adapter and its playback output automatically.
2. List available alternative playback devices by their friendly names, including speakers, monitor audio, and other outputs exposed by PipeWire.
3. Let the user choose the fallback output from a dropdown and refresh the list after connecting a device.
4. Show the current headset state and the selected fallback output.
5. Provide Save, Enable automatic switching, and Pause controls.
6. Explain missing device access, an unavailable selected output, or an unsupported adapter in plain language.

The CLI must support the complete setup and management workflow without a graphical display:

- List available playback devices with friendly names and stable identifiers.
- Configure the Pulse Elite and fallback outputs through an interactive terminal picker or explicit command arguments.
- Show and update configuration, inspect headset/service status, and enable, disable, pause, or resume switching.
- Control start-at-login separately from whether switching is running now.
- Provide dry-run diagnostics, useful help, documented exit codes, and machine-readable JSON output for scripts.
- Support noninteractive operation without surprise prompts; the exact command syntax will be defined during implementation.

CLI operation still requires a reachable user audio session and suitable HID permissions. Supporting a terminal without a desktop window does not imply a root system daemon or automatic access from arbitrary SSH sessions.

Save stable device identities in a per-user configuration file, never transient PipeWire object IDs. Reuse the existing `headset_sink` and `speakers_sink` configuration keys initially for compatibility. If friendly names collide, show enough device information to distinguish the choices. Handle changes to audio profiles and node names without silently selecting a different physical device.

## USB adapter unplug and reconnect behavior

Adapter presence and headset wireless connection are separate states, both required for the first release:

- If the USB adapter is unplugged, select the user's configured fallback output after confirming absence, even if the headset was still on.
- If the adapter is absent at startup, use the fallback output and keep watching for its return.
- Close stale HID handles and rediscover the adapter on reconnect; never rely on its previous hidraw number or PipeWire object ID.
- On reconnect, wait for readable headset status and an available playback output. Switch to the Pulse Elite only after confirming the headset is connected; otherwise remain on the fallback output.
- Handle USB resets and suspend/resume without rapid output changes or a permanently stuck detector.
- Distinguish confirmed adapter absence from permission errors, failed reads, and unknown reports. An unreadable adapter must not automatically be treated as unplugged.
- If the chosen fallback device is also absent, avoid repeatedly selecting a missing output or arbitrarily choosing another device. Show the condition in the UI/CLI, allow normal audio-server fallback behavior, and retry the configured output when it returns.
- Report “Adapter disconnected” separately from “Headset off/disconnected” and “Cannot read adapter” in both interfaces.

The current daemon already includes an `adapter-absent` path and device rediscovery. A physical unplug/replug cycle during playback has now passed on the test PC; additional reconnect scenarios remain in the acceptance checklist.

## Implementation sequence

### 1. Separate detection, routing, and configuration

- Extract reusable detection and routing code from the current polling loop.
- Keep measured report signatures, three-reading confirmation, and unknown-state behavior.
- Validate both configured outputs and reject choosing the headset as its own fallback.
- Provide shared APIs for device discovery, configuration validation and atomic persistence, routing, status, and service control.
- Keep CLI commands independent of GUI imports and display-server availability.
- Preserve a command-line dry-run mode and diagnostics.
- Add tests for state sequences, read failures, device replacement, and routing recovery.

### 2. Add the CLI and desktop setup window

- Implement the full CLI setup and management workflow first using the shared APIs.
- Build the desktop window on the same APIs, with equivalent configuration and service controls.
- Ensure changes made in either interface are reflected in the other and applied consistently to the daemon.
- Enumerate PipeWire playback outputs and display friendly names.
- Detect the Pulse Elite output and allow choosing the alternative device.
- Save configuration atomically and apply changes to the user service.
- Expose service enable/pause state and useful error messages.
- Keep device selection per user, including on shared computers.

Choose the GUI toolkit during implementation based on the target desktop and packaging dependencies. A tray icon is optional follow-up work, not a first-release dependency.

### 3. Build the package

- Include the daemon, CLI, setup application, desktop launcher, user service, and device-specific udev rule.
- Prefer a core package containing the daemon and CLI, with a desktop UI package depending on the core, so terminal-only users do not need graphical dependencies.
- Declare runtime dependencies and provide a repeatable build command.
- Let the package manager handle system-level installation permissions; keep audio routing in the logged-in user's session.
- Install the user unit in the appropriate system user-unit directory. Do not assume an interactive desktop user's HOME in package installation scripts.
- Do not enable routing before initial device selection is complete.
- Handle upgrades from the existing manual installation so two daemon instances cannot run at once.
- Preserve user configuration during upgrades and ordinary removal; document how to remove it explicitly.
- Publish a versioned package and checksum through a GitHub release once validation passes.

### 4. Validate before release

- Fresh installation, first-run selection, pause/resume, upgrade, removal, and reinstall.
- Complete initial configuration and ongoing management independently through the GUI and CLI.
- CLI operation with display environment variables unset, plus noninteractive JSON output and exit codes.
- Cross-interface consistency: CLI changes appear in the UI, UI changes appear in CLI output, and concurrent saves do not corrupt configuration.
- Headset power-on and power-off with playback already running.
- Login, reboot, suspend/resume, and PipeWire restart.
- Unplug the adapter during active headset playback: existing playback moves to the configured fallback output.
- Start with the adapter absent, then reconnect it with the headset on and with it off; routing follows the confirmed state without restarting the app.
- Replug into a different USB port, repeat quick unplug/replug cycles, and confirm device rediscovery when HID/PipeWire IDs change.
- Unplug the adapter while the fallback device is also absent, then reconnect devices in either order; recover without selecting an arbitrary output.
- Fallback device absent at login, disconnected during use, and later reconnected.
- Unknown HID reports, transient read failures, and active-session permissions.
- Charging and wireless-link loss; do not assume these match intentional power-off.
- Applications that follow the default output versus applications pinned to a particular output.
- Multiple matching adapters: show a clear unsupported-state message until explicit selection is implemented.

## Acceptance criteria

A user on the supported system can install the package, select their alternative playback device, and enable switching entirely through either the desktop UI or the CLI. The UI workflow requires no terminal commands after installation; the CLI workflow requires no graphical display or manual configuration-file editing. Both interfaces operate on the same saved configuration and service. Existing playback follows confirmed headset connection changes and confirmed USB adapter removal. Reconnecting the adapter recovers automatically without restarting the app. The app starts when the user chooses, preserves volume and microphone settings, and provides a clear way to pause or disable it.

Hardware support must remain scoped to the validated adapter ID `054c:0ecc` until additional revisions are tested. Document unverified firmware behavior rather than treating the observed protocol as universal.

## Current evidence and continuation notes

- The v0.1 feature branch includes a shared Python core, CLI, GTK desktop UI, migration helper, user service, udev rule, separate Debian packages, and expanded automated tests.
- Repeated headset cycles and live Chrome playback switching were verified on Zorin OS 18.1, PipeWire 1.0.5, and WirePlumber 0.4.17.
- `PROTOCOL.md` records the observed status signatures and remaining uncertainty.
- Fresh v0.1 package installation, reboot/start-at-login recovery, and physical adapter unplug/replug during playback are confirmed on the test PC. Suspend/resume, upgrades, package removal, and additional reconnect scenarios remain pending.
- The original machine-specific installation was removed, and the v0.1 packages are now installed and running on the test PC.
- Before changing an existing installation, inspect its active user unit, executable, configuration, and udev rule. Do not assume the administrator-only rule installation has been completed.

Suggested continuation request: "Continue the installable package milestone in ROADMAP.md, beginning with the shared configuration/control layer, complete CLI, desktop device-selection UI, and Debian packaging for Zorin/Ubuntu."
