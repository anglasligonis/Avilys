"""Main window: toolbar, status filters, torrent table, detail pane, status bar,
plus the tray icon, finished-download notifications and light/dark themes."""

from __future__ import annotations

import base64
import dataclasses
import json
import os
import shutil
import sys
import time
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import QByteArray, QLocale, QPointF, QSize, Qt, QTimer, QTranslator
from PySide6.QtGui import (
    QAction, QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QSizePolicy, QSplitter, QSystemTrayIcon, QTableView, QToolBar,
    QToolButton, QVBoxLayout, QWidget, QHBoxLayout,
)

from .. import __version__, config, display, i18n
from ..engine import Config, Engine, already_added, has_error, key_of, parse_source
from ..i18n import N_, qt_text, tr, trn
from ..geoip import GeoIP
from ..power import SleepBlocker
from ..update import RELEASES_PAGE, Release, is_newer
from . import autostart, files, theme
from .add_dialog import AddTorrentDialog
from .details import DetailPane
from .dialogs import SettingsDialog, confirm_remove, kib_box
from .icons import icon
from .updates import UpdateChecker
from .models import (
    COUNT_ROLE, FILTERS, FilterDelegate, FilterProxy, NameDelegate, ProgressDelegate, TorrentModel, category, key,
)
from .widgets import DiskMeter, SpeedHistory

S = lt.torrent_status.states

ENCRYPTION_STATUS = {"prefer": N_("Encryption: preferred"), "require": N_("Encryption: required"),
                     "disable": N_("Encryption: off")}

