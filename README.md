# Radio Key Daemon

Userspace keyboard daemon for Linux and Raspberry Pi. It reads a selected USB keyboard, numpad, macro pad, or other HID keyboard device through `evdev` and runs configured commands when selected keys are pressed.

No kernel driver is required. Linux already exposes USB keyboards as `/dev/input/eventX`; this daemon reads those events from userspace.


<img width="432" height="392" alt="image" src="https://github.com/user-attachments/assets/4d520fd7-2b48-43cd-b031-c1b809d41309" />

## Features

- Select keyboard by `/dev/input/eventX`, device name substring, or physical path substring.
- Optional exclusive grab so the selected keyboard does not type into the system.
- YAML key-to-command mapping using evdev key names like `KEY_F12`, `KEY_KPENTER`, and `KEY_ESC`.
- Sync command execution by default to avoid overlapping radio control procedures.
- Optional async command execution per command or globally.
- Per-key debounce and repeat filtering.
- Dry-run mode for testing.
- Local web interface for inspecting devices and editing key bindings.
- Systemd service example for Raspberry Pi.

## Install

On Raspberry Pi 4, install the `build-essential` meta package first:

```bash
sudo apt update
sudo apt install -y build-essential
```

Install `uv` first if it is not already available, then install the project dependencies:

```bash
uv sync
```

For a plain requirements-based install:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Find The Keyboard

List input devices:

```bash
uv run python -m radio_key_daemon --list-devices
```

The output includes path, name, physical path, unique ID, a capabilities summary, and whether the device looks keyboard-like.

## Scan Keys

After choosing a device path, scan key names:

```bash
uv run python -m radio_key_daemon --scan-keys --device /dev/input/eventX
```

Press keys on the selected keyboard. The daemon prints values suitable for YAML, for example:

```text
KEY_F12
KEY_KPENTER
KEY_A
KEY_ESC
```

## Configure

Copy the example config:

```bash
cp config.example.yaml config.yaml
```

Choose the device in one of these ways:

```yaml
device:
  path: /dev/input/event4
  name_contains: null
  phys_contains: null
```

or:

```yaml
device:
  path: null
  name_contains: "USB Keyboard"
  phys_contains: null
```

Map keys to commands:

```yaml
commands:
  KEY_F12:
    name: "Safe Tune"
    command: "/home/pi/radio/safe_tune.py"
    shell: false
```

For commands with arguments and `shell: false`, prefer argv arrays:

```yaml
commands:
  KEY_F12:
    name: "Safe Tune"
    command: ["/home/pi/radio/safe_tune.py", "--fast"]
    shell: false
```

Use `shell: true` only for trusted configs. It executes the command string through the shell:

```yaml
commands:
  KEY_F11:
    name: "Lower RF Power"
    command: "rigctl -m 1042 -r /dev/ttyUSB0 -s 38400 set_level RFPOWER 0.20"
    shell: true
```

Per-command overrides are supported:

```yaml
commands:
  KEY_F12:
    command: "/home/pi/radio/safe_tune.py"
    shell: false
    timeout: 10
    run_async: false
    debounce_ms: 1000
```

## Run

Manual run:

```bash
uv run python -m radio_key_daemon --config ./config.yaml
```

Dry run:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --dry-run
```

Dry-run mode logs what would execute and does not start commands.

Show the current key bindings without opening the input device:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --show-bindings
```

This parses the same YAML config as the daemon and prints an ASCII keyboard
layout plus a command summary table.

Start the web interface alongside the keypad daemon:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --web
```

Open `http://127.0.0.1:8765/` on the same machine. In this mode the HTTP server
runs in a background thread while the main thread keeps reading the selected
`evdev` input device. Key presses from the physical keypad continue to execute
commands.

The web interface shows the parsed config, command bindings, and available
input devices. It can edit only the `commands` key bindings section of the YAML
file. Device, behavior, and logging settings stay read-only in the web UI.

