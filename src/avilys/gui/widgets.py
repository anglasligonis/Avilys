"""Small custom widgets: country flags, the speed graph, the pieces bar and the disk meter."""

from __future__ import annotations

from collections import deque
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import display
from ..i18n import tr
from . import icons, theme

FLAGS = Path(__file__).resolve().parent / "flags"
HISTORY = 300  # seconds of speed history (5 minutes)


@lru_cache(maxsize=None)
def flag_icon(code: str) -> QIcon | None:
    """A 20x15 flag (drawn at 2x) for an ISO country code, or None."""
    path = FLAGS / f"{code.lower()}.png"
    if not path.is_file():
        return None
    pm = QPixmap(str(path))
    pm.setDevicePixelRatio(2.0)
    return QIcon(pm)


class SpeedHistory:
    """The last few minutes of download/upload rates, one sample a second."""

    def __init__(self, length: int = HISTORY):
        self.down: deque[float] = deque([0.0] * length, maxlen=length)
        self.up: deque[float] = deque([0.0] * length, maxlen=length)

    def add(self, down: float, up: float) -> None:
        self.down.append(down)
        self.up.append(up)


def nice_ceiling(value: float) -> float:
    """Round a rate up to a tidy axis maximum whose quarters are round too
    (e.g. 8 MiB/s -> 2, 4, 6, 8)."""
    if value <= 0:
        return 64 * 1024
    unit = 1.0
    while unit * 1024 <= value:
        unit *= 1024
    for step in (1, 2, 4, 8, 12, 16, 20, 40, 60, 80, 100, 200, 400, 600, 800, 1000, 1200):
        if step * unit >= value:
            return step * unit
    return value


