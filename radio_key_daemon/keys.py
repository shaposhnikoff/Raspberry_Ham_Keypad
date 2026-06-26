from __future__ import annotations

import time
from dataclasses import dataclass, field

try:
    from evdev import ecodes
except ImportError:  # pragma: no cover - exercised only without dependencies
    ecodes = None  # type: ignore[assignment]


COMMON_KEY_CODES = {
    "KEY_0",
    "KEY_1",
    "KEY_2",
    "KEY_3",
    "KEY_4",
    "KEY_5",
    "KEY_6",
    "KEY_7",
    "KEY_8",
    "KEY_9",
    "KEY_A",
    "KEY_APOSTROPHE",
    "KEY_B",
    "KEY_BACKSLASH",
    "KEY_BACKSPACE",
    "KEY_C",
    "KEY_CAPSLOCK",
    "KEY_COMMA",
    "KEY_D",
    "KEY_DELETE",
    "KEY_DOT",
    "KEY_DOWN",
    "KEY_E",
    "KEY_END",
    "KEY_ENTER",
    "KEY_ESC",
    "KEY_EQUAL",
    "KEY_F",
    "KEY_F1",
    "KEY_F2",
    "KEY_F3",
    "KEY_F4",
    "KEY_F5",
    "KEY_F6",
    "KEY_F7",
    "KEY_F8",
    "KEY_F9",
    "KEY_F10",
    "KEY_F11",
    "KEY_F12",
    "KEY_G",
    "KEY_GRAVE",
    "KEY_H",
    "KEY_HOME",
    "KEY_I",
    "KEY_INSERT",
    "KEY_J",
    "KEY_K",
    "KEY_KP0",
    "KEY_KP1",
    "KEY_KP2",
    "KEY_KP3",
    "KEY_KP4",
    "KEY_KP5",
    "KEY_KP6",
    "KEY_KP7",
    "KEY_KP8",
    "KEY_KP9",
    "KEY_KPASTERISK",
    "KEY_KPDOT",
    "KEY_KPENTER",
    "KEY_KPMINUS",
    "KEY_KPPLUS",
    "KEY_KPSLASH",
    "KEY_L",
    "KEY_LEFT",
    "KEY_LEFTALT",
    "KEY_LEFTBRACE",
    "KEY_LEFTCTRL",
    "KEY_LEFTSHIFT",
    "KEY_M",
    "KEY_MINUS",
    "KEY_N",
    "KEY_NUMLOCK",
    "KEY_O",
    "KEY_P",
    "KEY_PAGEDOWN",
    "KEY_PAGEUP",
    "KEY_Q",
    "KEY_R",
    "KEY_RIGHT",
    "KEY_RIGHTALT",
    "KEY_RIGHTBRACE",
    "KEY_RIGHTCTRL",
    "KEY_RIGHTSHIFT",
    "KEY_S",
    "KEY_SEMICOLON",
    "KEY_SLASH",
    "KEY_SPACE",
    "KEY_T",
    "KEY_TAB",
    "KEY_U",
    "KEY_UP",
    "KEY_V",
    "KEY_W",
    "KEY_X",
    "KEY_Y",
    "KEY_Z",
}


def is_known_key_code(key_code: str) -> bool:
    if not isinstance(key_code, str) or not key_code.startswith("KEY_"):
        return False
    if ecodes is None:
        return key_code in COMMON_KEY_CODES
    return key_code in ecodes.ecodes


def normalize_key_code(key_code: str | list[str]) -> str:
    if isinstance(key_code, list):
        preferred = [code for code in key_code if code.startswith("KEY_")]
        return preferred[0] if preferred else key_code[0]
    return key_code


def event_matches_trigger(keystate: int, trigger_on: str, repeat: bool) -> bool:
    if keystate == 2 and not repeat:
        return False
    if trigger_on == "down":
        return keystate == 1 or (repeat and keystate == 2)
    if trigger_on == "up":
        return keystate == 0
    return False


@dataclass
class Debouncer:
    default_debounce_ms: int
    _last_fire_by_key: dict[str, float] = field(default_factory=dict)

    def should_fire(
        self,
        key_code: str,
        *,
        now: float | None = None,
        debounce_ms: int | None = None,
    ) -> bool:
        current_time = time.monotonic() if now is None else now
        effective_debounce_ms = (
            self.default_debounce_ms if debounce_ms is None else debounce_ms
        )
        previous = self._last_fire_by_key.get(key_code)
        if previous is not None:
            elapsed_ms = (current_time - previous) * 1000
            if elapsed_ms < effective_debounce_ms:
                return False
        self._last_fire_by_key[key_code] = current_time
        return True
