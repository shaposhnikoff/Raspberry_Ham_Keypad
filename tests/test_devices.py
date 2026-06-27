from __future__ import annotations

from radio_key_daemon import devices
from radio_key_daemon.config import DeviceConfig


class FakeEcodes:
    EV_KEY = 1
    KEY_A = 30
    KEY_ENTER = 28
    KEY_VOLUMEUP = 115
    KEY_POWER = 116


class FakeDevice:
    def __init__(self, path: str, name: str, phys: str, key_codes: set[int]) -> None:
        self.path = path
        self.name = name
        self.phys = phys
        self.uniq = ""
        self.key_codes = key_codes
        self.closed = False

    def capabilities(self, verbose: bool = False) -> dict[object, object]:
        if verbose:
            return {"EV_KEY": list(self.key_codes)}
        return {FakeEcodes.EV_KEY: list(self.key_codes)}

    def close(self) -> None:
        self.closed = True


def test_open_selected_device_prefers_single_keyboard_like_match(monkeypatch):
    fake_devices = {
        "/dev/input/event3": FakeDevice(
            "/dev/input/event3",
            "SONiX USB Keyboard System Control",
            "usb-0000:01:00.0-1.4/input1",
            {FakeEcodes.KEY_POWER},
        ),
        "/dev/input/event1": FakeDevice(
            "/dev/input/event1",
            "SONiX USB Keyboard Consumer Control",
            "usb-0000:01:00.0-1.4/input1",
            {FakeEcodes.KEY_VOLUMEUP},
        ),
        "/dev/input/event0": FakeDevice(
            "/dev/input/event0",
            "SONiX USB Keyboard",
            "usb-0000:01:00.0-1.4/input0",
            {FakeEcodes.KEY_A, FakeEcodes.KEY_ENTER},
        ),
    }

    monkeypatch.setattr(devices, "ecodes", FakeEcodes)
    monkeypatch.setattr(devices, "list_devices", lambda: list(fake_devices))
    monkeypatch.setattr(devices, "InputDevice", lambda path: fake_devices[path])

    selected = devices.open_selected_device(DeviceConfig(name_contains="USB Keyboard"))

    assert selected.path == "/dev/input/event0"
    assert fake_devices["/dev/input/event0"].closed is False
    assert fake_devices["/dev/input/event1"].closed is True
    assert fake_devices["/dev/input/event3"].closed is True