WINDOW_FILE = "window.json"  # size, position, column widths and sort order


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.engine = Engine(cfg)
        resumed = self.engine.resume_all()
        if resumed:
            self.engine.log(trn("resumed {n} torrent", "resumed {n} torrents", resumed))
        self.geo = GeoIP(cfg.state_dir)
        if cfg.peer_countries and self.geo.needs_update():
            self.geo.update_in_background(self.engine.log)
        self.total_speed = SpeedHistory()
        self.speeds: dict[str, SpeedHistory] = {}
        self._file_pickers: list[AddTorrentDialog] = []
        self.sleep_blocker = SleepBlocker()

        self.setWindowTitle("Avilys")
        self.setWindowIcon(app_icon())
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._build_tray()
        self._apply_icons()
        self._restore_layout()
        # The state is shown under each name, so its own column stays hidden
        # (its data still drives the filters and tests).
        self.table.horizontalHeader().setSectionHidden(TorrentModel.STATUS, True)
        self.table.setFocus()  # not the filter box: typing there hides torrents

        self.notifications: list[tuple[str, str]] = []  # (title, text), newest last
        self._was_downloading: set[str] = set()  # notify only when these finish
        self._errors: dict[str, str] = {}  # torrents stopped by an error -> what we said about it
        self._quitting = False
        self._shut_down = False
        self._told_about_tray = False

        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):  # Qt 6.5+: follow the system live
            hints.colorSchemeChanged.connect(self._system_theme_changed)

        # libtorrent runs on its own threads; we only drain alerts and redraw.
        self.pump_timer = QTimer(self, interval=200, timeout=self.engine.pump)
        self.refresh_timer = QTimer(self, interval=1000, timeout=self.refresh)
        self.save_timer = QTimer(self, interval=60_000, timeout=self.engine.save_all)
        self.watch_timer = QTimer(self, interval=5_000, timeout=self._scan_watch_folder)
        for t in (self.pump_timer, self.refresh_timer, self.save_timer, self.watch_timer):
            t.start()

        self.updates = UpdateChecker(self)
        self.updates.finished.connect(self._update_checked)
        self.update_box: QMessageBox | None = None  # the "new version" pop-up, while open
        self._pending_update: Release | None = None  # found while hidden in the tray
        if cfg.check_updates:
            self.updates.start()
        self.refresh()

    @property
    def cfg(self) -> Config:
        return self.engine.cfg

    # -- layout -------------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar(tr("Toolbar"), movable=False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        dpr = self.devicePixelRatioF()
        logo = logo_pixmap(round(24 * dpr))
        logo.setDevicePixelRatio(dpr)
        mark = QLabel()
        mark.setPixmap(logo)
        title = QLabel("Avilys", objectName="wordmark")
        tb.addWidget(mark)
        tb.addWidget(title)

        self.act_add = QAction(tr("Add .torrent"), self, shortcut=QKeySequence.Open, triggered=self.add_files)
        self.act_magnet = QAction(tr("Add magnet"), self, shortcut="Ctrl+U", triggered=self.add_magnet)
        self.act_resume = QAction(tr("Resume"), self, triggered=lambda: self._each_selected(self.engine.resume))
        self.act_pause = QAction(tr("Pause"), self, triggered=lambda: self._each_selected(self.engine.pause))
        self.act_remove = QAction(tr("Remove"), self, shortcut=QKeySequence.Delete, triggered=self.remove_selected)
        self.act_settings = QAction(tr("Settings"), self, shortcut="Ctrl+,", triggered=self.open_settings)
        self.act_quit = QAction(tr("Quit Avilys"), self, shortcut=QKeySequence.Quit, triggered=self.quit)
        self.act_about = QAction(tr("About Avilys"), self, shortcut=QKeySequence.HelpContents, triggered=self.show_about)
        self.addAction(self.act_quit)
        self.addAction(self.act_about)
        tb.addAction(self.act_add)
        tb.widgetForAction(self.act_add).setObjectName("primary")
        tb.addAction(self.act_magnet)
        tb.widgetForAction(self.act_magnet).setObjectName("secondary")
        tb.addSeparator()
        for act in (self.act_resume, self.act_pause, self.act_remove):
            tb.addAction(act)
            btn = tb.widgetForAction(act)
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setToolTip(act.text())
            btn.setAccessibleName(act.text())
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)
        self.search = QLineEdit(placeholderText=tr("Filter torrents"))
        self.search.setAccessibleName(tr("Filter torrents"))
        self.search.setClearButtonEnabled(True)
        self.search_icon = self.search.addAction(QIcon(), QLineEdit.LeadingPosition)
        tb.addWidget(self.search)
        tb.addAction(self.act_settings)
        btn = tb.widgetForAction(self.act_settings)
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setToolTip(tr("Settings"))
        btn.setAccessibleName(tr("Settings"))

    def _apply_icons(self) -> None:
        """(Re)draw toolbar and tray icons in the current theme's colours."""
        t = theme.current
        self.act_add.setIcon(icon("plus", t["primary_fg"]))
        self.act_magnet.setIcon(icon("link", t["icon"]))
        self.act_resume.setIcon(icon("play", t["icon"]))
        self.act_pause.setIcon(icon("pause", t["icon"]))
        self.act_remove.setIcon(icon("trash", t["danger"]))
        self.act_settings.setIcon(icon("settings", t["icon"]))
        self.search_icon.setIcon(icon("search", t["placeholder"]))
        self.slow_button.setIcon(icon("slow", t["accent"] if self.engine.slow else t["muted"], 14))

    def _build_body(self) -> None:
        self.filters = QListWidget(objectName="filters")
        self.filters.setItemDelegate(FilterDelegate(self.filters))
        self.filters.setMouseTracking(True)  # hover highlight
        self.filters.setAccessibleName(tr("Status"))
        for name in FILTERS:
            item = QListWidgetItem(tr(name))
            item.setData(Qt.UserRole, name)
            self.filters.addItem(item)
        self.filters.setCurrentRow(0)
        self.disk = DiskMeter()
        side = QWidget(objectName="sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(212)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 10)
        sl.setSpacing(0)
        sl.addWidget(QLabel(tr("Status").upper(), objectName="section"))
        sl.addWidget(self.filters, 1)
        sl.addWidget(self.disk)

        self.model = TorrentModel(self)
        self.model.explain = self.engine.error_text
        self.proxy = FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)  # name, and under it the state
        self.table.setWordWrap(False)
        self.table.setItemDelegateForColumn(0, NameDelegate(self.table))
        self.table.setItemDelegateForColumn(TorrentModel.PROGRESS, ProgressDelegate(self.table))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in zip(range(1, 9), (84, 180, 150, 96, 88, 92, 64, 88)):
            header.resizeSection(col, width)
        self.table.doubleClicked.connect(self._toggle_row)

        self.details = DetailPane(self.engine, self.geo)
        self.details.retry.clicked.connect(lambda: self.retry(self.selected_handles()))
        self.details.show_countries = self.cfg.peer_countries
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.details)
        split.setSizes([420, 300])
        split.setHandleWidth(5)  # a 1px line (see the style sheet), easier to grab than it looks
        split.setChildrenCollapsible(False)
        self.split = split

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(side)
        bl.addWidget(split, 1)
        self.setCentralWidget(body)

        self.filters.currentItemChanged.connect(
            lambda item, _: self.proxy.set_categories(FILTERS[item.data(Qt.UserRole)]) if item else None)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.lbl_rates = QLabel()
        self.lbl_rates.setProperty("role", "strong")
        self.lbl_dht = QLabel()
        self.lbl_port = QLabel()
        self.lbl_transport = QLabel()
        self.lbl_enc = QLabel()
        self.lbl_counts = QLabel()
        sb.addWidget(self.lbl_rates)
        for w in (self.lbl_dht, self.lbl_port, self.lbl_transport, self.lbl_enc):
            rule = QFrame()
            rule.setProperty("role", "vrule")
            sb.addWidget(rule)
            sb.addWidget(w)
        self.slow_button = QToolButton()
        self.slow_button.setText(tr("Slow mode"))
        self.slow_button.setCheckable(True)
        self.slow_button.setAutoRaise(True)
        self.slow_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.slow_button.setIconSize(QSize(14, 14))
        self.slow_button.clicked.connect(self.toggle_slow_mode)
        sb.addPermanentWidget(self.slow_button)
        sb.addPermanentWidget(self.lbl_counts)

    def _build_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return  # e.g. GNOME without a tray extension: closing the window quits
        tray = QSystemTrayIcon(app_icon(), self)
        tray.setToolTip("Avilys")
        menu = QMenu(self)
        menu.addAction(tr("Show Avilys"), self.show_window)
        menu.addSeparator()
        menu.addAction(tr("Resume all"), lambda: self._each_torrent(self.engine.resume))
        menu.addAction(tr("Pause all"), lambda: self._each_torrent(self.engine.pause))
        menu.addSeparator()
        menu.addAction(self.act_about)
        menu.addAction(self.act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.messageClicked.connect(self.show_window)  # e.g. "a new version is out"
        tray.show()
        self.tray = tray
        # With a tray, hiding the window must not end the app; quit() ends it.
        QApplication.instance().setQuitOnLastWindowClosed(False)

    # -- remembered layout -------------------------------------------------------
    def _layout_file(self) -> Path:
        return self.cfg.state_dir / WINDOW_FILE

    def save_layout(self) -> None:
        """Remember the window's size and position, the column widths and sort
        order, the height of the detail pane and its open tab."""
        def pack(data: QByteArray) -> str:
            return base64.b64encode(bytes(data)).decode()

        data = {
            "geometry": pack(self.saveGeometry()),
            "split": pack(self.split.saveState()),
            "header": pack(self.table.horizontalHeader().saveState()),
            "columns": self.model.columnCount(),  # a saved header only fits the same columns
            "tab": self.details.currentIndex(),
        }
        try:
            path = self._layout_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(path)
        except OSError:
            pass  # not worth interrupting anything for

    def _restore_layout(self) -> None:
        try:
            data = json.loads(self._layout_file().read_text())
            unpack = lambda name: QByteArray(base64.b64decode(data[name]))  # noqa: E731
            self.restoreGeometry(unpack("geometry"))
            self.split.restoreState(unpack("split"))
            header = self.table.horizontalHeader()
            if data.get("columns") == self.model.columnCount() and header.restoreState(unpack("header")):
                self.table.sortByColumn(header.sortIndicatorSection(), header.sortIndicatorOrder())
            self.details.setCurrentIndex(int(data.get("tab", 0)))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # first run, or a file we can't read: keep the defaults

    # -- theme ----------------------------------------------------------------
    def apply_theme(self) -> None:
        theme.apply(QApplication.instance(), self.cfg.theme)
        self._apply_icons()
        self.table.viewport().update()
        self.refresh()

    def _system_theme_changed(self, *_) -> None:
        if self.cfg.theme == "system":
            self.apply_theme()

    # -- refresh ------------------------------------------------------------
    def refresh(self) -> None:
        if self._shut_down:
            return
        self.engine.pump()  # so what we show matches the latest events (e.g. why a torrent stopped)
        self.engine.enforce_seed_ratio()
        self.engine.request_stats()
        slow_before = self.engine.slow
        slow = self.engine.update_speed_mode()
        statuses = self.engine.statuses()
        self.model.update(statuses)
        self.details.refresh()
        self._notify_finished(statuses)
        self._notify_errors(statuses)
        self._record_speeds(statuses)
        self._show_file_pickers()
        self.sleep_blocker.set(self.cfg.prevent_sleep and any(
            st.state == S.downloading and not st.flags & lt.torrent_flags.paused and not has_error(st)
            for st in statuses))
        if slow != slow_before or self.slow_button.isChecked() != slow:
            self.slow_button.setChecked(slow)
            self._apply_icons()
        c = self.cfg
        limits = dict(down=display.size(c.alt_download_limit), up=display.size(c.alt_upload_limit))
        if slow and not c.alt_enabled:
            tip = tr("Slow mode is on by schedule: ↓ {down}/s, ↑ {up}/s", **limits)
        elif slow:
            tip = tr("Slow mode is on: ↓ {down}/s, ↑ {up}/s", **limits)
        else:
            tip = tr("Slow mode is off: ↓ {down}/s, ↑ {up}/s", **limits)
        if c.alt_schedule:
            tip += "\n" + tr("Scheduled every day {start}–{end}", start=c.alt_from, end=c.alt_to)
        self.slow_button.setToolTip(tip)

        cats = [category(st) for st in statuses]
        for i in range(self.filters.count()):
            item = self.filters.item(i)
            name = item.data(Qt.UserRole)
            members = FILTERS[name]
            n = len(cats) if members is None else sum(c in members for c in cats)
            if item.data(COUNT_ROLE) != n:
                item.setData(COUNT_ROLE, n)
            item.setHidden(name == "Errors" and n == 0 and not item.isSelected())

        down = sum(s.download_payload_rate for s in statuses)
        up = sum(s.upload_payload_rate for s in statuses)
        rates = f"↓ {display.size(down)}/s    ↑ {display.size(up)}/s"
        self.lbl_rates.setText(rates)
        if self.tray is not None:
            self.tray.setToolTip(f"Avilys\n{rates}")
        cfg = self.cfg
        self.lbl_dht.setText(trn("DHT: {n} node", "DHT: {n} nodes", self.engine.dht_nodes) if cfg.dht
                             else tr("DHT off"))
        port = self.engine.ses.listen_port()
        mapped = self.engine.port_mapped
        label = tr("Port {port}", port=port)
        reachable = self.engine.reachable()
        if reachable:
            self.lbl_port.setText(f"● {label} · " + tr("reachable"))
            self.lbl_port.setToolTip(tr("Other peers can connect to you.") + (
                "\n" + tr("Your router opened the port for Avilys (UPnP / NAT-PMP).") if mapped else ""))
        elif reachable is None:
            self.lbl_port.setText(label + (" · " + tr("UPnP mapped") if mapped else ""))
            self.lbl_port.setToolTip(tr("Not known yet whether other peers can connect to you.\n"
                                        "It shows here once one does."))
        else:
            self.lbl_port.setText(f"● {label} · " + tr("no incoming connections"))
            self.lbl_port.setToolTip(tr(
                "No peer has connected to you yet. Downloads still work, but can be slower.\n"
                "If this stays, open port {port} (TCP and UDP) on your router or firewall,\n"
                "or turn on “Open the port on my router” in Settings → Connection.", port=port))
        role = {True: "good", None: "", False: "warning"}[reachable]
        if self.lbl_port.property("role") != role:
            self.lbl_port.setProperty("role", role)
            self.lbl_port.style().unpolish(self.lbl_port)
            self.lbl_port.style().polish(self.lbl_port)
        self.lbl_transport.setText(
            "µTP + TCP" if cfg.utp and cfg.tcp else tr("µTP only") if cfg.utp else tr("TCP only"))
        self.lbl_enc.setText(tr(ENCRYPTION_STATUS[cfg.encryption]))
        self.lbl_counts.setText(" · ".join([
            trn("{n} torrent", "{n} torrents", len(statuses)),
            tr("{n} downloading", n=sum(c == "Downloading" for c in cats)),
            tr("{n} seeding", n=sum(c == "Seeding" for c in cats))]))
        try:
            usage = shutil.disk_usage(cfg.save_path)
            free = tr("{free} free of {total}", free=display.size(usage.free), total=display.size(usage.total))
            used = 1 - usage.free / usage.total if usage.total else None
        except OSError:
            free, used = "", None
        self.disk.set_usage(short_path(cfg.save_path, 200), used, free)  # the meter elides it to fit
        self.disk.setToolTip(str(cfg.save_path))
        if self.engine.events:
            self.statusBar().setToolTip("\n".join(self.engine.events))

    def _notify_finished(self, statuses) -> None:
        """Tell the user when something we saw downloading has finished.

        Only torrents seen actively downloading count, so torrents that were
        already complete (or are being re-checked at startup) never notify."""
        for st in statuses:
            k = key(st)
            if st.state in (S.downloading, S.downloading_metadata):
                self._was_downloading.add(k)
            elif st.is_finished and k in self._was_downloading:
                self._was_downloading.discard(k)
                self.notify(tr("Download complete"), st.name)

    def _notify_errors(self, statuses) -> None:
        """Say so, once, when a torrent stops because of an error."""
        errors = {key(st): self.engine.error_text(st) for st in statuses if has_error(st)}
        for st in statuses:
            k = key(st)
            if k in errors and k not in self._errors:
                self.notify(tr("Torrent stopped"), f"{st.name or k[:16]}: {errors[k]}")
        self._errors = errors

    def notify(self, title: str, text: str) -> None:
        self.notifications.append((title, text))
        if self.tray is not None:
            self.tray.showMessage(title, text, app_icon(), 8000)
        else:
            self.statusBar().showMessage(f"{title}: {text}", 10_000)
        QApplication.alert(self)  # flash the taskbar entry if the window isn't focused

    def _record_speeds(self, statuses) -> None:
        self.total_speed.add(sum(s.download_payload_rate for s in statuses),
                             sum(s.upload_payload_rate for s in statuses))
        alive = set()
        for st in statuses:
            k = key(st)
            alive.add(k)
            self.speeds.setdefault(k, SpeedHistory()).add(st.download_payload_rate, st.upload_payload_rate)
        for k in set(self.speeds) - alive:
            del self.speeds[k]
        hs = self.selected_handles()
        if hs and hs[0].is_valid() and key_of(hs[0]) in self.speeds:
            self.details.speed.show_history(self.speeds[key_of(hs[0])], hs[0].status().name)
        else:
            self.details.speed.show_history(self.total_speed, tr("All torrents"))

    def _scan_watch_folder(self) -> None:
        added = self.engine.scan_watch_dir()
        if added:
            self.statusBar().showMessage(
                tr("Added from the watch folder: {names}", names=", ".join(added)), 10_000)
            self.refresh()

    def _show_file_pickers(self) -> None:
        """A magnet's file list arrived: let the user pick files (nothing downloads meanwhile)."""
        while self.engine.files_ready:
            k = self.engine.files_ready.pop(0)
            h = self.engine.handles.get(k)
            if h is None or not h.is_valid():
                continue
            atp = lt.add_torrent_params()
            atp.ti = h.torrent_file()
            dlg = AddTorrentDialog(atp, self.engine.destination(h), self, choosing=True)
            dlg.finished.connect(lambda result, d=dlg, handle=h: self._file_picker_done(d, handle, result))
            self._file_pickers.append(dlg)
            self.show_window()
            dlg.open()

    def _file_picker_done(self, dlg: AddTorrentDialog, h, result: int) -> None:
        self._file_pickers.remove(dlg)
        if self._shut_down or not h.is_valid():
            return
        if result != QDialog.Accepted:
            self.engine.remove(h)  # Cancel means "don't add this after all"
            self.refresh()
            return
        atp, save_path = dlg.result_params()
        try:
            if save_path != self.engine.destination(h):
                self.engine.move(h, save_path)
        except OSError as e:
            self._report([str(e)])
            self.engine.files_ready.append(key_of(h))
            return
        self.engine.choose_files(h, list(atp.file_priorities) or [4] * h.torrent_file().num_files())
        if dlg.dont_ask.isChecked():
            self.set_preferences(confirm_add=False)
        self.refresh()

    def toggle_slow_mode(self) -> None:
        self.set_preferences(alt_enabled=self.slow_button.isChecked())
        if not self.slow_button.isChecked() and self.engine.slow:
            self.statusBar().showMessage(tr("Slow mode stays on until its scheduled time ends."), 6000)
        self.refresh()
        self._apply_icons()

    # -- the torrent list's right-click menu --------------------------------
    def _table_menu(self, pos) -> None:
        handles = self.selected_handles()
        if not handles:
            return
        h = handles[0]
        menu = QMenu(self)
        failed = [x for x in handles if has_error(x.status())]
        if failed:
            again = menu.addAction(tr("Try again"), lambda: self.retry(failed))
            font = again.font()
            font.setBold(True)
            again.setFont(font)
        menu.addAction(self.act_resume)
        menu.addAction(self.act_pause)
        menu.addSeparator()
        menu.addAction(tr("Open folder"), lambda: self.open_folder(h))
        menu.addAction(tr("Move to…"), lambda: self.move_selected())
        menu.addAction(tr("Copy magnet link"), lambda: QGuiApplication.clipboard().setText(
            "\n".join(lt.make_magnet_uri(x) for x in handles)))
        menu.addSeparator()
        seq = menu.addAction(tr("Download in order"))
        seq.setCheckable(True)
        seq.setChecked(bool(h.flags() & lt.torrent_flags.sequential_download))
        seq.setToolTip(tr("Download from the start of each file, so videos can be previewed sooner."))
        seq.toggled.connect(lambda on: [self.engine.set_sequential(x, on) for x in handles])
        menu.addAction(tr("Speed limits…"), lambda: self.ask_speed_limits(handles))
        menu.addAction(tr("Check files again"), lambda: [x.force_recheck() for x in handles])
        menu.addAction(tr("Announce now"), lambda: [x.force_reannounce() for x in handles])
        menu.addSeparator()
        menu.addAction(self.act_remove)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def retry(self, handles) -> None:
        """Clear the error and start again (after freeing disk space, say)."""
        for h in handles:
            self.engine.resume(h)
        self.refresh()

    def open_folder(self, h) -> None:
        """A multi-file torrent's own folder; for a single file, its folder with the file selected."""
        st = h.status()
        target = Path(st.save_path) / st.name
        if target.is_dir():
            files.open_path(target)
        else:
            files.reveal(target)

    def move_selected(self) -> None:
        handles = self.selected_handles()
        if not handles:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Move to"), str(self.engine.destination(handles[0])))
        if folder:
            for h in handles:
                self.engine.move(h, Path(folder))

    def ask_speed_limits(self, handles) -> None:
        h = handles[0]
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Speed limits"))
        form = QFormLayout(dlg)
        down = kib_box(max(h.download_limit(), 0), tr("No limit"))
        up = kib_box(max(h.upload_limit(), 0), tr("No limit"))
        form.addRow(QLabel(tr("For the selected torrents. The overall limits still apply.")))
        form.addRow(tr("Download limit"), down)
        form.addRow(tr("Upload limit"), up)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec():
            for x in handles:
                self.engine.set_limits(x, down.value() * 1024, up.value() * 1024)

    # -- selection helpers --------------------------------------------------
    def selected_handles(self):
        keys = {self.model.key_at(self.proxy.mapToSource(i).row())
                for i in self.table.selectionModel().selectedRows()}
        return [self.engine.handles[k] for k in keys if k in self.engine.handles]

    def _selection_changed(self, *_):
        hs = self.selected_handles()
        self.details.show_torrent(hs[0] if hs else None)

    def _each_selected(self, fn) -> None:
        for h in self.selected_handles():
            fn(h)
        self.refresh()

    def _each_torrent(self, fn) -> None:
        for h in list(self.engine.handles.values()):
            fn(h)
        self.refresh()

    def _toggle_row(self, index) -> None:
        row = self.proxy.mapToSource(index).row()
        st = self.model.statuses()[row]
        h = self.engine.handles.get(self.model.key_at(row))
        if h is not None:
            (self.engine.resume if category(st) in ("Paused", "Queued", "Error") else self.engine.pause)(h)
            self.refresh()

    # -- adding ---------------------------------------------------------------
    def add_sources(self, sources: list[str], ask: bool | None = None) -> list[str]:
        """Add magnets / .torrent paths, showing the add dialog for each one
        unless `ask` is False (default: the user's setting). Returns errors."""
        ask = self.cfg.confirm_add if ask is None else ask
        errors = []
        for src in sources:
            src = src.strip()
            if not src:
                continue
            try:
                atp = parse_source(src)
                if self.engine.has(atp):
                    raise ValueError(already_added(atp))
                save_path = self.cfg.save_path
                reuse_existing = False
                if ask:
                    dlg = AddTorrentDialog(atp, save_path, self)
                    if not dlg.exec():
                        continue
                    atp, save_path = dlg.result_params()
                    reuse_existing = dlg.reuse_existing.isChecked()
                    if dlg.dont_ask.isChecked():
                        self.set_preferences(confirm_add=False)
                        ask = False
                    choose = atp.ti is None and dlg.choose_later
                else:
                    choose = False
                self.engine.add_params(atp, save_path, choose_files=choose, reuse_existing=reuse_existing)
            except (ValueError, RuntimeError, OSError) as e:
                errors.append(str(e))
        self.refresh()
        return errors

    def accept_from_other_launch(self, sources: list[str]) -> None:
        """Links from a second launch (e.g. a magnet link clicked in a browser)."""
        self.show_window()
        self._report(self.add_sources(sources))

    def _report(self, errors: list[str]) -> None:
        if errors:
            QMessageBox.warning(self, tr("Couldn't add"), "\n\n".join(errors))

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Add torrent files"), str(Path.home()), tr("Torrent files") + " (*.torrent)")
        self._report(self.add_sources(paths))

    def add_magnet(self) -> None:
        clip = QGuiApplication.clipboard().text().strip()
        text, ok = QInputDialog.getMultiLineText(
            self, tr("Add magnet links"), tr("One magnet link per line:"),
            clip if clip.startswith("magnet:") else "")
        if ok:
            self._report(self.add_sources(text.splitlines()))

    # -- other actions -------------------------------------------------------
    def remove_selected(self, *, ask: bool = True, delete_files: bool = False) -> None:
        handles = self.selected_handles()
        if not handles:
            return
        if ask:
            ok, delete_files = confirm_remove(self, [h.status().name for h in handles])
            if not ok:
                return
        for h in handles:
            self.engine.remove(h, delete_files)
        self.details.show_torrent(None)
        self.refresh()

    def set_preferences(self, **changes) -> None:
        new = dataclasses.replace(self.cfg, **changes)
        self.engine.apply_config(new)
        config.save(new)

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self, blocked_ranges=self.engine.blocked_ranges, on_about=self.show_about,
                             on_check_updates=lambda: self.check_for_updates(manual=True))
        if dlg.exec():
            new = dlg.result_config()
            dlg.apply_autostart()
            theme_changed = new.theme != self.cfg.theme
            if new.check_updates and not self.cfg.check_updates:
                self.updates.start()
            elif not new.check_updates:
                self.updates.stop()
            self.engine.apply_config(new)
            config.save(new)
            self.details.show_countries = new.peer_countries
            if new.peer_countries and self.geo.needs_update():
                self.geo.update_in_background(self.engine.log)
            if theme_changed:
                self.apply_theme()
            self._apply_icons()
            self.refresh()

    # -- update check ---------------------------------------------------------
    def check_for_updates(self, manual: bool = False) -> None:
        """manual: the user asked, so also say when there's nothing new or the
        check failed, and show a version they had skipped."""
        if manual:
            QApplication.setOverrideCursor(Qt.BusyCursor)
        self.updates.check(manual)

    def _update_checked(self, release, error: str, manual: bool) -> None:
        if manual:
            QApplication.restoreOverrideCursor()
        if release is None:
            if manual:
                QMessageBox.warning(QApplication.activeWindow() or self, tr("Check for updates"),
                                    tr("Couldn't check for updates: {error}", error=error))
            else:
                self.engine.log(tr("update check failed: {error}", error=error))
            return
        if not is_newer(release.version, __version__):
            if manual:
                QMessageBox.information(QApplication.activeWindow() or self, tr("Check for updates"),
                                        tr("You have the latest version ({version}).", version=__version__))
            return
        if release.version == self.cfg.skipped_version and not manual:
            return
        if not manual and not self.isVisible() and self.tray is not None:
            # Hidden in the tray: a quiet notification now, the pop-up when the window opens
            self._pending_update = release
            self.tray.showMessage(tr("Update available"),
                                  tr("Avilys {version} is available.", version=release.version), app_icon(), 10_000)
            return
        self.show_update(release)

    def show_update(self, release: Release) -> None:
        """The pop-up: open the release page, skip this version, or later."""
        self._pending_update = None
        if self.update_box is not None:
            return  # already showing
        box = QMessageBox(QApplication.activeWindow() or self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(tr("Update available"))
        box.setText(tr("Avilys {version} is available. You have {current}.",
                       version=release.version, current=__version__))
        box.setInformativeText(tr("Download it from the releases page on GitHub. "
                                  "Your torrents and settings are kept when you install it."))
        get = box.addButton(tr("Open download page"), QMessageBox.AcceptRole)
        skip = box.addButton(tr("Skip this version"), QMessageBox.DestructiveRole)
        box.addButton(tr("Later"), QMessageBox.RejectRole)
        box.setDefaultButton(get)

        def done(_=None):
            clicked = box.clickedButton()
            if clicked is get:
                files.open_url(release.url or RELEASES_PAGE)
            elif clicked is skip:
                self.set_preferences(skipped_version=release.version)
            self.update_box = None

        box.finished.connect(done)
        self.update_box = box
        box.open()

    def show_about(self) -> None:
        from .about import AboutDialog

        AboutDialog(self).exec()

    # -- window, tray and quitting ---------------------------------------------
    def show_window(self) -> None:
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()  # not showNormal(): a maximized window stays maximized
        self.raise_()
        self.activateWindow()
        if self._pending_update is not None:
            self.show_update(self._pending_update)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def quit(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    # -- drag and drop: .torrent files and magnet text ----------------------
    def dragEnterEvent(self, e) -> None:
        md = e.mimeData()
        if md.hasUrls() or (md.hasText() and md.text().strip().startswith("magnet:")):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        md = e.mimeData()
        if md.hasUrls():
            sources = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in md.urls()]
        else:
            sources = md.text().splitlines()
        self._report(self.add_sources(sources))

    def closeEvent(self, e) -> None:
        if self.tray is not None and self.cfg.close_to_tray and not self._quitting:
            self.save_layout()
            self.hide()  # keep downloading in the tray
            e.ignore()
            if not self._told_about_tray:
                self._told_about_tray = True
                self.tray.showMessage(
                    tr("Avilys is still running"),
                    tr("Downloads continue in the background. Right-click the tray icon to quit."),
                    app_icon(), 6000)
            return
        self.shutdown()
        e.accept()
        if self.tray is not None:
            QApplication.quit()

    def shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        self.save_layout()
        self.sleep_blocker.set(False)
        for t in (self.pump_timer, self.refresh_timer, self.save_timer, self.watch_timer):
            t.stop()
        self.updates.stop()
        if self.tray is not None:
            self.tray.hide()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.engine.shutdown()
        finally:
            QApplication.restoreOverrideCursor()


def short_path(path: Path, limit: int = 26) -> str:
    text = str(path)
    home = str(Path.home())
    if text == home or text.startswith(home + os.sep):
        text = "~" + text[len(home):]
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


def logo_pixmap(size: int) -> QPixmap:
    """The Avilys logo ("C · Cell"): a honey hexagon, a comb cell, holding a
    download arrow. Same geometry as the logo canvas, on a 64-unit grid."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64
    hexagon = [QPointF(x * s, y * s) for x, y in
               ((32, 5), (55.38, 18.5), (55.38, 45.5), (32, 59), (8.62, 45.5), (8.62, 18.5))]
    p.setPen(QPen(QColor(theme.HONEY), 5 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))  # rounds the corners
    p.setBrush(QColor(theme.HONEY))
    p.drawPolygon(hexagon)
    p.setPen(QPen(QColor(theme.COMB), max(5.2 * s, 1.2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(32 * s, 16.5 * s), QPointF(32 * s, 37 * s))
    p.drawPolyline([QPointF(23 * s, 29 * s), QPointF(32 * s, 38 * s), QPointF(41 * s, 29 * s)])
    p.drawLine(QPointF(22 * s, 46.5 * s), QPointF(42 * s, 46.5 * s))
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(size))
    return ic


def make_app(argv=None, theme_choice: str = "system", language: str = "en") -> QApplication:
    """language: "system", or a code from i18n.LANGUAGES. It is fixed for the
    life of the window, so a change in Settings applies at the next start."""
    app = QApplication.instance() or QApplication(argv or sys.argv)
    install_language(app, language)
    app.setApplicationName("Avilys")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("avilys")  # matches avilys.desktop on Linux
    app.setWindowIcon(app_icon())
    app.setStyle(theme.Style("Fusion"))
    app.setFont(theme.ui_font(app.font()))
    theme.apply(app, theme_choice)
    return app


class QtStrings(QTranslator):
    """Qt's own words (OK, Cancel, the file dialog…) in our language."""

    def translate(self, context, source, disambiguation=None, n=-1):
        return qt_text(source) or ""


def install_language(app: QApplication, choice: str) -> str:
    """Switch the app's language; returns the code in use."""
    code = i18n.set_language(choice, QLocale.system().name())
    old = getattr(app, "_avilys_translator", None)
    if old is not None:
        app.removeTranslator(old)
        app._avilys_translator = None
    if code != "en":
        app._avilys_translator = QtStrings(app)
        app.installTranslator(app._avilys_translator)
    return code


def run(state_dir: Path | None = None, sources: list[str] | None = None, minimized: bool = False) -> int:
    """minimized: start in the tray (used when Avilys starts with the system)."""
    from ..cli import default_state_dir
    from .single import InstanceServer, send_to_running, server_name

    cfg = config.load(state_dir or default_state_dir())
    app = make_app(theme_choice=cfg.theme, language=cfg.language)
    name = server_name(cfg.state_dir)
    if send_to_running(name, sources or []):
        return 0  # the open window takes the links
    win = MainWindow(cfg)
    server = InstanceServer(name, win)
    server.received.connect(win.accept_from_other_launch)
    if not minimized:
        win.show()
    elif win.tray is None:
        win.showMinimized()  # no tray to hide in
    win._report(win.add_sources(sources or []))
    code = app.exec()
    win.shutdown()  # covers quitting from the tray or the session ending
    return code


def self_test() -> int:
    """Used by CI on the packaged app: start the engine and window headless."""
    import tempfile

    # Headless when the offscreen plugin is bundled, else the native one.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen;windows" if sys.platform == "win32" else "offscreen")
    app = make_app([sys.argv[0]], theme_choice="light")
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(state_dir=Path(tmp) / "state", save_path=Path(tmp) / "data",
                     listen="127.0.0.1:0", dht=False, lsd=False, port_mapping=False,
                     close_to_tray=False, confirm_add=False, peer_countries=False,
                     prevent_sleep=False, check_updates=False)
        win = MainWindow(cfg)
        errors = win.add_sources(["magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=selftest"])
        deadline = time.monotonic() + 10
        while win.model.rowCount() == 0 and time.monotonic() < deadline:
            app.processEvents()
            win.engine.pump(0.05)
            win.refresh()
        ok = not errors and win.model.rowCount() == 1
        # Flags: the bundled country database must work when the build asks for it
        from .widgets import flag_icon
        geo = GeoIP(Path(tmp) / "state")
        if os.environ.get("AVILYS_REQUIRE_GEOIP"):
            ok = ok and geo.country("8.8.8.8") == ("us", "United States")
        ok = ok and flag_icon("lt") is not None
        # Translations are loaded by name, so check the packaged app really has them
        ok = ok and install_language(app, "lt") == "lt" and tr("Settings") == "Nustatymai"
        install_language(app, "en")
        win.quit()
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        return self_test()
    if args[:1] == ["--version"]:
        return 0
    minimized = autostart.FLAG in args
    return run(sources=[a for a in args if a != autostart.FLAG], minimized=minimized)


if __name__ == "__main__":
    sys.exit(main())
