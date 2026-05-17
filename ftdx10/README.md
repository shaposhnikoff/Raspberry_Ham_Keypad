# FTDX10 CAT Helper

`ftdx10_cat.py` is a small command-line helper for controlling a Yaesu FTDX10
through its CAT serial interface from Linux or Raspberry Pi.

It has no `pyserial` dependency. The script opens the serial device directly
with Linux `termios`, sends ASCII CAT commands, and optionally reads the CAT
answer back until the first semicolon.

Default connection settings:

- CAT port: `/dev/ttyUSB0`
- CAT baud rate: `38400`
- CAT read timeout: `0.6` seconds
- Supported baud rates: `4800`, `9600`, `19200`, `38400`

For the FTDX10 USB connection, use the radio CAT port. On many Linux systems
this is the Enhanced COM Port exposed as `/dev/ttyUSB0` or `/dev/ttyUSB1`.

## Files

- `ftdx10_cat.py` - standalone CAT helper.
- `ftdx10_keypad_full_config.yaml` - example `radio_key_daemon` keypad mapping
  that calls `ftdx10_cat.py`.

## Install On Raspberry Pi

Copy the helper to a stable local path:

```bash
sudo mkdir -p /home/pi/radio
sudo cp ftdx10/ftdx10_cat.py /home/pi/radio/
sudo chmod +x /home/pi/radio/ftdx10_cat.py
```

If you use another user or directory, update all paths in the keypad YAML.

The script uses only the Python standard library, so no extra Python package is
needed for direct CAT usage.

## Serial Port Permissions

Temporary test option:

```bash
sudo /home/pi/radio/ftdx10_cat.py status
```

Better long-term option:

```bash
sudo usermod -aG dialout pi
```

Log out and back in after changing group membership. On some distributions the
serial group may be `uucp` instead of `dialout`.

To find the CAT device:

```bash
ls -l /dev/ttyUSB*
dmesg | grep ttyUSB
```

## Basic Usage

Run from the repository:

```bash
uv run python ftdx10/ftdx10_cat.py status
```

Run after copying to `/home/pi/radio`:

```bash
/home/pi/radio/ftdx10_cat.py status
```

Use a different serial port:

```bash
/home/pi/radio/ftdx10_cat.py --port /dev/ttyUSB1 status
```

Use environment variables, which is convenient from YAML command mappings:

```bash
CAT_PORT=/dev/ttyUSB0 CAT_BAUD=38400 /home/pi/radio/ftdx10_cat.py status
```

CLI shape:

```text
ftdx10_cat.py [--port PORT] [--baud BAUD] [--timeout TIMEOUT] COMMAND ...
```

Global options:

| Option | Environment | Default | Description |
| --- | --- | --- | --- |
| `--port` | `CAT_PORT` | `/dev/ttyUSB0` | Linux serial device for FTDX10 CAT. |
| `--baud` | `CAT_BAUD` | `38400` | Serial baud rate. |
| `--timeout` | `CAT_TIMEOUT` | `0.6` | Read timeout for commands that expect a response. |

## Command Reference

| Command | Arguments | CAT command sent | Example |
| --- | --- | --- | --- |
| `band` | band key | `BSxx;` | `ftdx10_cat.py band 14` |
| `freq` | `up` or `down`, optional count | `UP;` or `DN;` repeated | `ftdx10_cat.py freq up 5` |
| `vol` | `up` or `down`, optional step | reads `AG0;`, writes `AG0nnn;` | `ftdx10_cat.py vol down 8` |
| `power` | watts | `PCnnn;` | `ftdx10_cat.py power 10` |
| `tuner` | `off`, `on`, or `tune` | `AC000;`, `AC001;`, `AC002;` | `ftdx10_cat.py tuner tune` |
| `nb` | `on` or `off` | `NB01;` or `NB00;` | `ftdx10_cat.py nb on` |
| `clar` | `clear`, `up`, or `down` | `RC;`, `RU;`, `RD;` | `ftdx10_cat.py clar clear` |
| `raw` | CAT command, optional `--read` | given command | `ftdx10_cat.py raw 'FA;' --read` |
| `status` | none | queries `FA;`, `AG0;`, `PC;`, `IF;` | `ftdx10_cat.py status` |

