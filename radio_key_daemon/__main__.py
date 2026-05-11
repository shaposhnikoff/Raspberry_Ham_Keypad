from __future__ import annotations

import argparse
import logging
import sys

from evdev import InputDevice, categorize, ecodes

from radio_key_daemon.actions import ActionRunner
from radio_key_daemon.config import ConfigError, load_config
from radio_key_daemon.daemon import RadioKeyDaemon
from radio_key_daemon.devices import (
    DeviceSelectionError,
    list_input_devices,
    open_selected_device,
)
from radio_key_daemon.keys import normalize_key_code
from radio_key_daemon.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Radio keyboard command daemon")
    parser.add_argument("--config", help="Path to YAML config")
    parser.add_argument(
        "--list-devices", action="store_true", help="List input devices"
    )
    parser.add_argument(
        "--scan-keys", action="store_true", help="Print pressed key codes"
    )
    parser.add_argument("--device", help="Device path for --scan-keys")
    parser.add_argument(
        "--dry-run", action="store_true", help="Log commands without running"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_devices:
        return _list_devices()
    if args.scan_keys:
        if not args.device:
            print("--scan-keys requires --device /dev/input/eventX", file=sys.stderr)
            return 2
        return _scan_keys(args.device)
    if not args.config:
        print(
            "--config is required unless using --list-devices or --scan-keys",
            file=sys.stderr,
        )
        return 2
    try:
        config = load_config(args.config)
        setup_logging(config.logging.level)
        device = open_selected_device(config.device)
        runner = ActionRunner(config.behavior, dry_run=args.dry_run)
        daemon = RadioKeyDaemon(config, device, runner)
        daemon.install_signal_handlers()
        daemon.run()
    except (ConfigError, DeviceSelectionError, PermissionError, OSError) as exc:
        logger.error("%s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _list_devices() -> int:
    for device in list_input_devices():
        keyboard_flag = "yes" if device.is_keyboard_like else "no"
        print(f"path: {device.path}")
        print(f"  name: {device.name}")
        print(f"  phys: {device.phys}")
        print(f"  uniq: {device.uniq}")
        print(f"  capabilities: {device.capabilities_summary}")
        print(f"  keyboard-like: {keyboard_flag}")
    return 0


def _scan_keys(device_path: str) -> int:
    device = InputDevice(device_path)
    print(
        f"Scanning key presses from {device.path} ({device.name}). "
        "Press Ctrl+C to stop."
    )
    try:
        for event in device.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            key_event = categorize(event)
            if key_event.keystate == 1:
                print(normalize_key_code(key_event.keycode), flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        device.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
