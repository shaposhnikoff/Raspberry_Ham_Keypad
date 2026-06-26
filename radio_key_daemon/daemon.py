from __future__ import annotations

import logging
import signal
import threading

from radio_key_daemon.actions import ActionRunner
from radio_key_daemon.config import ConfigState
from radio_key_daemon.keys import Debouncer, event_matches_trigger, normalize_key_code

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depends on Linux input headers at install time
    from evdev import InputDevice, categorize, ecodes
except ImportError:  # pragma: no cover
    InputDevice = None  # type: ignore[assignment]
    categorize = None  # type: ignore[assignment]
    ecodes = None  # type: ignore[assignment]


class RadioKeyDaemon:
    def __init__(
        self,
        config_state: ConfigState,
        device: InputDevice,
        runner: ActionRunner,
    ) -> None:
        self._config_state = config_state
        self._device = device
        self._runner = runner
        self._stop_event = threading.Event()
        self._grabbed = False
        config = config_state.get()
        self._debouncer = Debouncer(config.behavior.debounce_ms)

    def request_stop(self, signum: int | None = None) -> None:
        if signum is None:
            logger.info("Shutdown requested")
        else:
            logger.info("Shutdown requested by signal %s", signum)
        self._stop_event.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, lambda signum, _frame: self.request_stop(signum))
        signal.signal(signal.SIGTERM, lambda signum, _frame: self.request_stop(signum))

    def run(self) -> None:
        try:
            self._grab_if_configured()
            logger.info(
                "Reading events from %s (%s)", self._device.path, self._device.name
            )
            for event in self._device.read_loop():
                if self._stop_event.is_set():
                    break
                self._handle_event(event)
        finally:
            self._restore_device()
            self._device.close()

    def _grab_if_configured(self) -> None:
        if not self._config_state.get().behavior.exclusive_grab:
            return
        try:
            self._device.grab()
        except PermissionError as exc:
            raise PermissionError(
                "Could not exclusive-grab input device. Run as root, add the "
                "service user to the input group, or install a udev rule."
            ) from exc
        self._grabbed = True
        logger.info("Exclusive grab enabled for %s", self._device.path)

    def _restore_device(self) -> None:
        if self._grabbed:
            try:
                self._device.ungrab()
                logger.info("Released exclusive grab for %s", self._device.path)
            finally:
                self._grabbed = False

    def _handle_event(self, event: object) -> None:
        _require_evdev()
        config = self._config_state.get()
        if getattr(event, "type", None) != ecodes.EV_KEY:
            return
        key_event = categorize(event)
        if not event_matches_trigger(
            key_event.keystate,
            config.behavior.trigger_on,
            config.behavior.repeat,
        ):
            return
        key_code = normalize_key_code(key_event.keycode)
        command = config.commands.get(key_code)
        if command is None:
            logger.debug("No command configured for %s", key_code)
            return
        if not self._debouncer.should_fire(key_code, debounce_ms=command.debounce_ms):
            logger.debug("Debounced %s", key_code)
            return
        logger.info("Triggering command for %s", key_code)
        self._runner.run(command)


def _require_evdev() -> None:
    if InputDevice is None or categorize is None or ecodes is None:
        raise RuntimeError("evdev is required to read Linux input devices")
