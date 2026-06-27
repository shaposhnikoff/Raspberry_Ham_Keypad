from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from radio_key_daemon.config import DeviceConfig

try:  # pragma: no cover - depends on Linux input headers at install time
    from evdev import InputDevice, ecodes, list_devices
except ImportError:  # pragma: no cover
    InputDevice = None  # type: ignore[assignment]
    ecodes = None  # type: ignore[assignment]
    list_devices = None  # type: ignore[assignment]


class DeviceSelectionError(Exception):
    """Raised when a keyboard input device cannot be selected."""


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    name: str
    phys: str
    uniq: str
    capabilities_summary: str
    is_keyboard_like: bool


def list_input_devices() -> list[DeviceInfo]:
    _require_evdev()
    devices: list[DeviceInfo] = []
    for path in list_devices():
        device = InputDevice(path)
        devices.append(device_info(device))
        device.close()
    return devices


def device_info(device: Any) -> DeviceInfo:
    _require_evdev()
    capabilities = device.capabilities(verbose=True)
    key_codes = set(device.capabilities().get(ecodes.EV_KEY, []))
    is_keyboard_like = ecodes.KEY_A in key_codes and ecodes.KEY_ENTER in key_codes
    return DeviceInfo(
        path=device.path,
        name=device.name or "",
        phys=device.phys or "",
        uniq=device.uniq or "",
        capabilities_summary=_summarize_capabilities(capabilities),
        is_keyboard_like=is_keyboard_like,
    )


def open_selected_device(config: DeviceConfig) -> Any:
    _require_evdev()
    if config.path:
        return InputDevice(config.path)
    matches = _matching_devices(config)
    if not matches:
        raise DeviceSelectionError(
            "No input device matched device.name_contains or device.phys_contains"
        )
    if len(matches) > 1:
        keyboard_like_matches = [
            device for device in matches if device_info(device).is_keyboard_like
        ]
        if len(keyboard_like_matches) == 1:
            selected = keyboard_like_matches[0]
            _close_unselected_devices(matches, selected)
            return selected
        details = "\n".join(
            f"- {device.path}: name={device.name!r} phys={device.phys!r}"
            for device in matches
        )
        for device in matches:
            device.close()
        raise DeviceSelectionError(f"Multiple matching input devices found:\n{details}")
    return matches[0]


def _close_unselected_devices(devices: list[Any], selected: Any) -> None:
    for device in devices:
        if device is not selected:
            device.close()


def _matching_devices(config: DeviceConfig) -> list[Any]:
    _require_evdev()
    matches: list[Any] = []
    for path in list_devices():
        device = InputDevice(path)
        name_ok = (
            config.name_contains is None
            or config.name_contains.lower() in (device.name or "").lower()
        )
        phys_ok = (
            config.phys_contains is None
            or config.phys_contains.lower() in (device.phys or "").lower()
        )
        if name_ok and phys_ok:
            matches.append(device)
        else:
            device.close()
    return matches


def _summarize_capabilities(capabilities: dict[object, object]) -> str:
    parts: list[str] = []
    for event_type, values in capabilities.items():
        name = str(event_type[0]) if isinstance(event_type, tuple) else str(event_type)
        try:
            count = len(values)  # type: ignore[arg-type]
        except TypeError:
            count = 1
        parts.append(f"{name}:{count}")
    return ", ".join(parts)


def _require_evdev() -> None:
    if InputDevice is None or ecodes is None or list_devices is None:
        raise RuntimeError("evdev is required to access Linux input devices")