All commands are terminated with `;` automatically if you omit it.

## Band Mapping

`band` accepts common MHz and meter-band aliases.

| Input keys | CAT command |
| --- | --- |
| `1.8`, `160` | `BS00;` |
| `3.5`, `80` | `BS01;` |
| `5`, `60` | `BS02;` |
| `7`, `40` | `BS03;` |
| `10`, `30` | `BS04;` |
| `14`, `20` | `BS05;` |
| `18`, `17` | `BS06;` |
| `21`, `15` | `BS07;` |
| `24.5`, `12` | `BS08;` |
| `28`, `10m` | `BS09;` |
| `50`, `6` | `BS10;` |
| `gen` | `BS11;` |
| `mw` | `BS12;` |

Example:

```bash
CAT_PORT=/dev/ttyUSB0 CAT_BAUD=38400 /home/pi/radio/ftdx10_cat.py band 14
```

Expected output:

```text
band=14 cat=BS05;
```

## Frequency Step Commands

Move frequency using the radio CAT `UP;` and `DN;` commands:

```bash
/home/pi/radio/ftdx10_cat.py freq up
/home/pi/radio/ftdx10_cat.py freq down
/home/pi/radio/ftdx10_cat.py freq up 5
```

The optional count repeats the CAT command. Values lower than `1` are treated as
`1`.

## AF Gain

Volume control reads the current AF gain first, then writes the adjusted value:

```bash
/home/pi/radio/ftdx10_cat.py vol up 8
/home/pi/radio/ftdx10_cat.py vol down 8
```

The value is clamped to the CAT range `0..255`. If the radio does not answer the
`AG0;` query, the command exits with a parse error.

## RF Power

Set RF power in watts:

```bash
/home/pi/radio/ftdx10_cat.py power 5
/home/pi/radio/ftdx10_cat.py power 10
/home/pi/radio/ftdx10_cat.py power 25
/home/pi/radio/ftdx10_cat.py power 100
```

The script clamps the requested value to `5..100` before sending `PCnnn;`.

## Tuner, Noise Blanker, And Clarifier

```bash
/home/pi/radio/ftdx10_cat.py tuner off
/home/pi/radio/ftdx10_cat.py tuner on
/home/pi/radio/ftdx10_cat.py tuner tune

/home/pi/radio/ftdx10_cat.py nb on
/home/pi/radio/ftdx10_cat.py nb off

/home/pi/radio/ftdx10_cat.py clar down
/home/pi/radio/ftdx10_cat.py clar clear
/home/pi/radio/ftdx10_cat.py clar up
```

Use `tuner tune` intentionally. It asks the radio tuner to start a tuning
operation.

## Raw CAT Commands

Send a CAT command without reading a response:

```bash
/home/pi/radio/ftdx10_cat.py raw 'FA;'
```

Send a CAT command and print the answer:

```bash
/home/pi/radio/ftdx10_cat.py raw 'FA;' --read
```

`raw` is useful for testing commands from the Yaesu CAT manual before adding a
new wrapper command.

## Status

Read common status fields:

```bash
/home/pi/radio/ftdx10_cat.py status
```

The helper queries:

- `FA;` - VFO-A frequency.
- `AG0;` - AF gain.
- `PC;` - RF power.
- `IF;` - operating information.

Some answers may be empty if the port, baud rate, or radio menu settings are not
ready. The script prints whatever it receives.

## Keypad Integration

The normal keypad flow uses `radio_key_daemon` to read USB keyboard events and
run shell commands from YAML. The included FTDX10 config maps keys to
`ftdx10_cat.py` commands.

Copy the example:

```bash
cp ftdx10/ftdx10_keypad_full_config.yaml config.ftdx10.yaml
```

Edit these values:

```yaml
device:
  path: null
  name_contains: "USB Keyboard"
  phys_contains: null

behavior:
  exclusive_grab: true
```

Set the correct CAT port in each command if it is not `/dev/ttyUSB0`:

```yaml
commands:
  KEY_KP6:
    name: "Band 14 MHz"
    command: "CAT_PORT=/dev/ttyUSB0 CAT_BAUD=38400 /home/pi/radio/ftdx10_cat.py band 14"
    shell: true
```

Run a dry test first:

```bash
uv run python -m radio_key_daemon --config config.ftdx10.yaml --dry-run
```

