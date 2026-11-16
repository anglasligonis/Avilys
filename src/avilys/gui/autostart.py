"""Start Avilys when you sign in, hidden in the tray. Windows uses the
per-user Run key; Linux uses an autostart .desktop entry."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .associations import launch_command

FLAG = "--minimized"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Avilys"


def supported() -> bool:
    return sys.platform == "win32" or sys.platform.startswith("linux")


def command() -> list[str]:
    return [*launch_command(), FLAG]


def _desktop_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "autostart" / "avilys.desktop"


def _desktop_entry() -> str:
    exec_line = " ".join(f'"{p}"' if " " in p else p for p in command())
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Avilys",
        f"Exec={exec_line}",
        "Icon=avilys",
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        "",
    ])


def enabled() -> bool:
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, NAME)
            return True
        return _desktop_file().is_file()
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    """Raises OSError if the system refuses."""
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_WRITE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, " ".join(f'"{p}"' for p in command()))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
    elif on:
        path = _desktop_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_desktop_entry())
    else:
        _desktop_file().unlink(missing_ok=True)
