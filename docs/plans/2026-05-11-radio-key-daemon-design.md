# Radio Key Daemon Design

## Goal

Build a production-ready Python userspace daemon for Linux and Raspberry Pi that reads a selected HID keyboard device through evdev and runs configured commands for selected key events.

## Recommended Approach

Use a small layered package:

- `config.py` loads YAML into dataclasses and validates behavior, device selection, and command mappings.
- `devices.py` lists and selects `evdev.InputDevice` instances by path, name, or physical path.
- `daemon.py` owns the event loop, debounce state, exclusive grab lifecycle, and graceful shutdown.
- `actions.py` runs configured commands synchronously or asynchronously and logs stdout/stderr.
- `keys.py` handles evdev key name normalization and event matching.
- `__main__.py` exposes the CLI modes requested in `AGENT.md`.

This keeps hardware access isolated from command execution and makes the core behavior testable without a real keyboard.

## Alternatives Considered

1. Single-file daemon. Simpler to copy, but harder to test and maintain.
2. Asyncio-based event loop. Useful later, but unnecessary while `evdev.InputDevice.read_loop()` and subprocess handling are enough.
3. Dataclasses plus manual validation. This is the selected approach because it avoids adding pydantic and matches the repository instructions.

## Data Flow

1. CLI loads config or handles utility modes.
2. Device selector opens a matching input device.
3. Daemon optionally grabs the device.
4. Daemon reads `EV_KEY` events, filters by configured trigger mode and repeat policy, then applies per-key debounce.
5. Matching keys dispatch to `ActionRunner`.
6. Shutdown handlers stop the loop and release exclusive grab.

## Error Handling

Configuration errors raise explicit exceptions with actionable messages. Device selection errors include matching candidates when selection is ambiguous. Command failures are logged but do not crash the daemon. Exclusive grab permission failures explain root, input group, and udev rule options.

## Testing

Unit tests cover YAML loading, command mapping validation, debounce behavior, and command argument construction for shell and non-shell modes. Hardware-facing behavior remains modular so it can be tested later with fake devices or integration tests on Raspberry Pi.