Run live:

```bash
uv run python -m radio_key_daemon --config config.ftdx10.yaml
```

## Full Keypad Layout From The Example Config

| Key | Action |
| --- | --- |
| `KEY_KP1` | Band 1.8 MHz |
| `KEY_KP2` | Band 3.5 MHz |
| `KEY_KP3` | Band 5 MHz |
| `KEY_KP4` | Band 7 MHz |
| `KEY_KP5` | Band 10 MHz |
| `KEY_KP6` | Band 14 MHz |
| `KEY_KP7` | Band 18 MHz |
| `KEY_KP8` | Band 21 MHz |
| `KEY_KP9` | Band 24.5 MHz |
| `KEY_KP0` | Band 28 MHz |
| `KEY_KPENTER` | Band 50 MHz |
| `KEY_KPPLUS` | Frequency up |
| `KEY_KPMINUS` | Frequency down |
| `KEY_PAGEUP` | Volume up |
| `KEY_PAGEDOWN` | Volume down |
| `KEY_F1` | RF power 5 W |
| `KEY_F2` | RF power 10 W |
| `KEY_F3` | RF power 25 W |
| `KEY_F4` | RF power 100 W |
| `KEY_F5` | Tuner on |
| `KEY_F6` | Tuner tune |
| `KEY_F7` | Noise blanker on |
| `KEY_F8` | Noise blanker off |
| `KEY_F9` | Clarifier down |
| `KEY_F10` | Clarifier clear |
| `KEY_F11` | Clarifier up |
| `KEY_F12` | Read status |

## Work Scheme

Keypad-controlled mode:

```mermaid
flowchart LR
    A[USB keypad key press] --> B[Linux evdev input event]
    B --> C[radio_key_daemon]
    C --> D[YAML key mapping]
    D --> E[shell command]
    E --> F[ftdx10_cat.py]
    F --> G[/dev/ttyUSB0 CAT serial port]
    G --> H[Yaesu FTDX10]
    F --> I[stdout or stderr]
    I --> C
    C --> J[daemon logs or journalctl]
```

Standalone mode:

```mermaid
flowchart LR
    A[User shell command] --> B[ftdx10_cat.py]
    B --> C[termios serial setup]
    C --> D[/dev/ttyUSB0]
    D --> E[FTDX10 CAT interface]
    E --> F[Optional CAT answer]
    F --> B
    B --> G[Printed output]
```

## Safety Notes

- Test `status` and `raw 'FA;' --read` before mapping live keys.
- Confirm that `CAT_PORT` points to the FTDX10 CAT interface, not another USB
  serial device.
- The keypad YAML uses `shell: true` so environment variables can be set inline.
  Treat the YAML as trusted configuration.
- `power` changes RF output power.
- `tuner tune` starts a tuner operation on the radio.
- Keep `radio_key_daemon` `exclusive_grab: false` while testing with your main
  keyboard. Use `true` only after the correct external keypad is selected.

## Troubleshooting

### Permission denied for `/dev/ttyUSB0`

Run once with `sudo` to confirm the device works, then add the service user to
the serial device group:

```bash
sudo usermod -aG dialout pi
```

Log out and back in before retrying.

### No response from `status`

Check:

- USB cable is connected to the radio.
- The radio is powered on.
- The selected `/dev/ttyUSB*` device is the CAT port.
- `CAT_BAUD` matches the radio CAT baud menu setting.
- No other program is holding the same CAT port.

### Wrong serial device after reboot

`/dev/ttyUSB0` numbers can change when USB devices are reconnected. Prefer a
stable `/dev/serial/by-id/...` path when available:

```bash
ls -l /dev/serial/by-id/
CAT_PORT=/dev/serial/by-id/YOUR_FTDX10_DEVICE /home/pi/radio/ftdx10_cat.py status
```

### `vol` exits with a parse error

`vol` must read a valid `AG0nnn;` answer before writing the new value. If parsing
fails, verify the CAT port, baud rate, timeout, and radio CAT settings.

### Keypad dry-run works but live mode does nothing

Check the daemon logs:

```bash
journalctl -u radio-key-daemon -f
```

Then run the exact command from the YAML manually in a shell. This separates
keypad event handling from CAT serial problems.
