import threading
import time

import pytest

from radio_key_daemon.actions import ActionRunner, build_subprocess_args
from radio_key_daemon.config import BehaviorConfig, CommandConfig


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


def test_async_command_blocks_next_command_until_process_exits(monkeypatch):
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    runner = ActionRunner(BehaviorConfig(command_timeout_sec=1))

    class FakeProcess:
        args = ["slow"]
        pid = 123
        returncode = 0

        def communicate(self):
            first_started.set()
            release_first.wait(timeout=5)
            return "", ""

    def fake_popen(*_args, **_kwargs):
        return FakeProcess()

    def fake_run(*_args, **_kwargs):
        second_started.set()
        return type(
            "Completed",
            (),
            {"stdout": "", "stderr": "", "returncode": 0},
        )()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("subprocess.run", fake_run)

    async_command = CommandConfig(
        key="KEY_F12",
        command="slow",
        shell=False,
        run_async=True,
    )
    sync_command = CommandConfig(key="KEY_F11", command="fast", shell=False)

    assert runner.run(async_command) is None
    assert first_started.wait(timeout=1)

    thread = threading.Thread(target=lambda: runner.run(sync_command))
    thread.start()
    time.sleep(0.05)
    assert not second_started.is_set()

    release_first.set()
    thread.join(timeout=1)
    assert second_started.is_set()
