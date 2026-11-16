"""Open a downloaded file, or show it selected in the system file manager."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_path(path: Path) -> bool:
    """Open a file or folder with its default application."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str) -> bool:
    """Open a web page in the default browser."""
    return QDesktopServices.openUrl(QUrl(url))


def reveal(path: Path) -> bool:
    """Open the folder holding `path`, with the item selected where the
    platform allows it. Falls back to just opening the folder."""
    path = Path(path)
    if not path.exists():
        return open_path(next((p for p in path.parents if p.exists()), path.parent))
    try:
        if sys.platform == "win32":
            # explorer's /select needs the comma form and returns 1 even on success
            subprocess.Popen(f'explorer /select,"{path}"')
            return True
        if sys.platform.startswith("linux"):
            # Asks the running file manager (Nautilus, Dolphin, Nemo, Caja…) to select it
            done = subprocess.run(
                ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.FileManager1",
                 "--type=method_call", "/org/freedesktop/FileManager1",
                 "org.freedesktop.FileManager1.ShowItems",
                 f"array:string:{QUrl.fromLocalFile(str(path)).toString()}", "string:"],
                capture_output=True, timeout=3)
            if done.returncode == 0:
                return True
    except (OSError, subprocess.SubprocessError):
        pass
    return open_path(path.parent if path.is_file() else path)
