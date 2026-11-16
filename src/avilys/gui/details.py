"""The bottom pane for the selected torrent: General, Files, Peers, Trackers,
Pieces and Speed."""

from __future__ import annotations

import time
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .. import display
from ..engine import UTP_SOCKET, share_ratio
from ..i18n import N_, num, tr, trn
from . import files
from .add_dialog import display_path, real_files
from .widgets import PieceBar, SpeedGraph, flag_icon

RIGHT = Qt.AlignRight | Qt.AlignVCenter

PRIORITIES = [(N_("Don't download"), 0), (N_("Normal"), 4), (N_("High"), 7)]
PRIORITY_NAMES = {0: N_("Skip"), 1: N_("Low"), 4: N_("Normal"), 7: N_("High")}

SOURCES = [(lt.peer_info.dht, "DHT"), (lt.peer_info.pex, "PEX"), (lt.peer_info.tracker, N_("Tracker")),
           (lt.peer_info.lsd, "LSD"), (lt.peer_info.resume_data, N_("Saved"))]
NO_TRACKERS = N_("(no trackers: peers come from DHT and PEX)")
GENERAL_FIELDS = [N_("Save path"), N_("Size"), N_("Downloaded"), N_("Uploaded"), N_("Ratio"), N_("Availability"),
                  N_("Pieces"), N_("Connections"), N_("Added"), N_("Active for"), N_("Seeding for"), N_("Info-hash")]


