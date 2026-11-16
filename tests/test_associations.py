"""Making Avilys the default app for magnet links and .torrent files."""

from __future__ import annotations

import os
import shutil
import sys

import pytest

from avilys.gui import associations as assoc


def test_describe():
    assert assoc.describe({"magnet": (True, "Avilys"), "torrent": (True, "Avilys")}) == \
        "Avilys opens magnet links and .torrent files."
    assert assoc.describe({"magnet": (False, "qbittorrent.exe"), "torrent": (False, None)}) == \
        "Magnet links open in qbittorrent.exe. .torrent files: no app set."


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("xdg-mime"),
                    reason="needs Linux with xdg-utils")
def test_linux_desktop_entry_and_defaults(tmp_path, monkeypatch):
    for var in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.setenv("APPIMAGE", "/opt/apps/Avilys 1.0.1.AppImage")

    before = assoc.status()
    assert before["magnet"][0] is False and before["torrent"][0] is False

    result = assoc.make_default(icon_png=b"\x89PNG fake")
    assert result.ok, result.message
    entry = (tmp_path / "xdg_data_home" / "applications" / "avilys.desktop").read_text()
    assert 'Exec="/opt/apps/Avilys 1.0.1.AppImage" %U' in entry  # the AppImage itself, quoted
    assert "MimeType=x-scheme-handler/magnet;application/x-bittorrent;" in entry
    assert (tmp_path / "xdg_data_home" / "icons" / "hicolor" / "256x256" / "apps" / "avilys.png").exists()
    assert assoc.status() == {"magnet": (True, "Avilys"), "torrent": (True, "Avilys")}


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("CI"),
                    reason="writes the real per-user registry: only on a throwaway CI machine")
def test_windows_registry_defaults():
    import winreg

    result = assoc.make_default()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Avilys.magnet\shell\open\command") as k:
        assert winreg.QueryValueEx(k, "")[0].endswith('"%1"')
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as k:
        assert winreg.QueryValueEx(k, "Avilys")[0] == r"Software\Avilys\Capabilities"
    # A fresh CI machine has no choice made in Settings, so the registry decides
    assert result.ok, result.message
    assert all(ours for ours, _ in assoc.status().values())
