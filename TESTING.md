# v0.1 release validation

## Automated / local checks

- Core and CLI tests: report interpretation, debounce, unknown-state handling, adapter absence, permission failures, descriptor replacement, missing fallback recovery, server-cookie changes, profile changes, atomic configuration, CLI errors, login preference, and migration backups.
- GTK tests: device population, separate adapter status, shared save backend, and preservation of pending UI edits.
- CLI smoke test without DISPLAY/WAYLAND_DISPLAY, using a separate configuration and dry-run lock.
- GTK window rendered offscreen against the local display server and inspected visually.
- Build both `.deb` packages; inspect metadata, file layout, permissions, dependencies and hashes.
- Extract core package and run CLI from its payload without the optional GUI module.

Tests using simulated hardware state verify policy, not the physical timing or firmware behavior of an unplug event.

## Confirmed on hardware (2026-09-30)

- Both v0.1.0 Debian packages installed successfully on Zorin OS 18.1 after the original manual switcher was removed.
- Saved headset/fallback configuration and the start-at-login preference survived a computer reboot, as reported by the user and verified afterward.
- The packaged systemd user service started automatically in the new boot and was active, using the packaged unit rather than the old manual unit.
- Device permissions were temporarily unavailable early in login; the daemon recovered automatically, selected the configured speakers, and then selected the Pulse Elite after the headset connected.
- Post-reboot status showed a connected headset with no current device or daemon errors.
- Physical USB adapter unplug/replug during playback succeeded, as confirmed by the user. The service logs show adapter absence followed by speaker selection roughly one second later, then automatic headset selection roughly one second after reconnection was confirmed. No service restart was needed.

This confirms fresh package installation and reboot/startup recovery on the tested PC. It also confirms the tested physical adapter unplug/replug cycle. It does not establish suspend/resume, package upgrade/removal, every reconnect scenario, or migration-helper acceptance.

## Hardware acceptance checklist before merging/releasing

1. Install core and desktop packages with apt; confirm first install does not enable routing.
2. On the development PC, migrate the old manual setup; verify backups and no duplicate daemon.
3. Use the GUI to choose outputs and start switching; change configuration through the CLI and confirm GUI/service agreement.
4. Play audio and cycle headset power twice; verify playback moves both ways without volume/microphone changes.
5. Unplug the adapter while the headset is on; verify playback moves to fallback. Replug with headset on and off, including another USB port.
6. Start with the adapter absent, then reconnect; verify recovery without restarting the app.
7. Disconnect the selected fallback too, reconnect devices in either order, and verify missing-device diagnostics/recovery.
8. Test login, reboot, suspend/resume, and a user-requested PipeWire restart.
9. Test core-only installation without graphical dependencies; verify all setup and control tasks through the CLI.
10. Test upgrades and removal. Confirm configuration survives, routing stops on removal, and the application disappears from the desktop menu.

Package installation, reboot/startup recovery, and a physical unplug/replug cycle during playback are confirmed above. Other checklist items remain pending unless explicitly confirmed; the original manual installation was removed before the fresh package installation.

## Version 1.0.0 release review

The user confirmed successful one-command installation and operation of the desktop and CLI packages, package upgrades, removal, reinstall, concise CLI controls, and contextual help during the 0.1/0.2 preview series. Version 1 retains those behaviors and adds regression coverage for closing during pending UI writes, invalid incomplete CLI input, and preserving an installed desktop package during a CLI upgrade.

The historical checklist above is broader than the v1 release gate. Suspend/resume, additional reconnect combinations, other distributions/firmware, and a physical migration from the old handwritten installation remain unverified. Unit tests and mocked installer tests do not substitute for those hardware checks.
