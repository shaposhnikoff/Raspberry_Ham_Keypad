from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass

from radio_key_daemon.config import BehaviorConfig, CommandConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubprocessArgs:
    args: str | list[str]
    shell: bool


def build_subprocess_args(command: CommandConfig) -> SubprocessArgs:
    if command.shell:
        if not isinstance(command.command, str):
            raise ValueError("shell commands must be strings")
        return SubprocessArgs(args=command.command, shell=True)
    if isinstance(command.command, str):
        return SubprocessArgs(args=[command.command], shell=False)
    return SubprocessArgs(args=command.command, shell=False)


class ActionRunner:
    def __init__(self, behavior: BehaviorConfig, *, dry_run: bool = False) -> None:
        self._behavior = behavior
        self._dry_run = dry_run
        self._lock = threading.Lock()

    def run(self, command: CommandConfig) -> int | None:
        timeout = command.timeout or self._behavior.command_timeout_sec
        run_async = (
            self._behavior.run_async if command.run_async is None else command.run_async
        )
        args = build_subprocess_args(command)
        label = command.name or command.key
        async_started = False
        self._lock.acquire()
        if self._dry_run:
            try:
                logger.info("Dry run: would execute %s: %r", label, args.args)
                return 0
            finally:
                self._lock.release()
        try:
            if run_async:
                process = subprocess.Popen(  # noqa: S603
                    args.args,
                    # shell=True is enabled only when trusted YAML opts in.
                    shell=args.shell,  # nosec B602
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                logger.info("Started async command %s with pid %s", label, process.pid)
                waiter = threading.Thread(
                    target=self._wait_for_async_process,
                    args=(label, process),
                    daemon=True,
                )
                waiter.start()
                async_started = True
                return None
            completed = subprocess.run(  # noqa: S603
                args.args,
                # shell=True is enabled only when trusted YAML opts in.
                shell=args.shell,  # nosec B602
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.error("Command timed out after %ss: %s", timeout, label)
            return 124
        except OSError as exc:
            logger.error("Could not execute command %s: %s", label, exc)
            return 127
        finally:
            if not async_started:
                self._lock.release()
        _log_completed_process(label, completed)
        return completed.returncode

    def _wait_for_async_process(
        self, label: str, process: subprocess.Popen[str]
    ) -> None:
        try:
            stdout, stderr = process.communicate()
            completed = subprocess.CompletedProcess(
                process.args,
                process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            _log_completed_process(label, completed)
        finally:
            self._lock.release()


def _log_completed_process(
    label: str, completed: subprocess.CompletedProcess[str]
) -> None:
    if completed.stdout:
        logger.info("%s stdout: %s", label, completed.stdout.rstrip())
    if completed.stderr:
        logger.warning("%s stderr: %s", label, completed.stderr.rstrip())
    if completed.returncode == 0:
        logger.info("Command completed successfully: %s", label)
    else:
        logger.error(
            "Command failed with exit code %s: %s", completed.returncode, label
        )