class SpeedGraph(QWidget):
    """Download (filled) and upload (line) rates over the last five minutes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = SpeedHistory()
        self.title = tr("All torrents")
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def show_history(self, history: SpeedHistory, title: str) -> None:
        self.history, self.title = history, title
        self.update()

    def paintEvent(self, _):
        t = theme.current
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t["window"]))
        down, up = list(self.history.down), list(self.history.up)
        top = nice_ceiling(max(max(down), max(up)) * 1.1)

        small = QFont(self.font())
        small.setPointSizeF(max(small.pointSizeF() - 1, 7))
        p.setFont(small)
        label_w = p.fontMetrics().horizontalAdvance("1000 KiB/s") + 22
        plot = QRectF(label_w, 40, self.width() - label_w - 16, self.height() - 64)
        if plot.width() < 20 or plot.height() < 20:
            return

        # Grid and axis labels
        grid = QPen(QColor(t["border"]), 1, Qt.DashLine)
        grid.setDashPattern([3, 4])
        for i in range(5):
            y = round(plot.top() + plot.height() * i / 4) + 0.5
            p.setPen(QPen(QColor(t["border"]), 1) if i == 4 else grid)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(t["faint"]))
            p.drawText(QRectF(0, y - 8, label_w - 12, 16), int(Qt.AlignRight | Qt.AlignVCenter),
                       f"{tidy(display.size(top * (4 - i) / 4))}/s" if i < 4 else "0")
        p.drawText(QRectF(plot.left(), plot.bottom() + 6, plot.width(), 16),
                   int(Qt.AlignLeft | Qt.AlignTop), tr("5 min ago"))
        p.drawText(QRectF(plot.left(), plot.bottom() + 6, plot.width(), 16),
                   int(Qt.AlignRight | Qt.AlignTop), tr("now"))

        def points(values):
            n = len(values)
            return [QPointF(plot.left() + plot.width() * i / (n - 1),
                            plot.bottom() - plot.height() * min(v / top, 1.0)) for i, v in enumerate(values)]

        down_c, up_c = QColor(t["downloading"]), QColor(t["seeding"])
        pts = points(down)
        if max(down) > 0:
            area = QPainterPath(QPointF(plot.left(), plot.bottom()))
            for pt in pts:
                area.lineTo(pt)
            area.lineTo(QPointF(plot.right(), plot.bottom()))
            shade = QLinearGradient(0, plot.top(), 0, plot.bottom())
            for stop, alpha in ((0, 90), (1, 6)):
                c = QColor(down_c)
                c.setAlpha(alpha)
                shade.setColorAt(stop, c)
            p.fillPath(area, shade)
            p.setPen(QPen(down_c, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline(pts)
        if max(up) > 0:  # a flat line along the bottom says nothing
            p.setPen(QPen(up_c, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline(points(up))

        # Legend with current rates
        p.setFont(self.font())
        fm = p.fontMetrics()
        x = plot.left()
        for color, label in ((down_c, f"↓ {display.size(down[-1])}/s"), (up_c, f"↑ {display.size(up[-1])}/s")):
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QRectF(x, 16, 8, 8))
            p.setPen(QColor(t["text"]))
            w = fm.horizontalAdvance(label)
            p.drawText(QRectF(x + 14, 10, w + 4, 20), int(Qt.AlignLeft | Qt.AlignVCenter), label)
            x += w + 36
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(x, 10, plot.right() - x, 20), int(Qt.AlignRight | Qt.AlignVCenter),
                   fm.elidedText(self.title, Qt.ElideMiddle, int(plot.right() - x)))
        p.end()


def tidy(size: str) -> str:
    """'512.0 KiB' -> '512 KiB' for axis labels (the axis steps are round numbers)."""
    number, _, unit = size.partition(" ")
    for zero in (".0", ",0"):
        if number.endswith(zero):
            number = number[: -len(zero)]
    return f"{number} {unit}".strip()


class PieceBar(QWidget):
    """Which pieces we have, squeezed into the widget's width."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pieces: list[bool] = []
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(400, 28)

    def set_pieces(self, pieces: list[bool]) -> None:
        self.pieces = pieces
        self.update()

    def paintEvent(self, _):
        t = theme.current
        p = QPainter(self)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 5, 5)
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipPath(clip)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(r, QColor(t["track"]))
        n = len(self.pieces)
        if n:
            have, missing = QColor(t["downloading"]), QColor(t["track"])
            width = int(r.width())
            for x in range(width):
                lo, hi = x * n // width, max((x + 1) * n // width, x * n // width + 1)
                chunk = self.pieces[lo:hi]
                frac = sum(chunk) / len(chunk)
                if frac:
                    c = QColor(
                        int(missing.red() + (have.red() - missing.red()) * frac),
                        int(missing.green() + (have.green() - missing.green()) * frac),
                        int(missing.blue() + (have.blue() - missing.blue()) * frac))
                    p.fillRect(QRectF(r.left() + x, r.top(), 1, r.height()), c)
        p.end()


class DiskMeter(QWidget):
    """The download folder at the foot of the sidebar: how full its drive is."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path, self.used, self.free = "", None, ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(180, 64)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, 64)

    def set_usage(self, path: str, used: float | None, free: str) -> None:
        """used: the fraction of the drive in use, or None if unknown."""
        if (path, used, free) != (self.path, self.used, self.free):
            self.path, self.used, self.free = path, used, free
            self.update()

    def paintEvent(self, _):
        t = theme.current
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = p.fontMetrics()
        x, w = 18.0, self.width() - 36.0
        line = fm.height()
        icons.paint(p, "drive", QRectF(x, 6 + (line - 14) / 2, 14, 14), t["muted"])
        p.setPen(QColor(t["text"]))
        p.drawText(QRectF(x + 22, 6, w - 22, line), int(Qt.AlignLeft | Qt.AlignVCenter),
                   fm.elidedText(self.path, Qt.ElideLeft, int(w - 22)))
        bar = QRectF(x, 6 + line + 7, w, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["track"]))
        p.drawRoundedRect(bar, 2, 2)
        if self.used:
            fill = QRectF(bar)
            fill.setWidth(max(bar.width() * min(self.used, 1.0), 4))
            p.setBrush(QColor(t["danger"] if self.used > 0.95 else t["muted"]))
            p.drawRoundedRect(fill, 2, 2)
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(x, bar.bottom() + 5, w, line), int(Qt.AlignLeft | Qt.AlignVCenter),
                   fm.elidedText(self.free, Qt.ElideRight, int(w)))
        p.end()
