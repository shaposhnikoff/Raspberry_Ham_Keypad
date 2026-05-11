from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from radio_key_daemon.keys import is_known_key_code


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class DeviceConfig:
    path: str | None = None
    name_contains: str | None = None
    phys_contains: str | None = None


@dataclass(frozen=True)
class BehaviorConfig:
    exclusive_grab: bool = False
    trigger_on: str = "down"
    repeat: bool = False
    debounce_ms: int = 250
    command_timeout_sec: int = 30
    run_async: bool = False
    restore_on_exit: bool = True


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class CommandConfig:
    key: str
    command: str | list[str]
    name: str | None = None
    shell: bool = False
    timeout: int | None = None
    run_async: bool | None = None
    debounce_ms: int | None = None


@dataclass(frozen=True)
class AppConfig:
    device: DeviceConfig = field(default_factory=DeviceConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    commands: dict[str, CommandConfig] = field(default_factory=dict)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigError(f"Could not read config file {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse YAML config {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a YAML mapping")
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    device = _parse_device(raw.get("device", {}))
    behavior = _parse_behavior(raw.get("behavior", {}))
    logging_config = _parse_logging(raw.get("logging", {}))
    commands = _parse_commands(raw.get("commands", {}))
    if not commands:
        raise ConfigError("At least one command mapping is required")
    return AppConfig(
        device=device,
        behavior=behavior,
        logging=logging_config,
        commands=commands,
    )


def _parse_device(raw: Any) -> DeviceConfig:
    data = _mapping(raw, "device")
    return DeviceConfig(
        path=_optional_string(data.get("path"), "device.path"),
        name_contains=_optional_string(
            data.get("name_contains"), "device.name_contains"
        ),
        phys_contains=_optional_string(
            data.get("phys_contains"), "device.phys_contains"
        ),
    )


def _parse_behavior(raw: Any) -> BehaviorConfig:
    data = _mapping(raw, "behavior")
    trigger_on = str(data.get("trigger_on", "down"))
    if trigger_on not in {"down", "up"}:
        raise ConfigError("behavior.trigger_on must be 'down' or 'up'")
    return BehaviorConfig(
        exclusive_grab=bool(data.get("exclusive_grab", False)),
        trigger_on=trigger_on,
        repeat=bool(data.get("repeat", False)),
        debounce_ms=_non_negative_int(data.get("debounce_ms", 250), "debounce_ms"),
        command_timeout_sec=_positive_int(
            data.get("command_timeout_sec", 30), "command_timeout_sec"
        ),
        run_async=bool(data.get("run_async", False)),
        restore_on_exit=bool(data.get("restore_on_exit", True)),
    )


def _parse_logging(raw: Any) -> LoggingConfig:
    data = _mapping(raw, "logging")
    level = str(data.get("level", "INFO")).upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level not in valid_levels:
        raise ConfigError(f"logging.level must be one of {sorted(valid_levels)}")
    return LoggingConfig(level=level)


def _parse_commands(raw: Any) -> dict[str, CommandConfig]:
    data = _mapping(raw, "commands")
    commands: dict[str, CommandConfig] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not is_known_key_code(key):
            raise ConfigError(f"Unknown key code: {key}")
        item = _mapping(value, f"commands.{key}")
        command = item.get("command")
        if not isinstance(command, str) and not _string_list(command):
            raise ConfigError(f"commands.{key}.command must be a string or argv array")
        shell = bool(item.get("shell", False))
        if shell and not isinstance(command, str):
            raise ConfigError(f"commands.{key}: shell: true requires string command")
        has_whitespace = isinstance(command, str) and any(
            char.isspace() for char in command
        )
        if not shell and has_whitespace:
            raise ConfigError(
                f"commands.{key}: use array argv or set shell: true for commands "
                "with arguments"
            )
        commands[key] = CommandConfig(
            key=key,
            name=_optional_string(item.get("name"), f"commands.{key}.name"),
            command=command,
            shell=shell,
            timeout=_optional_positive_int(
                item.get("timeout"), f"commands.{key}.timeout"
            ),
            run_async=_optional_bool(
                item.get("run_async"), f"commands.{key}.run_async"
            ),
            debounce_ms=_optional_non_negative_int(
                item.get("debounce_ms"), f"commands.{key}.debounce_ms"
            ),
        )
    return commands


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a string or null")
    return value


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ConfigError(f"{name} must be a non-negative integer")
    return value


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, name)


def _optional_non_negative_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value, name)


def _optional_bool(value: Any, name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be a boolean")
    return value