def make_table(headers: list[str], right_cols: set[int] = frozenset(), stretch: int = 0) -> QTableWidget:
    """headers: English, marked with N_(); translated here."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels([tr(h) for h in headers])
    t.verticalHeader().hide()
    t.setShowGrid(False)
    t.setAlternatingRowColors(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setWordWrap(False)
    t.verticalHeader().setDefaultSectionSize(26)
    h = t.horizontalHeader()
    h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    h.setSectionResizeMode(QHeaderView.ResizeToContents)
    h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    h.setMinimumSectionSize(70)
    t.right_cols = set(right_cols)
    return t


def fill(table: QTableWidget, rows: list[tuple]) -> None:
    """Update a table in place. A cell is text, or (text, icon)."""
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = table.item(r, c)
            if item is None:
                item = QTableWidgetItem()
                if c in table.right_cols:
                    item.setTextAlignment(RIGHT)
                table.setItem(r, c, item)
            icon = None
            if isinstance(value, tuple):
                value, icon = value
            text = str(value)
            if item.text() != text:
                item.setText(text)
                item.setIcon(icon or QIcon())


def duration(secs) -> str:
    if hasattr(secs, "total_seconds"):  # the bindings hand back timedelta
        secs = secs.total_seconds()
    if secs <= 0:
        return "–"
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return tr("{d}d {h}h", d=d, h=h) if d else tr("{h}h {m:02d}m", h=h, m=m) if h else tr("{m}m", m=m)


def tracker_status(t: dict) -> str:
    if t.get("updating"):
        return tr("Announcing…")
    if t.get("verified"):
        return tr("Working")
    if t.get("fails", 0):
        return trn("Not working ({n} failure)", "Not working ({n} failures)", t["fails"])
    return tr("Not contacted yet")


class DetailPane(QTabWidget):
    def __init__(self, engine, geo=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.geo = geo  # avilys.geoip.GeoIP, or None for no countries
        self.show_countries = True
        self.handle: lt.torrent_handle | None = None
        self._file_rows: list[int] = []  # Files tab row -> file index
        self.setDocumentMode(True)
        self._build_general()
        self.files = make_table([N_("Name"), N_("Size"), N_("Progress"), N_("Priority")], {1, 2})
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._files_menu)
        self.files.doubleClicked.connect(lambda index: self.open_file(index.row()))
        self.files.setToolTip(tr("Double-click a file to open it"))
        self.opener, self.revealer = files.open_path, files.reveal  # swappable in tests
        self.peers = make_table([N_("Country"), N_("Address"), N_("Client"), N_("Transport"), N_("Encryption"),
                                 N_("Source"), N_("Has"), N_("Down"), N_("Up")], {6, 7, 8}, stretch=2)
        self.peers.horizontalHeaderItem(0).setToolTip(tr("IP Geolocation by DB-IP (db-ip.com)"))
        self.trackers = make_table([N_("URL"), N_("Tier"), N_("Status"), N_("Seeds"), N_("Peers"), N_("Message")],
                                   {1, 3, 4})
        self.trackers.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trackers.customContextMenuRequested.connect(self._trackers_menu)
        self._build_pieces()
        self.speed = SpeedGraph()
        self.addTab(self.general, tr("General"))
        self.addTab(self.files, tr("Files"))
        self.addTab(self.peers, tr("Peers"))
        self.addTab(self.trackers, tr("Trackers"))
        self.addTab(self.pieces_page, tr("Pieces"))
        self.addTab(self.speed, tr("Speed"))
        self.currentChanged.connect(lambda _: self.refresh())

    def _build_general(self) -> None:
        self.general = QWidget()
        outer = QVBoxLayout(self.general)
        # Shown only when the torrent was stopped by an error
        self.error_row = QWidget()
        er = QHBoxLayout(self.error_row)
        er.setContentsMargins(0, 0, 0, 4)
        self.error = QLabel()
        self.error.setProperty("role", "warning")
        self.error.setWordWrap(True)
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.retry = QPushButton(tr("Try again"))
        er.addWidget(self.error, 1)
        er.addWidget(self.retry)
        self.error_row.hide()
        outer.addWidget(self.error_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        self.fields: dict[str, QLabel] = {}
        for i, name in enumerate(GENERAL_FIELDS):
            row, col = divmod(i, 3)
            label = QLabel(tr(name))
            label.setProperty("role", "muted")
            value = QLabel("–")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(label, row, col * 2)
            grid.addWidget(value, row, col * 2 + 1)
            self.fields[name] = value
        for c in (1, 3, 5):
            grid.setColumnStretch(c, 1)
        outer.addLayout(grid)
        magnet_row = QHBoxLayout()
        lbl = QLabel(tr("Magnet link"))
        lbl.setProperty("role", "muted")
        self.magnet = QLineEdit()
        self.magnet.setReadOnly(True)
        copy = QPushButton(tr("Copy"))
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.magnet.text()))
        magnet_row.addWidget(lbl)
        magnet_row.addWidget(self.magnet, 1)
        magnet_row.addWidget(copy)
        outer.addLayout(magnet_row)
        outer.addStretch(1)

    def _build_pieces(self) -> None:
        self.pieces_page = QWidget()
        layout = QVBoxLayout(self.pieces_page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        self.piece_bar = PieceBar()
        self.piece_info = QLabel("–")
        self.piece_info.setProperty("role", "muted")
        layout.addWidget(self.piece_bar)
        layout.addWidget(self.piece_info)
        layout.addStretch(1)

    # -- refresh ----------------------------------------------------------
    def show_torrent(self, handle: lt.torrent_handle | None) -> None:
        self.handle = handle
        if handle is None:
            for t in (self.files, self.peers, self.trackers):
                t.setRowCount(0)
            for v in self.fields.values():
                v.setText("–")
            self.magnet.clear()
            self.error_row.hide()
            self.piece_bar.set_pieces([])
            self.piece_info.setText("–")
        self.refresh()

    def refresh(self) -> None:
        h = self.handle
        if h is None or not h.is_valid():
            return
        page = self.currentWidget()
        if page is self.speed:
            return  # the window feeds the graph
        st = h.status(lt.status_flags_t.query_pieces) if page is self.pieces_page else h.status()
        if page is self.general:
            self._general(h, st)
        elif page is self.files:
            self._files(h, st)
        elif page is self.peers:
            self._peers(h)
        elif page is self.trackers:
            self._trackers(h)
        elif page is self.pieces_page:
            self._pieces(h, st)
        self.setTabText(2, tr("Peers ({n})", n=st.num_peers))

    def _general(self, h, st) -> None:
        ti = h.torrent_file() if st.has_metadata else None
        f = self.fields
        problem = self.engine.error_text(st)
        if problem:
            name = self.engine.error_file(st)
            if name:
                problem += f" ({name})"
            self.error.setText(tr("Stopped: {problem}. Fix the problem, then try again.", problem=problem))
        self.error_row.setVisible(bool(problem))
        dest = self.engine.destination(h)
        where = st.save_path if str(dest) == st.save_path else tr(
            "{folder} (moves to {destination} when finished)", folder=st.save_path, destination=dest)
        f["Save path"].setText(where)
        f["Save path"].setToolTip(where)  # long paths don't fit
        f["Size"].setText(display.size(st.total_wanted) if st.has_metadata else tr("unknown yet"))
        f["Downloaded"].setText(tr("{size} (all time {total})", size=display.size(st.total_wanted_done),
                                   total=display.size(st.all_time_download)))
        f["Uploaded"].setText(display.size(st.all_time_upload))
        f["Ratio"].setText(num(share_ratio(st), 2))
        f["Availability"].setText(num(st.distributed_copies, 2) if st.distributed_copies >= 0 else "–")
        f["Pieces"].setText(f"{st.num_pieces} / {ti.num_pieces()} × {display.size(ti.piece_length())}" if ti else "–")
        f["Connections"].setText(trn("{total} ({n} seed)", "{total} ({n} seeds)", st.num_seeds,
                                     total=st.num_connections))
        f["Added"].setText(time.strftime("%Y-%m-%d %H:%M", time.localtime(st.added_time)) if st.added_time else "–")
        f["Active for"].setText(duration(st.active_duration))
        f["Seeding for"].setText(duration(st.seeding_duration))
        f["Info-hash"].setText(str(st.info_hashes.get_best()))
        uri = lt.make_magnet_uri(h)
        if self.magnet.text() != uri:
            self.magnet.setText(uri)

    def _files(self, h, st) -> None:
        if not st.has_metadata:
            fill(self.files, [(tr("(waiting for metadata)"), "", "", "")])
            return
        ti = h.torrent_file()
        fs = ti.files()
        done = h.file_progress()
        prios = h.get_file_priorities()
        self._file_rows = sorted(real_files(ti), key=lambda i: display_path(ti, i).lower())
        rows = []
        for i in self._file_rows:
            size = fs.file_size(i)
            pct = done[i] / size * 100 if size else 100.0
            prio = PRIORITY_NAMES.get(int(prios[i]))
            rows.append((display_path(ti, i), display.size(size), f"{num(pct, 1)}%",
                         tr(prio) if prio else str(prios[i])))
        fill(self.files, rows)

    def _files_menu(self, pos) -> None:
        h = self.handle
        if h is None or not h.is_valid() or not h.status().has_metadata:
            return
        rows = sorted({i.row() for i in self.files.selectedIndexes()})
        if not rows:
            return
        menu = QMenu(self)
        open_act = menu.addAction(tr("Open"), lambda: self.open_file(rows[0]))
        font = open_act.font()
        font.setBold(True)  # the double-click action
        open_act.setFont(font)
        menu.addAction(tr("Show in folder"), lambda: self.show_in_folder(rows[0]))
        menu.addSeparator()
        for label, prio in PRIORITIES:
            act = QAction(tr(label), menu)
            act.triggered.connect(lambda _=False, p=prio: self._set_priority(rows, p))
            menu.addAction(act)
        menu.exec(self.files.viewport().mapToGlobal(pos))

    def file_path(self, row: int) -> Path | None:
        """Where the file shown in a Files-tab row lives on disk."""
        h = self.handle
        if h is None or not h.is_valid() or not 0 <= row < len(self._file_rows):
            return None
        st = h.status()
        if not st.has_metadata:
            return None
        return Path(st.save_path) / h.torrent_file().files().file_path(self._file_rows[row])

    def open_file(self, row: int) -> None:
        path = self.file_path(row)
        if path is None:
            return
        if not path.exists():
            skipped = self.handle.get_file_priorities()[self._file_rows[row]] == 0
            QMessageBox.information(
                self, tr("Not downloaded yet"),
                tr("“{name}” is set to “Don't download”.", name=path.name) if skipped else
                tr("“{name}” hasn't been downloaded yet.", name=path.name))
            return
        self.opener(path)

    def show_in_folder(self, row: int) -> None:
        path = self.file_path(row)
        if path is not None:
            self.revealer(path)

    def _set_priority(self, rows: list[int], prio: int) -> None:
        for r in rows:
            if r < len(self._file_rows):
                self.handle.file_priority(self._file_rows[r], prio)
        self.engine.save_resume(self.handle)
        self.refresh()

    def country_cell(self, ip: str):
        if not (self.show_countries and self.geo is not None):
            return ""
        found = self.geo.country(ip)
        if not found:
            return ""
        code, name = found
        return (name, flag_icon(code))

    def _peers(self, h) -> None:
        rows = []
        for p in sorted(h.get_peer_info(), key=lambda p: -p.payload_down_speed):
            flags = int(p.flags)
            if flags & int(lt.peer_info.rc4_encrypted):
                enc = "RC4"
            elif flags & int(lt.peer_info.plaintext_encrypted):
                enc = tr("Header only")
            else:
                enc = tr("Plaintext")
            src = ", ".join(tr(name) for bit, name in SOURCES if int(p.source) & int(bit)) or tr("Incoming")
            client = p.client.decode(errors="replace") if isinstance(p.client, bytes) else p.client
            rows.append((
                self.country_cell(p.ip[0]), f"{p.ip[0]}:{p.ip[1]}", client or "?",
                "µTP" if flags & UTP_SOCKET else "TCP", enc, src,
                f"{p.progress * 100:.0f}%", dash_rate(p.payload_down_speed), dash_rate(p.payload_up_speed),
            ))
        fill(self.peers, rows)

    def _trackers(self, h) -> None:
        rows = []
        for t in h.trackers():
            seeds = t.get("scrape_complete", -1)
            peers = t.get("scrape_incomplete", -1)
            rows.append((t["url"], t.get("tier", 0), tracker_status(t),
                         seeds if seeds >= 0 else "–", peers if peers >= 0 else "–", t.get("message", "")))
        fill(self.trackers, rows or [(tr(NO_TRACKERS), "", "", "", "", "")])

    def _trackers_menu(self, pos) -> None:
        h = self.handle
        if h is None or not h.is_valid():
            return
        urls = [self.trackers.item(i.row(), 0).text() for i in self.trackers.selectionModel().selectedRows()]
        urls = [u for u in urls if u != tr(NO_TRACKERS)]
        menu = QMenu(self)
        menu.addAction(tr("Add tracker…"), self.ask_add_tracker)
        remove = menu.addAction(
            tr("Remove tracker") if len(urls) < 2 else trn("Remove {n} tracker", "Remove {n} trackers", len(urls)),
            lambda: self.remove_trackers(urls))
        remove.setEnabled(bool(urls))
        menu.addSeparator()
        menu.addAction(tr("Announce now"), lambda: (h.force_reannounce(), self.refresh()))
        menu.exec(self.trackers.viewport().mapToGlobal(pos))

    def ask_add_tracker(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, tr("Add trackers"), tr("Tracker addresses, one per line:"))
        if not ok:
            return
        errors = []
        for line in filter(None, (l.strip() for l in text.splitlines())):
            try:
                self.engine.add_tracker(self.handle, line)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            QMessageBox.warning(self, tr("Couldn't add"), "\n".join(errors))
        self.refresh()

    def remove_trackers(self, urls: list[str]) -> None:
        for url in urls:
            self.engine.remove_tracker(self.handle, url)
        self.refresh()

    def _pieces(self, h, st) -> None:
        if not st.has_metadata:
            self.piece_bar.set_pieces([])
            self.piece_info.setText(tr("Waiting for the file list from peers…"))
            return
        ti = h.torrent_file()
        pieces = list(st.pieces)
        self.piece_bar.set_pieces(pieces)
        have = sum(pieces)
        text = tr("{have} of {total} pieces · {size} each", have=have, total=len(pieces),
                  size=display.size(ti.piece_length()))
        if st.distributed_copies >= 0:
            text += " · " + tr("{copies} copies available in the swarm", copies=num(st.distributed_copies, 2))
        self.piece_info.setText(text)


def dash_rate(n: float) -> str:
    return display.rate(n) if n > 0 else "–"
