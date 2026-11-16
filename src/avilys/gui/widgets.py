"""Small custom widgets: country flags, the speed graph and the pieces bar."""

from __future__ import annotations

from collections import deque
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import display
from ..i18n import tr
from . import theme

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
        label_w = p.fontMetrics().horizontalAdvance("1000.0 KiB/s") + 12
        plot = QRectF(label_w, 28, self.width() - label_w - 12, self.height() - 50)
        if plot.width() < 20 or plot.height() < 20:
            return

        # Grid and axis labels
        p.setPen(QPen(QColor(t["row_border"]), 1))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(t["muted"]))
            p.drawText(QRectF(0, y - 8, label_w - 8, 16), int(Qt.AlignRight | Qt.AlignVCenter),
                       f"{display.size(top * (4 - i) / 4)}/s" if i < 4 else "0")
            p.setPen(QPen(QColor(t["row_border"]), 1))
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(plot.left(), plot.bottom() + 4, plot.width(), 16),
                   int(Qt.AlignLeft | Qt.AlignTop), tr("5 min ago"))
        p.drawText(QRectF(plot.left(), plot.bottom() + 4, plot.width(), 16),
                   int(Qt.AlignRight | Qt.AlignTop), tr("now"))

        def points(values):
            n = len(values)
            return [QPointF(plot.left() + plot.width() * i / (n - 1),
                            plot.bottom() - plot.height() * min(v / top, 1.0)) for i, v in enumerate(values)]

        down_c, up_c = QColor(t["downloading"]), QColor(t["seeding"])
        pts = points(down)
        area = QPainterPath(QPointF(plot.left(), plot.bottom()))
        for pt in pts:
            area.lineTo(pt)
        area.lineTo(QPointF(plot.right(), plot.bottom()))
        fill = QColor(down_c)
        fill.setAlpha(60)
        p.fillPath(area, fill)
        p.setPen(QPen(down_c, 1.8))
        p.drawPolyline(pts)
        p.setPen(QPen(up_c, 1.8))
        p.drawPolyline(points(up))

        # Legend with current rates
        p.setFont(self.font())
        x = plot.left()
        for color, label in ((down_c, f"↓ {display.size(down[-1])}/s"), (up_c, f"↑ {display.size(up[-1])}/s")):
            p.fillRect(QRectF(x, 9, 10, 10), color)
            p.setPen(QColor(t["text"]))
            w = p.fontMetrics().horizontalAdvance(label)
            p.drawText(QRectF(x + 15, 4, w + 4, 20), int(Qt.AlignLeft | Qt.AlignVCenter), label)
            x += w + 40
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(plot.left(), 4, plot.width(), 20), int(Qt.AlignRight | Qt.AlignVCenter), self.title)
        p.end()


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
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
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
        p.setPen(QPen(QColor(t["border"]), 1))
        p.drawRect(r)
        p.end()
