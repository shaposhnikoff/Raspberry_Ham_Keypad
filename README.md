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
- Systemd service example for Raspberry Pi.

## Install

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

Copy the keypad service file:

```bash
sudo cp systemd/radio-key-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable radio-key-daemon
sudo systemctl start radio-key-daemon
```

Optional: run Hamlib `rigctld` as a service too:

```bash
sudo cp systemd/rigctld.service /etc/systemd/system/
```

Edit `/etc/systemd/system/rigctld.service` to match your rig model, serial port, and baud rate before starting it.

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
