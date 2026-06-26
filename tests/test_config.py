import textwrap

import pytest

from radio_key_daemon.config import ConfigError, load_config


def test_loads_yaml_config_with_command_overrides(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            device:
              path: /dev/input/event9
            behavior:
              exclusive_grab: true
              trigger_on: up
              repeat: true
              debounce_ms: 100
              command_timeout_sec: 5
              run_async: true
              restore_on_exit: true
            logging:
              level: DEBUG
            commands:
              KEY_F12:
                name: Safe Tune
                command: ["/home/pi/safe_tune.py", "--fast"]
                shell: false
                timeout: 3
                run_async: false
                debounce_ms: 500
            """
        ),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.device.path == "/dev/input/event9"
    assert config.behavior.exclusive_grab is True
    assert config.behavior.trigger_on == "up"
    assert config.logging.level == "DEBUG"
    command = config.commands["KEY_F12"]
    assert command.command == ["/home/pi/safe_tune.py", "--fast"]
    assert command.timeout == 3
    assert command.run_async is False
    assert command.debounce_ms == 500


def test_rejects_unknown_key_code(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            commands:
              KEY_NOT_REAL:
                command: echo nope
                shell: true
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unknown key code"):
        load_config(config_file)


def test_rejects_shell_false_string_with_spaces(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            commands:
              KEY_F12:
                command: "echo unsafe split"
                shell: false
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="array argv or set shell: true"):
        load_config(config_file)


def test_loads_ftdx10_keypad_config_without_evdev():
    config = load_config("ftdx10/ftdx10_keypad_full_config.yaml")

    assert config.commands["KEY_KP1"].name == "Band 1.8 MHz"
    assert config.commands["KEY_KPDOT"].name == "CW Beacon"
    assert config.commands["KEY_KPDOT"].command == "/home/pi/radio/beacon.sh"
    assert config.commands["KEY_KPDOT"].timeout == 60
    assert config.commands["KEY_KPPLUS"].name == "Frequency Up"
