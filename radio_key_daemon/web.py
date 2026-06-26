from __future__ import annotations

import html
import json
import logging
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml

from radio_key_daemon import __version__
from radio_key_daemon.actions import ActionRunner
from radio_key_daemon.bindings_visualizer import render_bindings
from radio_key_daemon.config import (
    AppConfig,
    CommandConfig,
    ConfigError,
    load_config,
    parse_config,
)
from radio_key_daemon.devices import DeviceInfo, list_input_devices

logger = logging.getLogger(__name__)

DeviceLister = Callable[[], list[DeviceInfo]]
ServiceRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
CommandRunner = Callable[[CommandConfig], int | None]


class ActivityLogBuffer:
    def __init__(self, max_entries: int = 200) -> None:
        self._entries: deque[dict[str, object]] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._next_id = 1

    def append(
        self,
        level: str,
        message: str,
        *,
        logger_name: str = "radio_key_daemon.web",
        created: float | None = None,
    ) -> None:
        if created is None:
            timestamp = datetime.now(UTC)
        else:
            timestamp = datetime.fromtimestamp(created, UTC)
        with self._lock:
            self._entries.append(
                {
                    "id": self._next_id,
                    "timestamp": timestamp.isoformat(timespec="seconds"),
                    "level": level.upper(),
                    "logger": logger_name,
                    "message": message,
                }
            )
            self._next_id += 1

    def entries(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class ActivityLogHandler(logging.Handler):
    def __init__(self, buffer: ActivityLogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(
                record.levelname,
                record.getMessage(),
                logger_name=record.name,
                created=record.created,
            )
        except Exception:
            self.handleError(record)


class WebApp:
    def __init__(
        self,
        config: AppConfig,
        *,
        config_path: str,
        device_lister: DeviceLister = list_input_devices,
        allow_service_restart: bool = False,
        service_name: str = "radio-key-daemon.service",
        service_runner: ServiceRunner | None = None,
        allow_command_run: bool = False,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.device_lister = device_lister
        self.allow_service_restart = allow_service_restart
        self.service_name = service_name
        self.service_runner = service_runner or run_systemctl
        self.allow_command_run = allow_command_run
        self.command_runner = command_runner
        self.csrf_token = secrets.token_urlsafe(32)
        self.activity_log = ActivityLogBuffer()
        self._lock = threading.RLock()
        self.activity_log.append("INFO", f"Loaded config {config_path}")


class RadioKeyWebHandler(BaseHTTPRequestHandler):
    server_version = "RadioKeyWeb/0.1"
    app: WebApp

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(render_dashboard(self.app))
            return
        if path == "/api/status":
            self._send_json(status_payload(self.app))
            return
        if path == "/api/config":
            self._send_json(config_payload(self.app))
            return
        if path == "/api/devices":
            self._send_json(devices_payload(self.app))
            return
        if path == "/api/bindings":
            self._send_text(render_bindings(self.app.config))
            return
        if path == "/api/logs":
            self._send_json(activity_log_payload(self.app))
            return
        self._send_text("Not found\n", status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if not self._csrf_valid(payload):
            self._send_json(
                {"error": "Invalid CSRF token"},
                status=HTTPStatus.FORBIDDEN,
            )
            return
        if path == "/api/config/commands":
            self._save_commands(payload)
            return
        if path == "/api/commands/run":
            self._run_command(payload)
            return
        if path == "/api/systemd/restart":
            self._restart_service()
            return
        if path == "/api/logs/clear":
            self.app.activity_log.clear()
            self._send_json({"ok": True, "entries": []})
            return
        self._send_text("Not found\n", status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_html(self, body: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(body.encode("utf-8"), "text/html; charset=utf-8", status)

    def _send_json(
        self, payload: object, *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_text(self, body: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(body.encode("utf-8"), "text/plain; charset=utf-8", status)

    def _send_bytes(self, body: bytes, content_type: str, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, object]:
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            return {}
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _csrf_valid(self, payload: dict[str, object]) -> bool:
        token = self.headers.get("X-CSRF-Token") or payload.get("csrf_token")
        return isinstance(token, str) and secrets.compare_digest(
            token, self.app.csrf_token
        )

    def _save_commands(self, payload: dict[str, object]) -> None:
        try:
            result = save_commands(self.app, payload.get("commands"))
        except ValueError as exc:
            self.app.activity_log.append("ERROR", f"Save rejected: {exc}")
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except ConfigError as exc:
            self.app.activity_log.append("ERROR", f"Save rejected: {exc}")
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except OSError as exc:
            self.app.activity_log.append("ERROR", f"Save failed: {exc}")
            self._send_json(
                {"error": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._send_json(result)

    def _restart_service(self) -> None:
        if not self.app.allow_service_restart:
            self._send_json(
                {"error": "Service restart is disabled"},
                status=HTTPStatus.FORBIDDEN,
            )
            return
        result = restart_service(self.app)
        status = HTTPStatus.OK if result["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR
        self._send_json(result, status=status)

    def _run_command(self, payload: dict[str, object]) -> None:
        if not self.app.allow_command_run:
            self._send_json(
                {"error": "Command run is disabled"},
                status=HTTPStatus.FORBIDDEN,
            )
            return
        try:
            result = run_configured_command(self.app, payload.get("key"))
        except KeyError as exc:
            self.app.activity_log.append("ERROR", str(exc.args[0]))
            self._send_json({"error": str(exc.args[0])}, status=HTTPStatus.NOT_FOUND)
            return
        except ValueError as exc:
            self.app.activity_log.append("ERROR", f"Run rejected: {exc}")
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result)


def make_handler(app: WebApp) -> type[RadioKeyWebHandler]:
    class BoundRadioKeyWebHandler(RadioKeyWebHandler):
        pass

    BoundRadioKeyWebHandler.app = app
    return BoundRadioKeyWebHandler


def run_web_server(
    config: AppConfig,
    *,
    config_path: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    device_lister: DeviceLister = list_input_devices,
    allow_service_restart: bool = False,
    service_name: str = "radio-key-daemon.service",
    service_runner: ServiceRunner | None = None,
    allow_command_run: bool = False,
    command_runner: CommandRunner | None = None,
) -> None:
    app = WebApp(
        config,
        config_path=config_path,
        device_lister=device_lister,
        allow_service_restart=allow_service_restart,
        service_name=service_name,
        service_runner=service_runner,
        allow_command_run=allow_command_run,
        command_runner=command_runner,
    )
    server = ThreadingHTTPServer((host, port), make_handler(app))
    logger.info("Serving web UI at http://%s:%s/", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Web UI shutdown requested")
    finally:
        server.server_close()


def status_payload(app: WebApp) -> dict[str, object]:
    return {
        "status": "ok",
        "config_valid": True,
        "config_path": app.config_path,
        "command_count": len(app.config.commands),
        "trigger_on": app.config.behavior.trigger_on,
        "repeat": app.config.behavior.repeat,
        "run_async": app.config.behavior.run_async,
        "version": __version__,
        "csrf_token": app.csrf_token,
        "allow_service_restart": app.allow_service_restart,
        "service_name": app.service_name,
        "allow_command_run": app.allow_command_run,
    }


def config_payload(app: WebApp) -> dict[str, object]:
    return {
        "device": asdict(app.config.device),
        "behavior": asdict(app.config.behavior),
        "logging": asdict(app.config.logging),
        "commands": [
            {
                "key": command.key,
                "name": command.name,
                "command": command_to_edit_text(command),
                "shell": command.shell,
                "timeout": command.timeout,
                "run_async": command.run_async,
                "debounce_ms": command.debounce_ms,
            }
            for command in sorted(
                app.config.commands.values(), key=lambda item: item.key
            )
        ],
    }


def devices_payload(app: WebApp) -> dict[str, object]:
    try:
        devices = app.device_lister()
    except (OSError, PermissionError, RuntimeError) as exc:
        return {"devices": [], "warning": str(exc)}
    return {
        "devices": [
            {
                "path": device.path,
                "name": device.name,
                "phys": device.phys,
                "uniq": device.uniq,
                "capabilities_summary": device.capabilities_summary,
                "is_keyboard_like": device.is_keyboard_like,
            }
            for device in devices
        ],
        "warning": None,
    }


def activity_log_payload(app: WebApp) -> dict[str, object]:
    return {"entries": app.activity_log.entries()}


def save_commands(app: WebApp, commands_payload: object) -> dict[str, object]:
    if not isinstance(commands_payload, list):
        raise ValueError("commands must be a list")
    commands = commands_from_payload(commands_payload)
    config_path = Path(app.config_path)
    with app._lock:
        raw_config = load_raw_config(config_path)
        raw_config["commands"] = commands
        parse_config(raw_config)
        backup_path = config_path.with_name(f"{config_path.name}.bak")
        shutil.copy2(config_path, backup_path)
        write_yaml_atomic(config_path, raw_config)
        app.config = load_config(config_path)
        app.activity_log.append(
            "INFO",
            f"Saved bindings. Backup: {backup_path}",
        )
    return {
        "ok": True,
        "backup_path": str(backup_path),
        "config": config_payload(app),
        "bindings": render_bindings(app.config),
    }


def commands_from_payload(payload: list[object]) -> dict[str, dict[str, object]]:
    commands: dict[str, dict[str, object]] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"commands[{index}] must be an object")
        key = require_string(item.get("key"), f"commands[{index}].key")
        if key in commands:
            raise ValueError(f"Duplicate key binding: {key}")
        command: dict[str, object] = {
            "command": parse_command_value(
                item.get("command"), f"commands[{index}].command"
            ),
            "shell": parse_bool(item.get("shell"), default=False),
        }
        name = optional_string(item.get("name"), f"commands[{index}].name")
        timeout = optional_int(item.get("timeout"), f"commands[{index}].timeout")
        run_async = optional_bool(item.get("run_async"), f"commands[{index}].run_async")
        debounce_ms = optional_int(
            item.get("debounce_ms"), f"commands[{index}].debounce_ms"
        )
        if name is not None:
            command["name"] = name
        if timeout is not None:
            command["timeout"] = timeout
        if run_async is not None:
            command["run_async"] = run_async
        if debounce_ms is not None:
            command["debounce_ms"] = debounce_ms
        commands[key] = command
    return commands


def parse_command_value(value: object, name: str) -> str | list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        if not value:
            raise ValueError(f"{name} must not be empty")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or JSON argv array")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} contains invalid JSON array") from exc
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            raise ValueError(f"{name} JSON value must be an array of strings")
        if not decoded:
            raise ValueError(f"{name} must not be empty")
        return decoded
    return text


def load_raw_config(path: Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse YAML config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a YAML mapping")
    return raw


def write_yaml_atomic(path: Path, raw_config: dict[str, object]) -> None:
    data = yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=False)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
    temp_path.replace(path)


def restart_service(app: WebApp) -> dict[str, object]:
    app.activity_log.append("INFO", f"Restart requested for {app.service_name}")
    try:
        completed = app.service_runner(["systemctl", "restart", app.service_name])
    except OSError as exc:
        app.activity_log.append("ERROR", f"Restart failed: {exc}")
        return {
            "ok": False,
            "service": app.service_name,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    if completed.returncode == 0:
        app.activity_log.append("INFO", f"Restarted {app.service_name}")
    else:
        app.activity_log.append(
            "ERROR",
            f"Restart failed for {app.service_name}: exit {completed.returncode}",
        )
    return {
        "ok": completed.returncode == 0,
        "service": app.service_name,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_configured_command(app: WebApp, key_payload: object) -> dict[str, object]:
    key = require_string(key_payload, "key")
    with app._lock:
        command = app.config.commands.get(key)
        if command is None:
            raise KeyError(f"No command configured for {key}")
        app.activity_log.append(
            "INFO",
            f"Run requested for {command.key}: {command.name or command.key}",
        )
        if app.command_runner is None:
            handler = ActivityLogHandler(app.activity_log)
            action_logger = logging.getLogger("radio_key_daemon.actions")
            action_logger.addHandler(handler)
            try:
                returncode = ActionRunner(app.config.behavior).run(command)
            finally:
                action_logger.removeHandler(handler)
        else:
            returncode = app.command_runner(command)
    if returncode is None:
        app.activity_log.append("INFO", f"Started async command for {command.key}")
    elif returncode == 0:
        app.activity_log.append("INFO", f"Command {command.key} completed with exit 0")
    else:
        app.activity_log.append(
            "ERROR", f"Command {command.key} failed with exit {returncode}"
        )
    return {
        "ok": returncode in (0, None),
        "key": command.key,
        "name": command.name or command.key,
        "started": returncode is None,
        "returncode": returncode,
    }


def run_systemctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )


def require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def optional_string(value: object, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def optional_int(value: object, name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def optional_bool(value: object, name: str) -> bool | None:
    if value is None or value == "":
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true, false, or null")
    return value


def parse_bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if not isinstance(value, bool):
        raise ValueError("shell must be true or false")
    return value


def render_dashboard(app: WebApp) -> str:
    status = status_payload(app)
    config = config_payload(app)
    devices = devices_payload(app)
    config_path = escape(app.config_path)
    restart_disabled = "" if app.allow_service_restart else "disabled"
    restart_title = (
        f"Restart {escape(app.service_name)}"
        if app.allow_service_restart
        else "Start web UI with --allow-service-restart to enable"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Radio Key Daemon</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --border: #d9dde5;
      --text: #161b22;
      --muted: #58606f;
      --accent: #176c72;
      --warn: #8a4b00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      background: var(--panel);
      padding: 18px 24px;
    }}
    main {{
      display: grid;
      gap: 16px;
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px;
    }}
    h1, h2 {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{ font-size: 1.45rem; }}
    h2 {{ font-size: 1rem; }}
    .subtle {{ color: var(--muted); font-size: 0.92rem; }}
    .grid {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      overflow: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 650; }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.86rem;
    }}
    pre {{
      margin: 10px 0 0;
      padding: 12px;
      background: #101418;
      color: #eef3f8;
      border-radius: 6px;
      overflow: auto;
      white-space: pre;
    }}
    .status {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }}
    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 4px 9px;
      background: #fbfcfd;
      font-size: 0.86rem;
    }}
    .ok {{ color: var(--accent); font-weight: 650; }}
    .warning {{ color: var(--warn); }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0;
    }}
    button {{
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      cursor: pointer;
      font: inherit;
      min-height: 34px;
      padding: 6px 10px;
    }}
    button.primary {{
      background: var(--accent);
      border-color: var(--accent);
      color: #ffffff;
    }}
    button.danger {{ color: #9b1c1c; }}
    button.run-button {{
      min-height: 28px;
      padding: 3px 7px;
      white-space: nowrap;
    }}
    button:disabled {{
      color: var(--muted);
      cursor: not-allowed;
      opacity: 0.65;
    }}
    input, select {{
      width: 100%;
      min-width: 90px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font: inherit;
      padding: 6px 8px;
    }}
    .command-input {{ min-width: 260px; }}
    .message {{
      min-height: 1.2rem;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .message.error {{ color: #9b1c1c; }}
    .message.success {{ color: var(--accent); }}
    .log-panel {{
      margin-top: 12px;
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #101418;
      color: #eef3f8;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.82rem;
      line-height: 1.35;
      padding: 10px;
    }}
    .log-row {{
      display: grid;
      gap: 8px;
      grid-template-columns: 7.5rem 4.5rem minmax(0, 1fr);
      padding: 2px 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .log-level-ERROR {{ color: #ffb4b4; }}
    .log-level-WARNING {{ color: #ffd08a; }}
    .log-level-INFO {{ color: #9ce3e8; }}
  </style>
</head>
<body>
  <header>
    <h1>Radio Key Daemon</h1>
    <div class="subtle">Web interface for {config_path}</div>
    <div class="status">
      <span class="pill ok">status: {escape(str(status["status"]))}</span>
      <span class="pill">commands: {escape(str(status["command_count"]))}</span>
      <span class="pill">version: {escape(str(status["version"]))}</span>
      <span class="pill">service: {escape(str(status["service_name"]))}</span>
    </div>
  </header>
  <main>
    <div class="grid">
      <section>
        <h2>Device Selection</h2>
        {render_key_value_table(config["device"])}
      </section>
      <section>
        <h2>Behavior</h2>
        {render_key_value_table(config["behavior"])}
      </section>
      <section>
        <h2>Logging</h2>
        {render_key_value_table(config["logging"])}
      </section>
    </div>
    <section>
      <h2>Key Bindings</h2>
      <div class="toolbar">
        <button type="button" onclick="addBindingRow()">Add binding</button>
        <button type="button" class="primary" onclick="saveBindings()">
          Save bindings
        </button>
        <button
          type="button"
          onclick="restartService()"
          {restart_disabled}
          title="{restart_title}"
        >
          Restart service
        </button>
      </div>
      <div id="message" class="message"></div>
      {render_commands_editor(config["commands"], app.allow_command_run)}
    </section>
    <section>
      <h2>Activity Log</h2>
      <div class="toolbar">
        <button type="button" onclick="refreshLogs()">Refresh</button>
        <button type="button" onclick="clearLogs()">Clear</button>
      </div>
      <div id="activity-log" class="log-panel"></div>
    </section>
    <section>
      <h2>Available Input Devices</h2>
      {render_devices_table(devices)}
    </section>
    <section>
      <h2>Bindings Preview</h2>
      <pre>{escape(render_bindings(app.config))}</pre>
    </section>
  </main>
  <script>
    const csrfToken = {json.dumps(app.csrf_token)};

    function rowTemplate(command = {{}}) {{
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>
          <input
            name="key"
            value="${{escapeAttr(command.key || "")}}"
            placeholder="KEY_F12"
          >
        </td>
        <td>
          <button
            type="button"
            class="run-button"
            data-key=""
            onclick="runBinding(this)"
            disabled
            title="Save this binding before running it"
          >
            Run
          </button>
        </td>
        <td>
          <input
            name="name"
            value="${{escapeAttr(command.name || "")}}"
            placeholder="Safe Tune"
          >
        </td>
        <td>
          <input
            class="command-input"
            name="command"
            value="${{escapeAttr(command.command || "")}}"
            placeholder="command or JSON argv array"
          >
        </td>
        <td>
          <select name="shell">
            <option value="false" ${{command.shell ? "" : "selected"}}>false</option>
            <option value="true" ${{command.shell ? "selected" : ""}}>true</option>
          </select>
        </td>
        <td>
          <input
            name="timeout"
            type="number"
            min="1"
            value="${{escapeAttr(command.timeout ?? "")}}"
          >
        </td>
        <td>
          <select name="run_async">
            <option
              value=""
              ${{command.run_async === null ||
                command.run_async === undefined ? "selected" : ""}}
            >inherit</option>
            <option
              value="false"
              ${{command.run_async === false ? "selected" : ""}}
            >false</option>
            <option
              value="true"
              ${{command.run_async === true ? "selected" : ""}}
            >true</option>
          </select>
        </td>
        <td>
          <input
            name="debounce_ms"
            type="number"
            min="0"
            value="${{escapeAttr(command.debounce_ms ?? "")}}"
          >
        </td>
        <td>
          <button
            type="button"
            class="danger"
            onclick="this.closest('tr').remove()"
          >
            Delete
          </button>
        </td>
      `;
      return row;
    }}

    function addBindingRow() {{
      document.querySelector("#commands-body").appendChild(rowTemplate());
    }}

    async function saveBindings() {{
      setMessage("Saving...", "");
      const rows = document.querySelectorAll("#commands-body tr");
      const commands = Array.from(rows).map((row) => {{
        const value = (name) => row.querySelector(`[name="${{name}}"]`).value;
        const nullableBool = (raw) => raw === "" ? null : raw === "true";
        const nullableInt = (raw) => raw === "" ? null : Number(raw);
        return {{
          key: value("key"),
          name: value("name") || null,
          command: value("command"),
          shell: value("shell") === "true",
          timeout: nullableInt(value("timeout")),
          run_async: nullableBool(value("run_async")),
          debounce_ms: nullableInt(value("debounce_ms")),
        }};
      }});
      const result = await postJson("/api/config/commands", {{commands}});
      if (!result.ok) {{
        setMessage(result.body.error || "Save failed", "error");
        return;
      }}
      setMessage(`Saved. Backup: ${{result.body.backup_path}}`, "success");
      refreshLogs();
      setTimeout(() => window.location.reload(), 700);
    }}

    async function restartService() {{
      setMessage("Restarting service...", "");
      const result = await postJson("/api/systemd/restart", {{}});
      if (!result.ok || !result.body.ok) {{
        const error = result.body.error || result.body.stderr || "Restart failed";
        setMessage(error, "error");
        return;
      }}
      setMessage("Service restarted.", "success");
      refreshLogs();
    }}

    async function runBinding(button) {{
      const key = button.dataset.key;
      if (!key) {{
        setMessage("Save this binding before running it.", "error");
        return;
      }}
      const previousText = button.textContent;
      button.disabled = true;
      button.textContent = "...";
      setMessage(`Running ${{key}}...`, "");
      const result = await postJson("/api/commands/run", {{key}});
      button.disabled = false;
      button.textContent = previousText;
      if (!result.ok || !result.body.ok) {{
        setMessage(result.body.error || `Command failed for ${{key}}`, "error");
        refreshLogs();
        return;
      }}
      if (result.body.started) {{
        setMessage(`Started ${{result.body.name}}.`, "success");
        refreshLogs();
        return;
      }}
      setMessage(
        `Finished ${{result.body.name}} with exit code ${{result.body.returncode}}.`,
        "success",
      );
      refreshLogs();
    }}

    async function refreshLogs() {{
      const response = await fetch("/api/logs", {{cache: "no-store"}});
      if (!response.ok) {{
        return;
      }}
      const payload = await response.json();
      renderLogs(payload.entries || []);
    }}

    async function clearLogs() {{
      const result = await postJson("/api/logs/clear", {{}});
      if (result.ok) {{
        renderLogs([]);
      }}
    }}

    function renderLogs(entries) {{
      const panel = document.querySelector("#activity-log");
      if (!entries.length) {{
        panel.innerHTML = '<div class="subtle">No activity yet</div>';
        return;
      }}
      panel.innerHTML = entries.map((entry) => {{
        const timestamp = escapeAttr(String(entry.timestamp || ""));
        const level = escapeAttr(String(entry.level || ""));
        const message = escapeAttr(String(entry.message || ""));
        return `
          <div class="log-row log-level-${{level}}">
            <span>${{timestamp}}</span>
            <span>${{level}}</span>
            <span>${{message}}</span>
          </div>
        `;
      }}).join("");
      panel.scrollTop = panel.scrollHeight;
    }}

    async function postJson(url, payload) {{
      const response = await fetch(url, {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        }},
        body: JSON.stringify(payload),
      }});
      let body = {{}};
      try {{
        body = await response.json();
      }} catch (_error) {{}}
      return {{ok: response.ok, body}};
    }}

    function setMessage(text, kind) {{
      const element = document.querySelector("#message");
      element.textContent = text;
      element.className = `message ${{kind}}`;
    }}

    function escapeAttr(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }}

    refreshLogs();
    setInterval(refreshLogs, 2000);
  </script>
</body>
</html>
"""


def render_key_value_table(values: object) -> str:
    if not isinstance(values, dict):
        return '<p class="subtle">No data</p>'
    rows = "\n".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in values.items()
    )
    return f"<table><tbody>{rows}</tbody></table>"


def render_commands_table(commands: object) -> str:
    if not isinstance(commands, list) or not commands:
        return '<p class="subtle">No commands configured</p>'
    rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(str(command['key']))}</code></td>"
        f"<td>{escape(str(command['name'] or ''))}</td>"
        f"<td><code>{escape(str(command['command']))}</code></td>"
        f"<td>{escape(str(command['shell']))}</td>"
        f"<td>{escape(str(command['timeout'] or ''))}</td>"
        f"<td>{escape(str(command['run_async'] or ''))}</td>"
        f"<td>{escape(str(command['debounce_ms'] or ''))}</td>"
        "</tr>"
        for command in commands
        if isinstance(command, dict)
    )
    return (
        "<table><thead><tr>"
        "<th>Key</th><th>Name</th><th>Command</th><th>Shell</th>"
        "<th>Timeout</th><th>Async</th><th>Debounce</th>"
        "</tr></thead><tbody>"
        f"{rows}</tbody></table>"
    )


def render_commands_editor(commands: object, allow_command_run: bool) -> str:
    if not isinstance(commands, list):
        commands = []
    rows = "\n".join(
        render_command_editor_row(command, allow_command_run)
        for command in commands
        if isinstance(command, dict)
    )
    return (
        "<table><thead><tr>"
        "<th>Key</th><th>Run</th><th>Name</th><th>Command</th><th>Shell</th>"
        "<th>Timeout</th><th>Async</th><th>Debounce</th><th></th>"
        '</tr></thead><tbody id="commands-body">'
        f"{rows}</tbody></table>"
    )


def render_command_editor_row(
    command: dict[str, object], allow_command_run: bool
) -> str:
    key = attr(command.get("key"))
    run_key = attr(command.get("key"))
    name = attr(command.get("name"))
    command_value = attr(command.get("command"))
    timeout = attr(command.get("timeout"))
    debounce_ms = attr(command.get("debounce_ms"))
    command_placeholder = (
        "/path/script.py or [&quot;/path/script.py&quot;, &quot;--fast&quot;]"
    )
    shell_true = "selected" if command.get("shell") is True else ""
    shell_false = "" if command.get("shell") is True else "selected"
    run_async = command.get("run_async")
    async_inherit = "selected" if run_async is None else ""
    async_false = "selected" if run_async is False else ""
    async_true = "selected" if run_async is True else ""
    run_disabled = "" if allow_command_run else "disabled"
    run_title = (
        "Run saved command"
        if allow_command_run
        else "Start web UI with --allow-command-run to enable"
    )
    return (
        "<tr>"
        "<td>"
        f'<input name="key" value="{key}" '
        'placeholder="KEY_F12">'
        "</td>"
        "<td>"
        f'<button type="button" class="run-button" data-key="{run_key}" '
        f'onclick="runBinding(this)" {run_disabled} '
        f'title="{escape(run_title)}">Run</button>'
        "</td>"
        "<td>"
        f'<input name="name" value="{name}" '
        'placeholder="Safe Tune">'
        "</td>"
        "<td>"
        '<input class="command-input" name="command" '
        f'value="{command_value}" '
        f'placeholder="{command_placeholder}">'
        "</td>"
        "<td>"
        '<select name="shell">'
        f'<option value="false" {shell_false}>false</option>'
        f'<option value="true" {shell_true}>true</option>'
        "</select>"
        "</td>"
        "<td>"
        '<input name="timeout" type="number" min="1" '
        f'value="{timeout}">'
        "</td>"
        "<td>"
        '<select name="run_async">'
        f'<option value="" {async_inherit}>inherit</option>'
        f'<option value="false" {async_false}>false</option>'
        f'<option value="true" {async_true}>true</option>'
        "</select>"
        "</td>"
        "<td>"
        '<input name="debounce_ms" type="number" min="0" '
        f'value="{debounce_ms}">'
        "</td>"
        "<td>"
        '<button type="button" class="danger" '
        "onclick=\"this.closest('tr').remove()\">Delete</button>"
        "</td>"
        "</tr>"
    )


def render_devices_table(payload: dict[str, object]) -> str:
    warning = payload.get("warning")
    if warning:
        return f'<p class="warning">{escape(str(warning))}</p>'
    devices = payload.get("devices")
    if not isinstance(devices, list) or not devices:
        return '<p class="subtle">No input devices found</p>'
    rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(str(device['path']))}</code></td>"
        f"<td>{escape(str(device['name']))}</td>"
        f"<td>{escape(str(device['phys']))}</td>"
        f"<td>{escape(str(device['is_keyboard_like']))}</td>"
        f"<td>{escape(str(device['capabilities_summary']))}</td>"
        "</tr>"
        for device in devices
        if isinstance(device, dict)
    )
    return (
        "<table><thead><tr>"
        "<th>Path</th><th>Name</th><th>Phys</th><th>Keyboard</th><th>Capabilities</th>"
        "</tr></thead><tbody>"
        f"{rows}</tbody></table>"
    )


def command_to_text(command: CommandConfig) -> str:
    if isinstance(command.command, str):
        return command.command
    return shlex.join(command.command)


def command_to_edit_text(command: CommandConfig) -> str:
    if isinstance(command.command, str):
        return command.command
    return json.dumps(command.command)


def escape(value: str) -> str:
    return html.escape(value, quote=True)


def attr(value: object) -> str:
    if value is None:
        return ""
    return escape(str(value))
