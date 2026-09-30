# v0.1 release validation

## Automated / local checks

- Core and CLI tests: report interpretation, debounce, unknown-state handling, adapter absence, permission failures, descriptor replacement, missing fallback recovery, server-cookie changes, profile changes, atomic configuration, CLI errors, login preference, and migration backups.
- GTK tests: device population, separate adapter status, shared save backend, and preservation of pending UI edits.
- CLI smoke test without DISPLAY/WAYLAND_DISPLAY, using a separate configuration and dry-run lock.
- GTK window rendered offscreen against the local display server and inspected visually.
- Build both `.deb` packages; inspect metadata, file layout, permissions, dependencies and hashes.
- Extract core package and run CLI from its payload without the optional GUI module.

Tests using simulated hardware state verify policy, not the physical timing or firmware behavior of an unplug event.

## Hardware acceptance before merging/releasing

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

Physical acceptance tests remain pending for this first candidate. Keep the existing installation available until the user completes the transition.
