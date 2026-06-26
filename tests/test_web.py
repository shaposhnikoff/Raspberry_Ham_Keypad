import json
import subprocess
import textwrap
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import yaml

from radio_key_daemon.config import load_config
from radio_key_daemon.devices import DeviceInfo
from radio_key_daemon.web import WebApp, devices_payload, make_handler


def test_dashboard_returns_configured_commands(tmp_path):
    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=_fake_devices,
    )

    status, content_type, body = _get(app, "/")

    assert status == 200
    assert "text/html" in content_type
    assert "Safe Tune" in body
    assert "KEY_F12" in body
    assert "<th>Key</th><th>Run</th><th>Name</th>" in body


def test_dashboard_disables_run_buttons_by_default(tmp_path):
    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _get(app, "/")

    assert status == 200
    assert 'data-key="KEY_F12"' in body
    assert "--allow-command-run" in body
    assert "disabled" in body


def test_status_api_returns_json(tmp_path):
    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=_fake_devices,
    )

    status, content_type, body = _get(app, "/api/status")

    payload = json.loads(body)
    assert status == 200
    assert "application/json" in content_type
    assert payload["status"] == "ok"
    assert payload["command_count"] == 1


def test_config_api_returns_read_only_command_text(tmp_path):
    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=_fake_devices,
    )

    status, content_type, body = _get(app, "/api/config")

    payload = json.loads(body)
    assert status == 200
    assert "application/json" in content_type
    assert payload["commands"] == [
        {
            "key": "KEY_F12",
            "name": "Safe Tune",
            "command": "/home/pi/radio/safe_tune.py",
            "shell": False,
            "timeout": None,
            "run_async": None,
            "debounce_ms": None,
        }
    ]


def test_bindings_api_returns_text(tmp_path):
    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=_fake_devices,
    )

    status, content_type, body = _get(app, "/api/bindings")

    assert status == 200
    assert "text/plain" in content_type
    assert "Current key bindings" in body
    assert "[F12: Safe Tune]" in body


def test_devices_payload_reports_listing_warning(tmp_path):
    def failing_lister():
        raise PermissionError("input devices are not readable")

    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=failing_lister,
    )

    payload = devices_payload(app)

    assert payload == {
        "devices": [],
        "warning": "input devices are not readable",
    }


def test_unknown_route_returns_404(tmp_path):
    app = WebApp(
        _load_sample_config(tmp_path),
        config_path=str(tmp_path / "config.yaml"),
        device_lister=_fake_devices,
    )

    status, content_type, body = _get(app, "/missing")

    assert status == 404
    assert "text/plain" in content_type
    assert body == "Not found\n"


