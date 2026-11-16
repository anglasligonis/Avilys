"""Entry point for the packaged desktop app (PyInstaller)."""

import sys

from avilys.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
