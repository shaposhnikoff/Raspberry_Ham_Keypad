import json
import textwrap
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

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


def _load_sample_config(tmp_path):
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
    return load_config(config_file)


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
