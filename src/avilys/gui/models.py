"""Qt models for the torrent table, plus the filter proxy and progress bars."""

from __future__ import annotations

import libtorrent as lt
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import display
from ..engine import error_text, has_error, is_stopped, share_ratio
from ..i18n import N_, num, tr
from . import theme

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


def state_color(cat: str) -> QColor:
    return QColor(theme.current[STATE_KEYS[cat]])

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
    PROGRESS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keys: list[str] = []
        self._status: dict[str, lt.torrent_status] = {}
        self._icons: dict[str, QIcon] = {}
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

    def _dot(self, cat: str) -> QIcon:
        cache_key = f"{theme.current_name}:{cat}"
        if cache_key not in self._icons:
            pm = QPixmap(10, 10)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(state_color(cat))
            p.setPen(Qt.NoPen)
            p.drawEllipse(1, 1, 8, 8)
            p.end()
            self._icons[cache_key] = QIcon(pm)
        return self._icons[cache_key]

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
            return [
                st.name or key(st)[:16],
                size,
                f"{num(st.progress * 100, 1)}%",
                tr(cat),
                dash(display.rate(st.download_payload_rate)),
                dash(display.rate(st.upload_payload_rate)),
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
        if role == Qt.DecorationRole and col == 3:
            return self._dot(cat)
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


class ProgressDelegate(QStyledItemDelegate):
    """A slim rounded bar with the percentage beside it, colored by state."""

    def paint(self, painter: QPainter, option, index):
        # Draw the selection/background the normal way, without text.
        opt = option.__class__(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        st = index.data(STATUS_ROLE)
        r = option.rect.adjusted(8, 0, -8, 0)
        text_w = 48
        bar = QRectF(r.left(), r.center().y() - 3.5, max(r.width() - text_w - 8, 10), 7)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.current["track"]))
        painter.drawRoundedRect(bar, 3.5, 3.5)
        if st is not None and st.progress > 0:
            fill = QRectF(bar)
            fill.setWidth(max(bar.width() * st.progress, 7))
            painter.setBrush(state_color(category(st)))
            painter.drawRoundedRect(fill, 3.5, 3.5)
        painter.setPen(option.palette.text().color())
        painter.drawText(
            QRectF(bar.right() + 8, r.top(), text_w, r.height()),
            int(Qt.AlignRight | Qt.AlignVCenter),
            index.data(),
        )
        painter.restore()
