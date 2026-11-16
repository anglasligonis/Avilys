"""Make Avilys the default app for magnet links and .torrent files, and
report whether it is. Windows uses the per-user registry (no admin rights);
Linux uses a .desktop launcher plus xdg-mime."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..i18n import N_, tr

KINDS = {"magnet": N_("magnet links"), "torrent": N_(".torrent files")}
KINDS_OPEN_IN = {"magnet": N_("Magnet links open in {app}."), "torrent": N_(".torrent files open in {app}.")}
KINDS_NO_APP = {"magnet": N_("Magnet links: no app set."), "torrent": N_(".torrent files: no app set.")}
MIME = {"magnet": "x-scheme-handler/magnet", "torrent": "application/x-bittorrent"}
DESKTOP_ID = "avilys.desktop"
WINDOWS_SETTINGS = "ms-settings:defaultapps?registeredAppUser=Avilys"


@dataclass
class Result:
    ok: bool                      # Avilys is now the default for everything asked
    needs_settings: bool = False  # Windows wants the user to confirm in Settings
    message: str = ""


def launch_command() -> list[str]:
    """How the OS should start Avilys with a link or file."""
    if os.environ.get("APPIMAGE"):  # running from an AppImage: point at the AppImage itself
        return [os.environ["APPIMAGE"]]
    if getattr(sys, "frozen", False):  # PyInstaller build
        return [sys.executable]
    script = shutil.which("avilys-gui")
    if script:
        return [script]
    python = sys.executable
    if sys.platform == "win32":  # no console window
        pythonw = Path(python).with_name("pythonw.exe")
        python = str(pythonw) if pythonw.exists() else python
    return [python, "-m", "avilys.gui.app"]


# -- Windows ------------------------------------------------------------------------
def _win_command() -> str:
    return " ".join(f'"{part}"' for part in launch_command()) + ' "%1"'


def _win_write(kinds) -> None:
    import winreg

    exe = launch_command()[0]
    command = _win_command()

    def put(path: str, values: dict) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
            for name, value in values.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    classes = r"Software\Classes"
    # ProgIDs, plus "Capabilities" so Avilys is listed in Settings > Default apps
    put(rf"{classes}\Avilys.torrent", {"": "BitTorrent file"})
    put(rf"{classes}\Avilys.torrent\DefaultIcon", {"": f"{exe},0"})
    put(rf"{classes}\Avilys.torrent\shell\open\command", {"": command})
    put(rf"{classes}\Avilys.magnet", {"": "URL:Magnet link", "URL Protocol": ""})
    put(rf"{classes}\Avilys.magnet\DefaultIcon", {"": f"{exe},0"})
    put(rf"{classes}\Avilys.magnet\shell\open\command", {"": command})
    put(r"Software\Avilys\Capabilities", {
        "ApplicationName": "Avilys",
        "ApplicationDescription": "A BitTorrent client",
    })
    put(r"Software\Avilys\Capabilities\FileAssociations", {".torrent": "Avilys.torrent"})
    put(r"Software\Avilys\Capabilities\URLAssociations", {"magnet": "Avilys.magnet"})
    put(r"Software\RegisteredApplications", {"Avilys": r"Software\Avilys\Capabilities"})
    # The classic defaults, used when the user hasn't picked an app in Settings
    if "torrent" in kinds:
        put(rf"{classes}\.torrent", {"": "Avilys.torrent"})
        put(rf"{classes}\.torrent\OpenWithProgids", {"Avilys.torrent": ""})
    if "magnet" in kinds:
        put(rf"{classes}\magnet", {"": "URL:Magnet link", "URL Protocol": ""})
        put(rf"{classes}\magnet\DefaultIcon", {"": f"{exe},0"})
        put(rf"{classes}\magnet\shell\open\command", {"": command})
    try:  # tell Explorer associations changed
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def _win_handler(kind: str) -> str | None:
    """The program Windows actually uses (respects choices made in Settings)."""
    import ctypes
    from ctypes import wintypes

    assoc = ".torrent" if kind == "torrent" else "magnet"
    size = wintypes.DWORD(1024)
    buf = ctypes.create_unicode_buffer(size.value)
    ASSOCSTR_EXECUTABLE = 2
    hr = ctypes.windll.shlwapi.AssocQueryStringW(0, ASSOCSTR_EXECUTABLE, assoc, "open", buf, ctypes.byref(size))
    return buf.value if hr == 0 and buf.value else None


def _same_program(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a.lower() == b.lower()


# -- Linux ---------------------------------------------------------------------------
def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _desktop_entry() -> str:
    exec_line = " ".join(f'"{p}"' if " " in p else p for p in launch_command())
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Avilys",
        "GenericName=BitTorrent Client",
        "GenericName[lt]=BitTorrent klientas",
        "Comment=Download and share files with BitTorrent",
        "Comment[lt]=Atsisiųskite ir dalinkitės failais per BitTorrent",
        f"Exec={exec_line} %U",
        "Icon=avilys",
        "Terminal=false",
        "Categories=Network;FileTransfer;P2P;Qt;",
        "MimeType=x-scheme-handler/magnet;application/x-bittorrent;",
        "StartupWMClass=avilys",
        "",
    ])


def _linux_write(kinds, icon_png: bytes | None) -> None:
    apps = _data_home() / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / DESKTOP_ID).write_text(_desktop_entry())
    if icon_png:
        icons = _data_home() / "icons" / "hicolor" / "256x256" / "apps"
        icons.mkdir(parents=True, exist_ok=True)
        (icons / "avilys.png").write_bytes(icon_png)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps)], capture_output=True, timeout=10)
    subprocess.run(["xdg-mime", "default", DESKTOP_ID, *(MIME[k] for k in kinds)],
                   capture_output=True, timeout=10, check=True)


def _linux_handler(kind: str) -> str | None:
    try:
        out = subprocess.run(["xdg-mime", "query", "default", MIME[kind]],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


# -- public ------------------------------------------------------------------------
def supported() -> bool:
    return sys.platform == "win32" or (sys.platform.startswith("linux") and shutil.which("xdg-mime") is not None)


def status() -> dict[str, tuple[bool, str | None]]:
    """For each kind: (is Avilys the default?, the current handler's name)."""
    out = {}
    for kind in KINDS:
        try:
            if sys.platform == "win32":
                handler = _win_handler(kind)
                ours = handler is not None and _same_program(handler, launch_command()[0])
                name = Path(handler).name if handler else None
            else:
                handler = _linux_handler(kind)
                ours = handler == DESKTOP_ID
                name = handler.removesuffix(".desktop") if handler else None
        except Exception:
            ours, name = False, None
        out[kind] = (ours, "Avilys" if ours else name)
    return out


def describe(st: dict[str, tuple[bool, str | None]]) -> str:
    """One sentence for Settings: who opens what."""
    if all(ours for ours, _ in st.values()):
        return tr("Avilys opens magnet links and .torrent files.")
    parts = []
    for kind, (ours, name) in st.items():
        parts.append(tr(KINDS_OPEN_IN[kind], app=name) if name else tr(KINDS_NO_APP[kind]))
    return " ".join(parts)


def make_default(kinds=tuple(KINDS), icon_png: bytes | None = None) -> Result:
    if not supported():
        return Result(False, message=tr("Setting the default app isn't supported on this system."))
    try:
        if sys.platform == "win32":
            _win_write(kinds)
        else:
            _linux_write(kinds, icon_png)
    except (OSError, subprocess.SubprocessError) as e:
        return Result(False, message=tr("Couldn't register Avilys: {error}", error=e))
    now = status()
    joined = lambda names: tr(" and ").join(names)  # noqa: E731
    missing = [tr(KINDS[k]) for k in kinds if not now[k][0]]
    if not missing:
        return Result(True, message=tr("Avilys now opens {kinds}.", kinds=joined(tr(KINDS[k]) for k in kinds)))
    if sys.platform == "win32":
        # A choice made in Windows Settings wins over the registry; only the user can change it.
        labels = {"magnet": "MAGNET", "torrent": ".torrent"}
        todo = [labels[k] for k in kinds if not now[k][0]]
        return Result(False, needs_settings=True, message=tr(
            "Windows asks you to confirm this yourself. In the Settings page that opens, "
            "choose Avilys for {kinds}.", kinds=joined(f"“{t}”" for t in todo)))
    return Result(False, message=tr("Your desktop didn't accept the change for {kinds}.", kinds=joined(missing)))
