"""Render the app icon (drawn in code, see avilys.gui.app.logo_pixmap) to
packaging/build/avilys.png and a multi-size packaging/build/avilys.ico."""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from avilys.gui.app import logo_pixmap  # noqa: E402

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    logo_pixmap(size).save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path) -> None:
    """ICO with PNG-compressed entries (supported since Windows Vista)."""
    images = [png_bytes(s) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, img in zip(ICO_SIZES, images):
        dim = 0 if size >= 256 else size  # 0 means 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    path.write_bytes(header + entries + b"".join(images))


def main() -> int:
    QApplication.instance() or QApplication(sys.argv[:1])
    out = Path(__file__).resolve().parent / "build"
    out.mkdir(exist_ok=True)
    (out / "avilys.png").write_bytes(png_bytes(256))
    write_ico(out / "avilys.ico")
    print(f"wrote {out / 'avilys.png'} and {out / 'avilys.ico'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
