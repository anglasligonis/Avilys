# PyInstaller spec for the desktop app. Build from the repo root:
#   python packaging/make_icons.py
#   pyinstaller packaging/avilys.spec --noconfirm
# Output: dist/avilys/ (a folder holding avilys or avilys.exe plus its libraries)
import sys
from pathlib import Path

HERE = Path(SPECPATH)  # noqa: F821  (defined by PyInstaller)
ROOT = HERE.parent
ICON = HERE / "build" / ("avilys.ico" if sys.platform == "win32" else "avilys.png")
GEOIP = HERE / "build" / "dbip-country-lite.mmdb"  # from packaging/fetch_geoip.py

datas = [(str(ROOT / "src" / "avilys" / "gui" / "flags"), "avilys/gui/flags")]
if GEOIP.exists():
    datas.append((str(GEOIP), "avilys/data"))

a = Analysis(  # noqa: F821
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=["avilys.translations.lt"],  # languages are loaded by name at run time
    excludes=["tkinter", "unittest", "pydoc", "pytest"],
)

# Don't ship the build machine's GTK: the GTK theme plugin drags in libgtk-3
# and friends, which clash with other distros' versions. Qt's own dialogs are used instead.
GTK = ("libqgtk3", "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk", "libcairo", "libpango", "libharfbuzz")
a.binaries = [b for b in a.binaries if not any(g in Path(b[0]).name for g in GTK)]

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="avilys",
    console=False,  # a window app: no console on Windows
    icon=str(ICON) if ICON.exists() and sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="avilys")  # noqa: F821
