"""Line icons, kept here as SVG source so there are no image files to ship.

The shapes are from Lucide (https://lucide.dev), ISC License:
Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of
Feather (MIT). All other copyright (c) for Lucide are held by Lucide
Contributors 2022. Permission to use, copy, modify, and/or distribute this
software for any purpose with or without fee is hereby granted, provided that
the above copyright notice and this permission notice appear in all copies.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import PurePosixPath

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SHAPES = {
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
            '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "play": '<path fill="COLOR" d="M6 3.5v17a.5.5 0 0 0 .76.43l14-8.5a.5.5 0 0 0 0-.86l-14-8.5A.5.5 0 0 0 6 3.5z"/>',
    "pause": '<rect fill="COLOR" x="14" y="4" width="4" height="16" rx="1"/>'
             '<rect fill="COLOR" x="6" y="4" width="4" height="16" rx="1"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
             '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    "settings": '<path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "slow": '<path d="m12 14-4-3"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "drive": '<path d="M22 12H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6'
             'l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><path d="M6 16h.01M10 16h.01"/>',
    # Sidebar filters
    "all": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0'
           'l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
           '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "downloading": '<path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/>',
    "seeding": '<path d="m18 9-6-6-6 6"/><path d="M12 3v14"/><path d="M5 21h14"/>',
    "paused": '<circle cx="12" cy="12" r="10"/><path d="M10 15V9M14 15V9"/>',
    "magnet": '<path d="m6 15-4-4 6.75-6.77a7.79 7.79 0 0 1 11 11L13 22l-4-4 6.39-6.36a2.14 2.14 0 0 0-3-3L6 15"/>'
              '<path d="m5 8 4 4"/><path d="m12 15 4 4"/>',
    "error": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
             '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    # What a torrent holds
    "disc": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="2"/>',
    "video": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18M3 7.5h4M3 12h18M3 16.5h4'
             'M17 3v18M17 7.5h4M17 16.5h4"/>',
    "audio": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "archive": '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/>'
               '<path d="M10 12h4"/>',
    "image": '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/>'
             '<path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    "document": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
                '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8M16 17H8M10 9H8"/>',
    "app": '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4'
           'A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 8.7 5 8.7-5"/>'
           '<path d="m7.5 4.27 9 5.15"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4'
              'a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
}

KINDS = {
    "disc": {"iso", "img", "dmg", "vhd", "vhdx", "vmdk", "qcow2", "ova", "nrg"},
    "video": {"mp4", "mkv", "avi", "mov", "webm", "m4v", "wmv", "mpg", "mpeg", "ts", "flv", "ogv"},
    "audio": {"mp3", "flac", "ogg", "opus", "wav", "m4a", "aac", "wma", "alac", "ape"},
    "archive": {"zip", "rar", "7z", "tar", "gz", "tgz", "xz", "bz2", "zst", "lz", "cab"},
    "image": {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "svg", "heic", "raw"},
    "document": {"pdf", "epub", "mobi", "azw3", "djvu", "txt", "md", "doc", "docx", "odt", "rtf", "cbz", "cbr"},
    "app": {"exe", "msi", "deb", "rpm", "appimage", "apk", "pkg", "flatpak", "snap", "jar"},
}
_BY_EXT = {ext: kind for kind, exts in KINDS.items() for ext in exts}


def file_kind(name: str, num_files: int | None) -> str:
    """Which icon a torrent gets: 'magnet' while its file list is unknown,
    'folder' for several files, else by the single file's extension."""
    if num_files is None:
        return "magnet"
    if num_files > 1:
        return "folder"
    ext = PurePosixPath(name.lower()).suffix.lstrip(".")
    return _BY_EXT.get(ext, "file")


def _svg(name: str, color: str, stroke: float) -> QByteArray:
    return QByteArray(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        f'{SHAPES[name].replace("COLOR", color)}</svg>'.encode())  # COLOR: filled shapes


def paint(p: QPainter, name: str, rect: QRectF, color: str, stroke: float = 2.0) -> None:
    QSvgRenderer(_svg(name, QColor(color).name(), stroke)).render(p, rect)


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int, ratio: float = 2.0, stroke: float = 2.0) -> QPixmap:
    """`size` logical pixels square, drawn at `ratio` for sharp HiDPI output."""
    px = max(1, round(size * ratio))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    paint(p, name, QRectF(0, 0, px, px), color, stroke)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int = 16) -> QIcon:
    ic = QIcon()
    for ratio in (1.0, 2.0):
        ic.addPixmap(pixmap(name, color, size, ratio))
    return ic


@lru_cache(maxsize=256)
def tile(kind: str, fg: str, bg: str, size: int = 24, ratio: float = 2.0) -> QPixmap:
    """A rounded square in the torrent's state tint with its kind's icon on top."""
    px = round(size * ratio)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(QRectF(0, 0, px, px), 6 * ratio, 6 * ratio)
    inset = px * 0.22
    paint(p, kind, QRectF(inset, inset, px - 2 * inset, px - 2 * inset), fg, 2.2)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm
