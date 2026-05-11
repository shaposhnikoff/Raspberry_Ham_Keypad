from __future__ import annotations

import time
from dataclasses import dataclass, field

try:
    from evdev import ecodes
except ImportError:  # pragma: no cover - exercised only without dependencies
    ecodes = None  # type: ignore[assignment]


COMMON_KEY_CODES = {
    "KEY_A",
    "KEY_ESC",
    "KEY_F10",
    "KEY_F11",
    "KEY_F12",
    "KEY_KPENTER",
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
