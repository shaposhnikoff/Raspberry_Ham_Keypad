from __future__ import annotations

import shlex

from radio_key_daemon.config import AppConfig, CommandConfig

KeyRow = tuple[str, ...]
KeySection = tuple[str, tuple[KeyRow, ...]]


KEYBOARD_LAYOUT: tuple[KeySection, ...] = (
    (
        "Function row",
        (
            (
                "KEY_ESC",
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
            ),
        ),
    ),
    (
        "Main keyboard",
        (
            (
                "KEY_GRAVE",
                "KEY_1",
                "KEY_2",
                "KEY_3",
                "KEY_4",
                "KEY_5",
                "KEY_6",
                "KEY_7",
                "KEY_8",
                "KEY_9",
                "KEY_0",
                "KEY_MINUS",
                "KEY_EQUAL",
                "KEY_BACKSPACE",
            ),
            (
                "KEY_TAB",
                "KEY_Q",
                "KEY_W",
                "KEY_E",
                "KEY_R",
                "KEY_T",
                "KEY_Y",
                "KEY_U",
                "KEY_I",
                "KEY_O",
                "KEY_P",
                "KEY_LEFTBRACE",
                "KEY_RIGHTBRACE",
                "KEY_BACKSLASH",
            ),
            (
                "KEY_CAPSLOCK",
                "KEY_A",
                "KEY_S",
                "KEY_D",
                "KEY_F",
                "KEY_G",
                "KEY_H",
                "KEY_J",
                "KEY_K",
                "KEY_L",
                "KEY_SEMICOLON",
                "KEY_APOSTROPHE",
                "KEY_ENTER",
            ),
            (
                "KEY_LEFTSHIFT",
                "KEY_Z",
                "KEY_X",
                "KEY_C",
                "KEY_V",
                "KEY_B",
                "KEY_N",
                "KEY_M",
                "KEY_COMMA",
                "KEY_DOT",
                "KEY_SLASH",
                "KEY_RIGHTSHIFT",
            ),
            (
                "KEY_LEFTCTRL",
                "KEY_LEFTALT",
                "KEY_SPACE",
                "KEY_RIGHTALT",
                "KEY_RIGHTCTRL",
            ),
        ),
    ),
    (
        "Navigation and keypad",
        (
            (
                "KEY_INSERT",
                "KEY_HOME",
                "KEY_PAGEUP",
                "KEY_NUMLOCK",
                "KEY_KPSLASH",
                "KEY_KPASTERISK",
                "KEY_KPMINUS",
            ),
            (
                "KEY_DELETE",
                "KEY_END",
                "KEY_PAGEDOWN",
                "KEY_KP7",
                "KEY_KP8",
                "KEY_KP9",
                "KEY_KPPLUS",
            ),
            (
                "KEY_UP",
                "KEY_KP4",
                "KEY_KP5",
                "KEY_KP6",
            ),
            (
                "KEY_LEFT",
                "KEY_DOWN",
                "KEY_RIGHT",
                "KEY_KP1",
                "KEY_KP2",
                "KEY_KP3",
                "KEY_KPENTER",
            ),
            (
                "KEY_KP0",
                "KEY_KPDOT",
            ),
        ),
    ),
)


def render_bindings(config: AppConfig) -> str:
    layout_keys = _layout_key_order()
    lines = [
        "Current key bindings",
        (
            "Behavior: "
            f"trigger_on={config.behavior.trigger_on} "
            f"repeat={str(config.behavior.repeat).lower()} "
            f"debounce_ms={config.behavior.debounce_ms} "
            f"run_async={str(config.behavior.run_async).lower()} "
            f"timeout={config.behavior.command_timeout_sec}s"
        ),
        "",
    ]

    for title, rows in KEYBOARD_LAYOUT:
        lines.append(title)
        for row in rows:
            cells = [_format_key_cell(key, config.commands.get(key)) for key in row]
            lines.append("  " + " ".join(cells))
        lines.append("")

    unplaced_keys = sorted(key for key in config.commands if key not in layout_keys)
    if unplaced_keys:
        lines.append("Other configured keys")
        lines.append(
            "  "
            + " ".join(
                _format_key_cell(key, config.commands[key]) for key in unplaced_keys
            )
        )
        lines.append("")

    lines.append("Configured commands")
    for command in _commands_in_display_order(config.commands, layout_keys):
        label = command.name or command.key
        lines.append(f"{command.key:<14} {label:<24} {_command_to_text(command)}")

    return "\n".join(lines)


def _layout_key_order() -> dict[str, int]:
    keys: list[str] = []
    for _, rows in KEYBOARD_LAYOUT:
        for row in rows:
            keys.extend(row)
    return {key: index for index, key in enumerate(keys)}


def _commands_in_display_order(
    commands: dict[str, CommandConfig], layout_keys: dict[str, int]
) -> list[CommandConfig]:
    return sorted(
        commands.values(),
        key=lambda command: (
            layout_keys.get(command.key, len(layout_keys)),
            command.key,
        ),
    )


def _format_key_cell(key: str, command: CommandConfig | None) -> str:
    label = _key_label(key)
    if command is None:
        return f"[{label}]"
    return f"[{label}: {command.name or command.key}]"


def _key_label(key: str) -> str:
    return key.removeprefix("KEY_")


def _command_to_text(command: CommandConfig) -> str:
    if isinstance(command.command, str):
        return command.command
    return shlex.join(command.command)
