from types import SimpleNamespace

from radio_key_daemon.actions import ActionRunner
from radio_key_daemon.config import ConfigState, parse_config
from radio_key_daemon.daemon import RadioKeyDaemon


class FakeDevice:
    path = "/dev/input/event9"
    name = "Fake keypad"

    def close(self):
        pass


def test_daemon_uses_updated_config_state_for_key_events(monkeypatch):
    first_config = parse_config(
        {
            "behavior": {
                "debounce_ms": 0,
            },
            "commands": {
                "KEY_F12": {
                    "name": "Old",
                    "command": "/bin/old",
                    "shell": False,
                }
            },
        }
    )
    second_config = parse_config(
        {
            "behavior": {
                "debounce_ms": 0,
            },
            "commands": {
                "KEY_F12": {
                    "name": "New",
                    "command": "/bin/new",
                    "shell": False,
                }
            },
        }
    )
    config_state = ConfigState(first_config)
    runner = ActionRunner(first_config.behavior, dry_run=True)
    calls = []

    monkeypatch.setattr("radio_key_daemon.daemon.InputDevice", object)
    monkeypatch.setattr("radio_key_daemon.daemon.ecodes", SimpleNamespace(EV_KEY=1))
    monkeypatch.setattr(
        "radio_key_daemon.daemon.categorize",
        lambda _event: SimpleNamespace(keystate=1, keycode="KEY_F12"),
    )
    monkeypatch.setattr(runner, "run", lambda command: calls.append(command))

    daemon = RadioKeyDaemon(config_state, FakeDevice(), runner)
    daemon._handle_event(SimpleNamespace(type=1))
    config_state.set(second_config)
    daemon._handle_event(SimpleNamespace(type=1))

    assert [command.name for command in calls] == ["Old", "New"]
