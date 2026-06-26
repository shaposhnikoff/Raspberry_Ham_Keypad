from __future__ import annotations

import argparse
import logging
import sys

from radio_key_daemon.actions import ActionRunner
from radio_key_daemon.bindings_visualizer import render_bindings
from radio_key_daemon.config import ConfigError, ConfigState, load_config
from radio_key_daemon.daemon import RadioKeyDaemon
from radio_key_daemon.devices import (
    DeviceSelectionError,
    list_input_devices,
    open_selected_device,
)
from radio_key_daemon.keys import normalize_key_code
from radio_key_daemon.logging_setup import setup_logging
from radio_key_daemon.web import run_web_server, start_web_server

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
    parser.add_argument(
        "--show-bindings",
        action="store_true",
        help="Print configured key bindings and exit",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start the web interface alongside the keypad daemon",
    )
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Start only the web interface without reading an input device",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for --web (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        default=8765,
        type=int,
        help="Port for --web (default: 8765)",
    )
    parser.add_argument(
        "--allow-service-restart",
        action="store_true",
        help="Allow the web interface to restart the systemd service",
    )
    parser.add_argument(
        "--allow-command-run",
        action="store_true",
        help="Allow the web interface to run configured commands",
    )
    parser.add_argument(
        "--service-name",
        default="radio-key-daemon.service",
        help="Systemd service name for --allow-service-restart",
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
    if args.show_bindings:
        if not args.config:
            print("--show-bindings requires --config", file=sys.stderr)
            return 2
        try:
            print(render_bindings(load_config(args.config)))
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.web and args.web_only:
        print("--web and --web-only cannot be used together", file=sys.stderr)
        return 2
    if args.web and not args.config:
        print("--web requires --config", file=sys.stderr)
        return 2
    if args.web_only:
        if not args.config:
            print("--web-only requires --config", file=sys.stderr)
            return 2
        try:
            config = load_config(args.config)
            setup_logging(config.logging.level)
            run_web_server(
                config,
                config_path=args.config,
                host=args.host,
                port=args.port,
                allow_service_restart=args.allow_service_restart,
                service_name=args.service_name,
                allow_command_run=args.allow_command_run,
            )
        except (ConfigError, OSError) as exc:
            logger.error("%s", exc)
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if not args.config:
        print(
            "--config is required unless using --list-devices, --scan-keys, "
            "--show-bindings, or --web-only",
            file=sys.stderr,
        )
        return 2
    web_handle = None
    try:
        config = load_config(args.config)
        setup_logging(config.logging.level)
        config_state = ConfigState(config)
        runner = ActionRunner(config.behavior, dry_run=args.dry_run)
        if args.web:
            web_handle = start_web_server(
                config,
                config_path=args.config,
                config_state=config_state,
                host=args.host,
                port=args.port,
                allow_service_restart=args.allow_service_restart,
                service_name=args.service_name,
                allow_command_run=args.allow_command_run,
                command_runner=runner.run,
            )
        device = open_selected_device(config.device)
        daemon = RadioKeyDaemon(config_state, device, runner)
        daemon.install_signal_handlers()
        try:
            daemon.run()
        finally:
            if web_handle is not None:
                web_handle.shutdown()
                web_handle = None
    except (
        ConfigError,
        DeviceSelectionError,
        PermissionError,
        OSError,
        RuntimeError,
    ) as exc:
        if web_handle is not None:
            web_handle.shutdown()
        logger.error("%s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _list_devices() -> int:
    try:
        devices = list_input_devices()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for device in devices:
        keyboard_flag = "yes" if device.is_keyboard_like else "no"
        print(f"path: {device.path}")
        print(f"  name: {device.name}")
        print(f"  phys: {device.phys}")
        print(f"  uniq: {device.uniq}")
        print(f"  capabilities: {device.capabilities_summary}")
        print(f"  keyboard-like: {keyboard_flag}")
    return 0


def _scan_keys(device_path: str) -> int:
    try:
        from evdev import InputDevice, categorize, ecodes
    except ImportError:
        print("error: evdev is required to scan keys", file=sys.stderr)
        return 1

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