def test_save_commands_rewrites_only_commands_and_creates_backup(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, content_type, body = _post(
        app,
        "/api/config/commands",
        {
            "commands": [
                {
                    "key": "KEY_F10",
                    "name": "Restore Power",
                    "command": "/home/pi/radio/restore_power.py",
                    "shell": False,
                    "timeout": 5,
                    "run_async": False,
                    "debounce_ms": 1000,
                }
            ]
        },
    )

    payload = json.loads(body)
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    backup = tmp_path / "config.yaml.bak"
    assert status == 200
    assert "application/json" in content_type
    assert payload["ok"] is True
    assert backup.exists()
    assert raw["device"] == {"path": "/dev/input/event9"}
    assert raw["commands"] == {
        "KEY_F10": {
            "command": "/home/pi/radio/restore_power.py",
            "shell": False,
            "name": "Restore Power",
            "timeout": 5,
            "run_async": False,
            "debounce_ms": 1000,
        }
    }
    assert app.config.commands["KEY_F10"].name == "Restore Power"


def test_save_commands_accepts_json_argv_array(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _post(
        app,
        "/api/config/commands",
        {
            "commands": [
                {
                    "key": "KEY_F12",
                    "name": "Safe Tune",
                    "command": '["/home/pi/safe_tune.py", "--fast"]',
                    "shell": False,
                    "timeout": None,
                    "run_async": None,
                    "debounce_ms": None,
                }
            ]
        },
    )

    payload = json.loads(body)
    assert status == 200
    assert payload["ok"] is True
    assert app.config.commands["KEY_F12"].command == [
        "/home/pi/safe_tune.py",
        "--fast",
    ]


def test_save_commands_rejects_missing_csrf(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _post(
        app,
        "/api/config/commands",
        {"commands": []},
        csrf_token="wrong",
    )

    payload = json.loads(body)
    assert status == 403
    assert payload["error"] == "Invalid CSRF token"
    assert not (tmp_path / "config.yaml.bak").exists()


def test_save_commands_rejects_invalid_binding_without_writing(tmp_path):
    config_file = _write_sample_config(tmp_path)
    before = config_file.read_text(encoding="utf-8")
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _post(
        app,
        "/api/config/commands",
        {
            "commands": [
                {
                    "key": "KEY_F12",
                    "name": "Bad",
                    "command": "echo bad",
                    "shell": False,
                    "timeout": None,
                    "run_async": None,
                    "debounce_ms": None,
                }
            ]
        },
    )

    payload = json.loads(body)
    assert status == 400
    assert "array argv or set shell: true" in payload["error"]
    assert config_file.read_text(encoding="utf-8") == before
    assert not (tmp_path / "config.yaml.bak").exists()


def test_save_commands_rejects_deleting_all_bindings(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _post(
        app,
        "/api/config/commands",
        {"commands": []},
    )

    payload = json.loads(body)
    assert status == 400
    assert payload["error"] == "At least one command mapping is required"


def test_restart_service_requires_opt_in(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _post(app, "/api/systemd/restart", {})

    payload = json.loads(body)
    assert status == 403
    assert payload["error"] == "Service restart is disabled"


def test_restart_service_invokes_configured_service(tmp_path):
    config_file = _write_sample_config(tmp_path)
    calls = []

    def fake_runner(args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
        allow_service_restart=True,
        service_name="radio-key-daemon.service",
        service_runner=fake_runner,
    )

    status, _content_type, body = _post(app, "/api/systemd/restart", {})

    payload = json.loads(body)
    assert status == 200
    assert payload["ok"] is True
    assert calls == [["systemctl", "restart", "radio-key-daemon.service"]]


def test_run_command_requires_opt_in(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
    )

    status, _content_type, body = _post(
        app,
        "/api/commands/run",
        {"key": "KEY_F12"},
    )

    payload = json.loads(body)
    assert status == 403
    assert payload["error"] == "Command run is disabled"


def test_run_command_rejects_missing_csrf(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
        allow_command_run=True,
    )

    status, _content_type, body = _post(
        app,
        "/api/commands/run",
        {"key": "KEY_F12"},
        csrf_token="wrong",
    )

    payload = json.loads(body)
    assert status == 403
    assert payload["error"] == "Invalid CSRF token"


def test_run_command_returns_404_for_unknown_key(tmp_path):
    config_file = _write_sample_config(tmp_path)
    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
        allow_command_run=True,
    )

    status, _content_type, body = _post(
        app,
        "/api/commands/run",
        {"key": "KEY_F11"},
    )

    payload = json.loads(body)
    assert status == 404
    assert payload["error"] == "No command configured for KEY_F11"


def test_run_command_invokes_saved_command(tmp_path):
    config_file = _write_sample_config(tmp_path)
    calls = []

    def fake_command_runner(command):
        calls.append(command)
        return 0

    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
        allow_command_run=True,
        command_runner=fake_command_runner,
    )

    status, _content_type, body = _post(
        app,
        "/api/commands/run",
        {"key": "KEY_F12"},
    )

    payload = json.loads(body)
    assert status == 200
    assert payload == {
        "key": "KEY_F12",
        "name": "Safe Tune",
        "ok": True,
        "returncode": 0,
        "started": False,
    }
    assert calls[0].key == "KEY_F12"
    assert calls[0].command == "/home/pi/radio/safe_tune.py"


def test_run_command_reports_failure_return_code(tmp_path):
    config_file = _write_sample_config(tmp_path)

    def fake_command_runner(_command):
        return 127

    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
        allow_command_run=True,
        command_runner=fake_command_runner,
    )

    status, _content_type, body = _post(
        app,
        "/api/commands/run",
        {"key": "KEY_F12"},
    )

    payload = json.loads(body)
    assert status == 200
    assert payload["ok"] is False
    assert payload["returncode"] == 127


def test_run_command_reports_async_started(tmp_path):
    config_file = _write_sample_config(tmp_path)

    def fake_command_runner(_command):
        return None

    app = WebApp(
        load_config(config_file),
        config_path=str(config_file),
        device_lister=_fake_devices,
        allow_command_run=True,
        command_runner=fake_command_runner,
    )

    status, _content_type, body = _post(
        app,
        "/api/commands/run",
        {"key": "KEY_F12"},
    )

    payload = json.loads(body)
    assert status == 200
    assert payload["ok"] is True
    assert payload["started"] is True
    assert payload["returncode"] is None


def _load_sample_config(tmp_path):
    return load_config(_write_sample_config(tmp_path))


def _write_sample_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            device:
              path: /dev/input/event9
            commands:
              KEY_F12:
                name: Safe Tune
                command: /home/pi/radio/safe_tune.py
                shell: false
            """
        ),
        encoding="utf-8",
    )
    return config_file


def _fake_devices():
    return [
        DeviceInfo(
            path="/dev/input/event9",
            name="USB Keypad",
            phys="usb-1",
            uniq="",
            capabilities_summary="EV_KEY:10",
            is_keyboard_like=True,
        )
    ]


def _get(app, path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}{path}"
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return (
                    response.status,
                    response.headers.get("Content-Type", ""),
                    response.read().decode("utf-8"),
                )
        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                exc.headers.get("Content-Type", ""),
                exc.read().decode("utf-8"),
            )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _post(app, path, payload, csrf_token=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": app.csrf_token if csrf_token is None else csrf_token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return (
                    response.status,
                    response.headers.get("Content-Type", ""),
                    response.read().decode("utf-8"),
                )
        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                exc.headers.get("Content-Type", ""),
                exc.read().decode("utf-8"),
            )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