Before saving changes, the server validates the new bindings with the same
config parser used by the daemon. On a successful save it writes a rolling
backup next to the config file, for example `config.yaml.bak`, then replaces
the YAML file atomically and reloads the shared in-memory config used by the
keypad loop. Existing YAML comments may not be preserved.

The web page includes an Activity Log below the key bindings table. It shows
recent web-session events such as binding saves, run requests, command
stdout/stderr, exit codes, validation errors, and service restart results. The
log is an in-memory ring buffer for the current web process; it is not a
replacement for `journalctl`.

By default the server binds only to `127.0.0.1`. To expose it on a LAN, choose
the address explicitly and treat the page as operational station tooling:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --web --host 0.0.0.0 --port 8765
```

By default the web UI will not restart services. To show the restart button and
allow `systemctl restart radio-key-daemon.service`, start it explicitly:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --web --allow-service-restart
```

Use `--service-name` if your systemd unit has a different name.

By default the web UI will not run configured commands. To enable the per-key
`Run` buttons, start it explicitly:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --web --allow-command-run
```

The run API accepts only configured key names, such as `KEY_KP1`, and executes
the saved YAML command for that key. It does not accept arbitrary shell command
text from the browser. If you bind the web server to `0.0.0.0`, treat this as
remote operational control of the station.

For config-only maintenance without opening an input device, use `--web-only`:

```bash
uv run python -m radio_key_daemon --config ./config.yaml --web-only
```

## Exclusive Grab

`exclusive_grab` prevents the selected keyboard from sending key presses to the rest of the system:

```yaml
behavior:
  exclusive_grab: true
```

Keep it `false` while testing with your main full-size keyboard. For a dedicated external keypad or macro pad, set it to `true` after you confirm the selected device is correct.

## Permissions

Temporary option:

```bash
sudo uv run python -m radio_key_daemon --config ./config.yaml
```

Better option on Raspberry Pi:

```bash
sudo usermod -aG input pi
```

Log out and back in after changing group membership.

Optional udev rule example:

```udev
KERNEL=="event*", SUBSYSTEM=="input", GROUP="input", MODE="660"
```

Place custom rules under `/etc/udev/rules.d/`, then reload udev rules.

## Systemd

Copy the web control service file:

```bash
sudo cp systemd/radio-key-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable radio-key-daemon
sudo systemctl start radio-key-daemon
```

The included service starts the web UI on `0.0.0.0:8765` with configured command
run buttons enabled:

```text
--web --host 0.0.0.0 --port 8765 --allow-command-run
```

Open `http://RASPBERRY_PI_ADDRESS:8765/` from your LAN. This service runs the
web UI and the evdev keypad event loop in the same process. The HTTP server runs
in a background thread; the main thread remains the keypad reader.

Optional: run Hamlib `rigctld` as a service too:

```bash
sudo cp systemd/rigctld.service /etc/systemd/system/
```

Prefer a drop-in override for local `User=` changes (for example `/etc/systemd/system/rigctld.service.d/override.conf`) and optionally set rig values in `/etc/default/rigctld` (`RIGCTLD_MODEL`, `RIGCTLD_DEVICE`, `RIGCTLD_BAUD`, `RIGCTLD_BIND`, `RIGCTLD_PORT`) before starting it.

```bash
sudo systemctl daemon-reload
sudo systemctl enable rigctld
sudo systemctl start rigctld
```

Check logs:

```bash
journalctl -u radio-key-daemon -f
journalctl -u rigctld -f
```

If using `uv` in production instead of system Python, adjust `ExecStart` to the venv or `uv run` command you actually deploy.

## Safe Tune Placeholder

Example external script target:

```python
#!/usr/bin/env python3
print("Safe tune placeholder")
```

Make it executable:

```bash
chmod +x /home/pi/radio/safe_tune.py
```

Then map `KEY_F12` to that script in `config.yaml`.
