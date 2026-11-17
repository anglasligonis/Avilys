"""Qt models for the torrent table, plus the filter proxy and progress bars."""

from __future__ import annotations

import libtorrent as lt
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import display
from ..engine import error_text, has_error, is_stopped, share_ratio
from ..i18n import N_, num, tr
from . import icons, theme

# Each category's colour comes from the current theme under this key.
STATE_KEYS = {
    N_("Downloading"): "downloading",
    N_("Seeding"): "seeding",
    N_("Finished"): "seeding",
    N_("Paused"): "paused",
    N_("Queued"): "paused",
    N_("Checking"): "checking",
    N_("Fetching metadata"): "checking",
    N_("Error"): "danger",
}


def state_color(cat: str, part: str = "") -> QColor:
    """part: "" for the mark (dots, bars), "_bg" for its tint, "_fg" for text on the tint."""
    return QColor(theme.current[STATE_KEYS[cat] + part])

# Sidebar filters: label -> categories it shows (None = everything).
# Labels and categories are English here; tr() translates them when shown.
FILTERS = {
    N_("All"): None,
    "Downloading": {"Downloading", "Checking"},
    "Seeding": {"Seeding", "Finished"},
    "Paused": {"Paused", "Queued"},
    "Fetching metadata": {"Fetching metadata"},
    N_("Errors"): {"Error"},
}
FILTER_ICONS = {"All": "all", "Downloading": "downloading", "Seeding": "seeding", "Paused": "paused",
                "Fetching metadata": "magnet", "Errors": "error"}
PLACEHOLDERS = {"–", "?", "0 / 0"}  # drawn faint so real numbers stand out

S = lt.torrent_status.states


def category(st: lt.torrent_status) -> str:
    if has_error(st):  # stopped by a problem such as a full disk
        return "Error"
    if st.flags & lt.torrent_flags.paused:
        return "Paused" if is_stopped(st) else "Queued"
    if st.state in (S.checking_files, S.checking_resume_data, S.queued_for_checking):
        return "Checking"
    if st.state == S.downloading_metadata:
        return "Fetching metadata"
    if st.state == S.seeding:
        return "Seeding"
    if st.state == S.finished:
        return "Finished"
    return "Downloading"


def key(st: lt.torrent_status) -> str:
    return str(st.info_hashes.get_best())


def dash(text: str) -> str:
    return "–" if text in ("-", "done") else text


SORT_ROLE = Qt.UserRole + 1
STATUS_ROLE = Qt.UserRole + 2  # the raw torrent_status


