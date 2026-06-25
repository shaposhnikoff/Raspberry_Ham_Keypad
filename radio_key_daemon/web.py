from __future__ import annotations

import html
import json
import logging
import shlex
from collections.abc import Callable
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from radio_key_daemon import __version__
from radio_key_daemon.bindings_visualizer import render_bindings
from radio_key_daemon.config import AppConfig, CommandConfig
from radio_key_daemon.devices import DeviceInfo, list_input_devices

logger = logging.getLogger(__name__)

DeviceLister = Callable[[], list[DeviceInfo]]


class WebApp:
    def __init__(
        self,
        config: AppConfig,
        *,
        config_path: str,
        device_lister: DeviceLister = list_input_devices,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.device_lister = device_lister


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
        self._send_text("Not found\n", status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_html(
        self, body: str, *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self._send_bytes(body.encode("utf-8"), "text/html; charset=utf-8", status)

    def _send_json(
        self, payload: object, *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_text(
        self, body: str, *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self._send_bytes(body.encode("utf-8"), "text/plain; charset=utf-8", status)

    def _send_bytes(
        self, body: bytes, content_type: str, status: HTTPStatus
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


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
) -> None:
    app = WebApp(config, config_path=config_path, device_lister=device_lister)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    logger.info("Serving read-only web UI at http://%s:%s/", host, port)
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
                "command": command_to_text(command),
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


def render_dashboard(app: WebApp) -> str:
    status = status_payload(app)
    config = config_payload(app)
    devices = devices_payload(app)
    config_path = escape(app.config_path)
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
  </style>
</head>
<body>
  <header>
    <h1>Radio Key Daemon</h1>
    <div class="subtle">Read-only local web interface for {config_path}</div>
    <div class="status">
      <span class="pill ok">status: {escape(str(status["status"]))}</span>
      <span class="pill">commands: {escape(str(status["command_count"]))}</span>
      <span class="pill">version: {escape(str(status["version"]))}</span>
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
      <h2>Configured Commands</h2>
      {render_commands_table(config["commands"])}
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
</body>
</html>
"""


def render_key_value_table(values: object) -> str:
    if not isinstance(values, dict):
        return "<p class=\"subtle\">No data</p>"
    rows = "\n".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in values.items()
    )
    return f"<table><tbody>{rows}</tbody></table>"


def render_commands_table(commands: object) -> str:
    if not isinstance(commands, list) or not commands:
        return "<p class=\"subtle\">No commands configured</p>"
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


def render_devices_table(payload: dict[str, object]) -> str:
    warning = payload.get("warning")
    if warning:
        return f"<p class=\"warning\">{escape(str(warning))}</p>"
    devices = payload.get("devices")
    if not isinstance(devices, list) or not devices:
        return "<p class=\"subtle\">No input devices found</p>"
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


def escape(value: str) -> str:
    return html.escape(value, quote=True)
