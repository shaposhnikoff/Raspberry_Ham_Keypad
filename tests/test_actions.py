import pytest

from radio_key_daemon.actions import build_subprocess_args
from radio_key_daemon.config import CommandConfig


def test_builds_shell_command_from_string():
    command = CommandConfig(key="KEY_F12", command="echo hello", shell=True)

    popen_args = build_subprocess_args(command)

    assert popen_args.args == "echo hello"
    assert popen_args.shell is True


def test_builds_argv_command_from_list():
    command = CommandConfig(
        key="KEY_F12",
        command=["/home/pi/safe_tune.py", "--fast"],
        shell=False,
    )

    popen_args = build_subprocess_args(command)

    assert popen_args.args == ["/home/pi/safe_tune.py", "--fast"]
    assert popen_args.shell is False


def test_rejects_shell_true_with_argv():
    command = CommandConfig(key="KEY_F12", command=["echo", "hello"], shell=True)

    with pytest.raises(ValueError, match="shell commands must be strings"):
        build_subprocess_args(command)