class TorrentModel(QAbstractTableModel):
    COLUMNS = [N_("Name"), N_("Size"), N_("Progress"), N_("Status"), N_("Down"), N_("Up"),
               N_("Seeds/Peers"), N_("Ratio"), N_("ETA")]
    PROGRESS, STATUS = 2, 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keys: list[str] = []
        self._status: dict[str, lt.torrent_status] = {}
        self._kinds: dict[str, str] = {}  # torrent -> its icon (see icons.file_kind)
        self.explain = error_text  # status -> why it stopped; the window plugs in the engine's

    # -- updating, keeping row identity so selection survives refreshes --
    def update(self, statuses: list[lt.torrent_status]) -> None:
        fresh = {key(st): st for st in statuses}
        for row in reversed(range(len(self._keys))):
            if self._keys[row] not in fresh:
                self.beginRemoveRows(QModelIndex(), row, row)
                self._status.pop(self._keys.pop(row), None)
                self.endRemoveRows()
        added = [k for k in fresh if k not in self._status]
        if added:
            first = len(self._keys)
            self.beginInsertRows(QModelIndex(), first, first + len(added) - 1)
            self._keys.extend(added)
            self._status.update({k: fresh[k] for k in added})
            self.endInsertRows()
        self._status.update(fresh)
        for k in set(self._kinds) - set(fresh):
            del self._kinds[k]
        for k, st in fresh.items():
            if self._kinds.get(k, "magnet") == "magnet":  # once known, a torrent's files don't change
                self._kinds[k] = self._kind(st)
        if self._keys:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._keys) - 1, len(self.COLUMNS) - 1))

    def key_at(self, row: int) -> str:
        return self._keys[row]

    def statuses(self) -> list[lt.torrent_status]:
        return [self._status[k] for k in self._keys]

    # -- Qt model API ----------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._keys)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return tr(self.COLUMNS[section])
            if role == Qt.TextAlignmentRole and section not in (0, 2, 3):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    @staticmethod
    def _kind(st: lt.torrent_status) -> str:
        if not st.has_metadata:
            return icons.file_kind(st.name, None)
        try:
            ti = st.handle.torrent_file()
        except RuntimeError:  # removed meanwhile
            ti = None
        return icons.file_kind(st.name, ti.num_files() if ti is not None else 1)

    def kind(self, row: int) -> str:
        return self._kinds.get(self._keys[row], "file")

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        st = self._status[self._keys[index.row()]]
        col = index.column()
        cat = category(st)
        if role == STATUS_ROLE:
            return st
        if role == Qt.DisplayRole:
            size = display.size(st.total_wanted) if st.has_metadata else "?"
            stopped = cat in ("Paused", "Queued", "Error")  # libtorrent's rates take a moment to fall to 0
            return [
                st.name or key(st)[:16],
                size,
                f"{num(st.progress * 100, 1)}%",
                tr(cat),
                "–" if stopped else dash(display.rate(st.download_payload_rate)),
                "–" if stopped else dash(display.rate(st.upload_payload_rate)),
                f"{st.num_seeds} / {st.num_peers}",
                num(share_ratio(st), 2),
                "–" if cat in ("Paused", "Seeding", "Finished", "Error") else dash(display.eta(st)),
            ][col]
        if role == SORT_ROLE:
            left = st.total_wanted - st.total_wanted_done
            eta = left / st.download_payload_rate if st.download_payload_rate > 0 else float("inf")
            return [
                (st.name or "").lower(), st.total_wanted, st.progress, cat,
                st.download_payload_rate, st.upload_payload_rate, st.num_peers,
                share_ratio(st), eta,
            ][col]
        if role == Qt.DecorationRole and col == 0:
            kind = "error" if cat == "Error" else self._kinds.get(key(st), "file")
            t, k = theme.current, STATE_KEYS[cat]
            return icons.tile(kind, t[k], t[k + "_bg"])
        if role == Qt.ForegroundRole and col not in (0, 2, 3):
            if self.data(index) in PLACEHOLDERS:
                return QColor(theme.current["faint"])
            return None
        if role == Qt.TextAlignmentRole and col not in (0, 2, 3):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole and cat == "Error":
            return f"{st.name}\n{self.explain(st)}"
        if role == Qt.ToolTipRole and col == 0:
            return st.name
        return None


class FilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.categories: set[str] | None = None
        self.setSortRole(SORT_ROLE)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(0)

    def set_categories(self, cats: set[str] | None) -> None:
        if hasattr(self, "beginFilterChange"):  # Qt 6.10+
            self.beginFilterChange()
            self.categories = cats
            self.endFilterChange()
        else:
            self.categories = cats
            self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if self.categories is not None:
            st = self.sourceModel().index(row, 3, parent).data(STATUS_ROLE)
            if st is None or category(st) not in self.categories:
                return False
        return super().filterAcceptsRow(row, parent)


def draw_background(delegate: QStyledItemDelegate, painter: QPainter, option, index) -> None:
    """The row's selection and border, drawn the normal way, without text or icon."""
    opt = option.__class__(option)
    delegate.initStyleOption(opt, index)
    opt.text = ""
    opt.icon = opt.icon.__class__()
    style = opt.widget.style() if opt.widget else None
    if style:
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)


