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


def test_web_loads_config_and_starts_server(tmp_path, monkeypatch):
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

    def fake_run_web_server(config, *, config_path, host, port):
        calls.append((config, config_path, host, port))

    monkeypatch.setattr(cli, "run_web_server", fake_run_web_server)

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--web",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
        ]
    )

    assert exit_code == 0
    assert calls[0][0].commands["KEY_F12"].name == "Safe Tune"
    assert calls[0][1] == str(config_file)
    assert calls[0][2] == "0.0.0.0"
    assert calls[0][3] == 9000
