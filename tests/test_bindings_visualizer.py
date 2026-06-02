import textwrap

from radio_key_daemon.bindings_visualizer import render_bindings
from radio_key_daemon.config import load_config


def test_renders_keyboard_bindings_from_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            behavior:
              trigger_on: down
              repeat: false
              debounce_ms: 250
              command_timeout_sec: 30
              run_async: false
            commands:
              KEY_F12:
                name: Safe Tune
                command: /home/pi/radio/safe_tune.py
                shell: false
              KEY_KPENTER:
                name: Test beep
                command: "echo beep"
                shell: true
            """
        ),
        encoding="utf-8",
    )
    config = load_config(config_file)

    output = render_bindings(config)

    assert "Current key bindings" in output
    assert "trigger_on=down" in output
    assert "[F12: Safe Tune]" in output
    assert "[KPENTER: Test beep]" in output
    assert "KEY_F12" in output
    assert "/home/pi/radio/safe_tune.py" in output
    assert "echo beep" in output
