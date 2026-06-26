import textwrap

import radio_key_daemon.__main__ as cli
from radio_key_daemon.__main__ import main


def test_show_bindings_prints_configured_keys_and_exits(tmp_path, capsys):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            commands:
              KEY_F12:
                name: Safe Tune
                command: /home/pi/radio/safe_tune.py
                shell: false
            """
        ),
        encoding="utf-8",
    )

    exit_code = main(["--config", str(config_file), "--show-bindings"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Current key bindings" in captured.out
    assert "[F12: Safe Tune]" in captured.out
    assert captured.err == ""


def test_show_bindings_requires_config(capsys):
    exit_code = main(["--show-bindings"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--show-bindings requires --config" in captured.err


def test_web_requires_config(capsys):
    exit_code = main(["--web"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--web requires --config" in captured.err


def test_web_only_loads_config_and_starts_server(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            commands:
              KEY_F12:
                name: Safe Tune
                command: /home/pi/radio/safe_tune.py
                shell: false
            """
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run_web_server(
        config,
        *,
        config_path,
        host,
        port,
        allow_service_restart,
        service_name,
        allow_command_run,
    ):
        calls.append(
            (
                config,
                config_path,
                host,
                port,
                allow_service_restart,
                service_name,
                allow_command_run,
            )
        )

    monkeypatch.setattr(cli, "run_web_server", fake_run_web_server)

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--web-only",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--allow-service-restart",
            "--allow-command-run",
            "--service-name",
            "radio-key-daemon.service",
        ]
    )

    assert exit_code == 0
    assert calls[0][0].commands["KEY_F12"].name == "Safe Tune"
    assert calls[0][1] == str(config_file)
    assert calls[0][2] == "0.0.0.0"
    assert calls[0][3] == 9000
    assert calls[0][4] is True
    assert calls[0][5] == "radio-key-daemon.service"
    assert calls[0][6] is True


def test_web_starts_server_and_keypad_daemon(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            commands:
              KEY_F12:
                name: Safe Tune
                command: /home/pi/radio/safe_tune.py
                shell: false
            """
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeHandle:
        def shutdown(self):
            calls.append(("shutdown",))

    class FakeDaemon:
        def __init__(self, config_state, device, runner):
            calls.append(("daemon", config_state, device, runner))

        def install_signal_handlers(self):
            calls.append(("signals",))

        def run(self):
            calls.append(("run",))

    def fake_start_web_server(
        config,
        *,
        config_path,
        config_state,
        host,
        port,
        allow_service_restart,
        service_name,
        allow_command_run,
        command_runner,
    ):
        calls.append(
            (
                "web",
                config,
                config_path,
                config_state,
                host,
                port,
                allow_service_restart,
                service_name,
                allow_command_run,
                command_runner,
            )
        )
        return FakeHandle()

    monkeypatch.setattr(cli, "start_web_server", fake_start_web_server)
    monkeypatch.setattr(cli, "open_selected_device", lambda _device_config: "device")
    monkeypatch.setattr(cli, "RadioKeyDaemon", FakeDaemon)

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--web",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--allow-command-run",
        ]
    )

    assert exit_code == 0
    assert calls[0][0] == "web"
    assert calls[0][4] == "0.0.0.0"
    assert calls[0][5] == 9000
    assert calls[0][8] is True
    assert calls[1][0] == "daemon"
    assert calls[1][1] is calls[0][3]
    assert calls[0][9].__self__ is calls[1][3]
    assert calls[-1] == ("shutdown",)


def test_web_and_web_only_are_mutually_exclusive(capsys):
    exit_code = main(["--config", "config.yaml", "--web", "--web-only"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--web and --web-only cannot be used together" in captured.err


def test_web_shutdown_runs_once_when_keypad_daemon_fails(
    tmp_path,
    monkeypatch,
    capsys,
):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            commands:
              KEY_F12:
                name: Safe Tune
                command: /home/pi/radio/safe_tune.py
                shell: false
            """
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeHandle:
        def shutdown(self):
            calls.append("shutdown")

    class FailingDaemon:
        def __init__(self, _config_state, _device, _runner):
            pass

        def install_signal_handlers(self):
            pass

        def run(self):
            raise RuntimeError("keypad loop failed")

    monkeypatch.setattr(cli, "start_web_server", lambda *_args, **_kwargs: FakeHandle())
    monkeypatch.setattr(cli, "open_selected_device", lambda _device_config: "device")
    monkeypatch.setattr(cli, "RadioKeyDaemon", FailingDaemon)

    exit_code = main(["--config", str(config_file), "--web"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "keypad loop failed" in captured.err
    assert calls == ["shutdown"]
