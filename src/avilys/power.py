"""Keep the computer from going to sleep while a download is running."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

# SetThreadExecutionState flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

# Ends by itself when Avilys ($0 is its process id) is gone, so a crash never
# leaves the computer unable to sleep.
WAIT_FOR_PARENT = 'while kill -0 "$0" 2>/dev/null; do sleep 15; done'


def system_env() -> dict[str, str]:
    """The environment for system programs. A packaged build points
    LD_LIBRARY_PATH at its own libraries, which system programs must not load."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def helper_command(pid: int) -> list[str] | None:
    """A program that blocks sleep for as long as it runs (Linux and macOS)."""
    if sys.platform == "darwin":
        return ["caffeinate", "-i", "-w", str(pid)] if shutil.which("caffeinate") else None
    if sys.platform.startswith("linux") and shutil.which("systemd-inhibit"):
        return ["systemd-inhibit", "--what=sleep:idle", "--who=Avilys", "--why=Downloading",
                "--mode=block", "sh", "-c", WAIT_FOR_PARENT, str(pid)]
    return None


class SleepBlocker:
    """Call set(True) while downloading and set(False) when idle."""

    def __init__(self) -> None:
        self.active = False
        self._proc: subprocess.Popen | None = None

    def set(self, on: bool) -> None:
        if on == self.active:
            return
        self.active = on
        try:
            if sys.platform == "win32":
                import ctypes

                flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
                ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
            elif on:
                cmd = helper_command(os.getpid())
                if cmd:
                    self._proc = subprocess.Popen(
                        cmd, env=system_env(), start_new_session=True, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                self._stop_helper()
        except (OSError, AttributeError, subprocess.SubprocessError):
            pass  # sleep can't be blocked here; downloading still works

    def _stop_helper(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, 15)  # the helper and the shell it started
        except (OSError, AttributeError):
            proc.terminate()