class ProgressDelegate(QStyledItemDelegate):
    """A slim rounded bar with the percentage beside it, colored by state."""

    def paint(self, painter: QPainter, option, index):
        draw_background(self, painter, option, index)
        st = index.data(STATUS_ROLE)
        r = option.rect.adjusted(8, 0, -12, 0)
        text_w = 48
        bar = QRectF(r.left(), r.center().y() - 3, max(r.width() - text_w - 10, 10), 6)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.current["track"]))
        painter.drawRoundedRect(bar, 3, 3)
        if st is not None and st.progress > 0:
            fill = QRectF(bar)
            fill.setWidth(max(bar.width() * st.progress, 6))
            painter.setBrush(state_color(category(st)))
            painter.drawRoundedRect(fill, 3, 3)
        painter.setPen(QColor(theme.current["muted"]))
        painter.drawText(
            QRectF(bar.right() + 10, r.top(), text_w, r.height()),
            int(Qt.AlignRight | Qt.AlignVCenter),
            index.data(),
        )
        painter.restore()


class NameDelegate(QStyledItemDelegate):
    """The name cell: the torrent's icon tile, its name, and under it what it is
    doing ("Downloading", "Seeding"…) in the state's colour."""

    TILE = 24

    def paint(self, painter: QPainter, option, index):
        draw_background(self, painter, option, index)
        st = index.data(STATUS_ROLE)
        r = option.rect
        painter.save()
        tile = index.data(Qt.DecorationRole)
        if tile is not None:
            painter.drawPixmap(r.left() + 8, r.center().y() - self.TILE // 2 + 1, tile)
        x = r.left() + 8 + self.TILE + 10
        width = max(r.right() - x - 6, 10)
        name_font = QFont(option.font)
        name_font.setWeight(QFont.Medium)
        state_font = QFont(option.font)
        state_font.setPointSizeF(max(state_font.pointSizeF() - 1, 7))
        name_h = QFontMetricsF(name_font).height()
        state_h = QFontMetricsF(state_font).height()
        top = r.center().y() - (name_h + state_h) / 2 + 1
        painter.setFont(name_font)
        painter.setPen(option.palette.text().color())
        painter.drawText(QRectF(x, top, width, name_h), int(Qt.AlignLeft | Qt.AlignVCenter),
                         painter.fontMetrics().elidedText(index.data(), Qt.ElideMiddle, int(width)))
        if st is not None:
            cat = category(st)
            painter.setFont(state_font)
            painter.setPen(state_color(cat, "_fg"))
            painter.drawText(QRectF(x, top + name_h, width, state_h), int(Qt.AlignLeft | Qt.AlignVCenter),
                             painter.fontMetrics().elidedText(tr(cat), Qt.ElideRight, int(width)))
        painter.restore()


COUNT_ROLE = Qt.UserRole + 3  # a sidebar filter's number of torrents


class FilterDelegate(QStyledItemDelegate):
    """A sidebar row: icon, label and the number of torrents, right-aligned."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 34)

    def paint(self, painter: QPainter, option, index):
        t = theme.current
        name = index.data(Qt.UserRole)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        r = QRectF(option.rect).adjusted(0, 1, 0, -1)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if selected or hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t["filter_selected" if selected else "hover"]))
            painter.drawRoundedRect(r, 6, 6)
        count = index.data(COUNT_ROLE)
        if name == "Errors" and count:
            color = t["danger"]
        else:
            color = t["accent"] if selected else t["muted"]
        icons.paint(painter, FILTER_ICONS.get(name, "all"), QRectF(r.left() + 10, r.center().y() - 8, 16, 16), color)
        font = QFont(option.font)
        if selected:
            font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        number = "" if count is None else str(count)
        num_w = painter.fontMetrics().horizontalAdvance(number) + 4
        painter.setPen(QColor(t["text"]))
        painter.drawText(r.adjusted(36, 0, -(num_w + 14), 0), int(Qt.AlignLeft | Qt.AlignVCenter),
                         painter.fontMetrics().elidedText(index.data(), Qt.ElideRight, int(r.width() - num_w - 50)))
        painter.setPen(QColor(t["muted"]))
        painter.drawText(r.adjusted(0, 0, -12, 0), int(Qt.AlignRight | Qt.AlignVCenter), number)
        painter.restore()
