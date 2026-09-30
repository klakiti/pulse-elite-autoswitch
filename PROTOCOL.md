# Observed connection status

These are experimental observations from a PULSE Elite with a `054c:0ecc` PlayStation Link adapter, not a vendor protocol specification.

The capture found no corresponding PipeWire, ALSA-control, or udev events during a headset power cycle while the dongle remained plugged in. The adapter exposes a HID control interface through Linux `hidraw`.

The implementation requests feature report `0x82` with a 64-byte buffer using `HIDIOCGFEATURE(64)`. The tested device returns **34 bytes including the report ID**.

| Bytes | Observed interpretation | Routing decision |
|---|---|---|
| `82`, followed by 33 zero bytes | Fully disconnected | Speakers |
| `82 01 10 …` | Connected | Headset |
| `82 01 20 …` | Shutdown/disconnection transition | Speakers |
| Other signature or length | Unrecognized | Keep current output |

Classification uses only bytes 1 and 2 for the two nonzero signatures. The remaining bytes are not assumed constant; their full meaning has not been established here.

Across repeated cycles, the intermediate signature preceded the fully-zero report. Three measured intermediate periods lasted approximately 70, 21, and 20 seconds. Physical power-button presses were not timestamped. A follow-up test kept the headset connected for approximately 95 seconds; its report stayed `82 01 10 …`, changed to `82 01 20 …` around the requested shutdown, and became zero approximately 20 seconds later. A subsequent live audio test worked in both directions, as confirmed by the user and PipeWire routing snapshots.

This supports using the intermediate signature to avoid waiting for the adapter's full disconnected state. It does not prove identical behavior on every firmware revision, with another paired device, while charging, or under radio-link loss.

Feature report `0xB0` was also explored: reads failed with `EPIPE` when fully off and succeeded while connected, but could continue succeeding during shutdown. The final detector only polls `0x82`.

No HID settings reports are written, no audio interfaces are detached, and no raw captures are included in this repository.
