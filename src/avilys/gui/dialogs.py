"""Settings (in tabs) and the remove confirmation."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTime, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget,
    QTimeEdit, QVBoxLayout, QWidget,
)

from ..config import listen_on, port_of
from . import associations, autostart
from ..engine import Config
from ..i18n import LANGUAGES, N_, tr, trn
from ..net import AdapterNotConnected

THEME_LABELS = [("system", N_("Same as system")), ("light", N_("Light")), ("dark", N_("Dark"))]

ENCRYPTION_LABELS = [
    ("prefer", N_("Prefer encrypted (accept both)")),
    ("require", N_("Require encryption")),
    ("disable", N_("Never encrypt")),
]


def network_interfaces() -> list[tuple[str, str]]:
    """(value for libtorrent, label) for each connected network adapter.

    Linux and macOS bind by device name (e.g. wg0), so a VPN that reconnects
    with a new address still works; on Windows we bind by IPv4 address."""
    from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface

    out = []
    for iface in QNetworkInterface.allInterfaces():
        flags = iface.flags()
        if not flags & QNetworkInterface.IsUp or flags & QNetworkInterface.IsLoopBack:
            continue
        v4 = [e.ip().toString() for e in iface.addressEntries()
              if e.ip().protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol]
        if sys.platform == "win32":
            if not v4:
                continue
            value = v4[0]
        else:
            value = iface.name()
        out.append((value, f"{iface.humanReadableName()} ({', '.join(v4) or tr('IPv6 only')})"))
    return out


def adapter_address(interface: str | None) -> str | None:
    """The address to send Avilys's own web requests from, so they leave
    through the adapter chosen in Settings like the transfers do. None when no
    adapter is chosen (any route). Raises AdapterNotConnected when it is
    chosen but down: the request must then not be made at all."""
    import ipaddress

    from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface

    if not interface:
        return None
    try:  # Windows binds by address
        ipaddress.ip_address(interface)
        wanted = interface
    except ValueError:
        wanted = None
    for iface in QNetworkInterface.allInterfaces():
        if not iface.flags() & QNetworkInterface.IsUp or (wanted is None and iface.name() != interface):
            continue
        ips = [e.ip() for e in iface.addressEntries() if not e.ip().isLinkLocal()]
        texts = [ip.toString() for ip in ips]
        if wanted is not None:
            if wanted in texts:
                return wanted
            continue
        v4 = [t for ip, t in zip(ips, texts) if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol]
        if v4 or texts:
            return (v4 or texts)[0]
    raise AdapterNotConnected(tr("network adapter {name} isn't connected", name=interface))


def folder_row(edit: QLineEdit, parent, title: str, files: str | None = None, clearable: bool = False) -> QWidget:
    """A path field with Browse… (and optionally Clear) buttons."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(edit, 1)
    browse = QPushButton(tr("Browse…"))
    browse.setAutoDefault(False)

    def pick():
        if files:
            path, _ = QFileDialog.getOpenFileName(parent, title, edit.text() or str(Path.home()), files)
        else:
            path = QFileDialog.getExistingDirectory(parent, title, edit.text() or str(Path.home()))
        if path:
            edit.setText(path)

    browse.clicked.connect(pick)
    lay.addWidget(browse)
    if clearable:
        clear = QPushButton(tr("Clear"))
        clear.setAutoDefault(False)
        clear.clicked.connect(edit.clear)
        lay.addWidget(clear)
    return row


def kib_box(limit: int, unlimited_label: str | None = None) -> QSpinBox:
    box = QSpinBox()
    box.setRange(0, 10_000_000)
    box.setSuffix(" KiB/s")
    box.setSpecialValueText(unlimited_label or tr("Unlimited"))
    box.setValue(max(limit, 0) // 1024)
    return box


def count_box(value: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(0, 999)
    box.setSpecialValueText(tr("Unlimited"))  # 0 here means -1 to libtorrent
    box.setValue(0 if value < 0 else value)
    return box


def time_edit(hhmm: str) -> QTimeEdit:
    edit = QTimeEdit(QTime.fromString(hhmm, "HH:mm") if QTime.fromString(hhmm, "HH:mm").isValid() else QTime(8, 0))
    edit.setDisplayFormat("HH:mm")
    return edit


def page(*rows) -> QWidget:
    """A settings tab. It scrolls when the screen is too small to show it all."""
    w = QWidget()
    form = QFormLayout(w)
    form.setVerticalSpacing(10)
    for label, widget in rows:
        form.addRow(label, widget)
    scroll = QScrollArea()
    scroll.setWidget(w)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return scroll


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "muted")
    lbl.setWordWrap(True)
    return lbl


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None, blocked_ranges: int | None = None, on_about=None,
                 on_check_updates=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.setMinimumWidth(620)
        self.cfg = cfg
        tabs = QTabWidget()

        # General
        self.save_path = QLineEdit(str(cfg.save_path))
        self.watch_on = QCheckBox(tr("Add .torrent files that appear in this folder"))
        self.watch_dir = QLineEdit(str(cfg.watch_dir or ""))
        self.watch_on.setChecked(cfg.watch_dir is not None)
        self.watch_dir.setEnabled(cfg.watch_dir is not None)
        self.watch_on.toggled.connect(self.watch_dir.setEnabled)
        self.incomplete_on = QCheckBox(tr("Keep unfinished downloads in a separate folder"))
        self.incomplete_dir = QLineEdit(str(cfg.incomplete_dir or ""))
        self.incomplete_on.setChecked(cfg.incomplete_dir is not None)
        self.incomplete_dir.setEnabled(cfg.incomplete_dir is not None)
        self.incomplete_on.toggled.connect(self.incomplete_dir.setEnabled)
        self.autostart = QCheckBox(tr("Start Avilys when I sign in, hidden in the tray"))
        self._autostart_was = autostart.supported() and autostart.enabled()
        self.autostart.setChecked(self._autostart_was)
        self.autostart.setEnabled(autostart.supported())
        self.prevent_sleep = QCheckBox(tr("Keep the computer awake while downloading"))
        self.prevent_sleep.setChecked(cfg.prevent_sleep)
        self.check_updates = QCheckBox(tr("Tell me when a new version is out"))
        self.check_updates.setChecked(cfg.check_updates)
        self.check_now = QPushButton(tr("Check now"))
        self.check_now.setAutoDefault(False)
        self.check_now.setEnabled(on_check_updates is not None)
        if on_check_updates is not None:
            self.check_now.clicked.connect(on_check_updates)
        updates_row = QWidget()
        ul = QHBoxLayout(updates_row)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(self.check_updates, 1)
        ul.addWidget(self.check_now)
        self.confirm_add = QCheckBox(tr("Ask for the save folder and files when adding a torrent"))
        self.confirm_add.setChecked(cfg.confirm_add)
        self.close_to_tray = QCheckBox(tr("Keep downloading in the tray when the window is closed"))
        self.close_to_tray.setChecked(cfg.close_to_tray)
        self.theme = QComboBox()
        for value, label in THEME_LABELS:
            self.theme.addItem(tr(label), value)
        self.theme.setCurrentIndex([v for v, _ in THEME_LABELS].index(cfg.theme))
        self.language = QComboBox()
        self.language.addItem(tr("Same as system"), "system")
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)  # each language under its own name
        self.language.setCurrentIndex(max(self.language.findData(cfg.language), 0))
        self.default_status = QLabel()
        self.default_status.setWordWrap(True)
        self.default_button = QPushButton(tr("Make Avilys the default"))
        self.default_button.setAutoDefault(False)
        self.default_button.clicked.connect(self.make_default_app)
        default_row = QWidget()  # who opens links now, with the button underneath
        dl = QVBoxLayout(default_row)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        dl.addWidget(self.default_status)
        button_row = QHBoxLayout()
        button_row.addWidget(self.default_button)
        button_row.addStretch(1)
        dl.addLayout(button_row)
        self.refresh_default_status()
        tabs.addTab(page(
            (tr("Save new downloads to"), folder_row(self.save_path, self, tr("Save downloads to"))),
            (tr("Unfinished"), self.incomplete_on),
            ("", folder_row(self.incomplete_dir, self, tr("Folder for unfinished downloads"))),
            ("", hint(tr("Files move to the save folder when a download completes."))),
            (tr("Watch folder"), self.watch_on),
            ("", folder_row(self.watch_dir, self, tr("Watch folder"))),
            ("", hint(tr("Added files are renamed to .torrent.added, so each one is picked up once."))),
            (tr("Adding"), self.confirm_add),
            (tr("Window"), self.close_to_tray),
            ("", self.autostart),
            ("", self.prevent_sleep),
            (tr("Theme"), self.theme),
            (tr("Language"), self.language),
            ("", hint(tr("A new language is used the next time Avilys starts."))),
            (tr("Updates"), updates_row),
            ("", hint(tr("Avilys asks GitHub once a day whether there's a newer release. "
                         "It never downloads or installs anything by itself."))),
            (tr("Default app"), default_row),
        ), tr("General"))

        # Connection
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(port_of(cfg.listen))
        self.interface = QComboBox()
        self.interface.addItem(tr("Any (all connections)"), None)
        for value, label in network_interfaces():
            self.interface.addItem(label, value)
        if cfg.interface and self.interface.findData(cfg.interface) < 0:
            self.interface.addItem(tr("{name} (not connected now)", name=cfg.interface), cfg.interface)
        self.interface.setCurrentIndex(max(self.interface.findData(cfg.interface), 0))
        self.encryption = QComboBox()
        for value, label in ENCRYPTION_LABELS:
            self.encryption.addItem(tr(label), value)
        self.encryption.setCurrentIndex([v for v, _ in ENCRYPTION_LABELS].index(cfg.encryption))
        self.dht = QCheckBox(tr("DHT (find peers without trackers)"))
        self.dht.setChecked(cfg.dht)
        self.utp = QCheckBox(tr("µTP (UDP transport that yields to other traffic)"))
        self.utp.setChecked(cfg.utp)
        self.lsd = QCheckBox(tr("Find peers on the local network"))
        self.lsd.setChecked(cfg.lsd)
        self.port_mapping = QCheckBox(tr("Open the port on my router (UPnP / NAT-PMP)"))
        self.port_mapping.setChecked(cfg.port_mapping)
        tabs.addTab(page(
            (tr("Listening port"), self.port),
            (tr("Network"), self.interface),
            ("", hint(tr("Pick your VPN here to use only that connection. If it disconnects, "
                         "transfers stop instead of continuing over your normal connection."))),
            (tr("Encryption"), self.encryption),
            ("", self.dht), ("", self.utp), ("", self.lsd), ("", self.port_mapping),
        ), tr("Connection"))

        # Speed
        self.max_down = kib_box(cfg.download_limit)
        self.max_up = kib_box(cfg.upload_limit)
        self.alt_down = kib_box(cfg.alt_download_limit)
        self.alt_up = kib_box(cfg.alt_upload_limit)
        self.alt_enabled = QCheckBox(tr("Slow mode is on"))
        self.alt_enabled.setChecked(cfg.alt_enabled)
        self.alt_schedule = QCheckBox(tr("Turn on slow mode every day"))
        self.alt_schedule.setChecked(cfg.alt_schedule)
        self.alt_from = time_edit(cfg.alt_from)
        self.alt_to = time_edit(cfg.alt_to)
        times = QWidget()
        tl = QHBoxLayout(times)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(QLabel(tr("from")))
        tl.addWidget(self.alt_from)
        tl.addWidget(QLabel(tr("to")))
        tl.addWidget(self.alt_to)
        tl.addStretch(1)
        for w in (self.alt_from, self.alt_to):
            w.setEnabled(cfg.alt_schedule)
            self.alt_schedule.toggled.connect(w.setEnabled)
        tabs.addTab(page(
            (tr("Download limit"), self.max_down),
            (tr("Upload limit"), self.max_up),
            ("", hint(tr("Slow mode swaps in lower limits, for example while you work or game. "
                         "Toggle it from the status bar."))),
            (tr("Slow download limit"), self.alt_down),
            (tr("Slow upload limit"), self.alt_up),
            ("", self.alt_enabled),
            (tr("Schedule"), self.alt_schedule),
            ("", times),
        ), tr("Speed"))

        # Queue & seeding
        self.active_downloads = count_box(cfg.active_downloads)
        self.active_seeds = count_box(cfg.active_seeds)
        self.stop_at_ratio = QCheckBox(tr("Stop seeding at ratio"))
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(0, 100)
        self.ratio.setSingleStep(0.5)
        self.ratio.setValue(cfg.seed_ratio if cfg.seed_ratio is not None else 2.0)
        self.stop_at_ratio.setChecked(cfg.seed_ratio is not None)
        self.ratio.setEnabled(cfg.seed_ratio is not None)
        self.stop_at_ratio.toggled.connect(self.ratio.setEnabled)
        self.stop_after = QCheckBox(tr("Stop seeding after"))
        self.hours = QDoubleSpinBox()
        self.hours.setRange(0.5, 10_000)
        self.hours.setSingleStep(1)
        self.hours.setSuffix(" " + tr("hours"))
        self.hours.setValue(cfg.seed_hours if cfg.seed_hours is not None else 24)
        self.stop_after.setChecked(cfg.seed_hours is not None)
        self.hours.setEnabled(cfg.seed_hours is not None)
        self.stop_after.toggled.connect(self.hours.setEnabled)
        tabs.addTab(page(
            (tr("Downloading at once"), self.active_downloads),
            (tr("Seeding at once"), self.active_seeds),
            ("", hint(tr("Extra torrents wait in the queue and start when a slot frees up."))),
            ("", self._pair(self.stop_at_ratio, self.ratio)),
            ("", self._pair(self.stop_after, self.hours)),
            ("", hint(tr("Whichever comes first. With neither, Avilys seeds until you pause or remove a torrent."))),
        ), tr("Queue && seeding"))  # && shows a literal & (a single one marks a shortcut)

        # Privacy
        self.blocklist = QLineEdit(str(cfg.blocklist or ""))
        self.blocklist.setPlaceholderText(tr("No blocklist"))
        loaded = "" if blocked_ranges is None or not cfg.blocklist else trn(
            "{n} address range blocked.", "{n} address ranges blocked.", blocked_ranges) + " "
        self.anonymous = QCheckBox(tr("Don't tell peers and trackers which program and version I use"))
        self.anonymous.setChecked(cfg.anonymous)
        self.peer_countries = QCheckBox(tr("Show peer countries"))
        self.peer_countries.setChecked(cfg.peer_countries)
        tabs.addTab(page(
            (tr("IP blocklist"), folder_row(
                self.blocklist, self, tr("Choose a blocklist"),
                tr("Blocklists") + " (*.p2p *.dat *.txt *.gz);;" + tr("All files") + " (*)", clearable=True)),
            ("", hint(loaded + tr("Peers in these address ranges are never contacted. P2P, eMule .dat "
                                  "and CIDR lists work, gzipped or not."))),
            (tr("Anonymous mode"), self.anonymous),
            ("", hint(tr("Your IP address stays visible to peers: use a VPN to hide it. "
                         "Some private trackers refuse programs they can't identify."))),
            (tr("Countries"), self.peer_countries),
            ("", hint(tr("Uses the free country database from db-ip.com (IP Geolocation by DB-IP), "
                         "refreshed about once a month."))),
        ), tr("Privacy"))

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if on_about is not None:
            about = buttons.addButton(tr("About Avilys"), QDialogButtonBox.HelpRole)
            about.setAutoDefault(False)
            about.clicked.connect(on_about)
        layout.addWidget(buttons)
        self.tabs = tabs
        self._fit_to_screen()

    def _fit_to_screen(self) -> None:
        """Open tall enough to show the longest tab without scrolling, if the
        screen allows; otherwise the tabs scroll."""
        pages = [self.tabs.widget(i).widget() for i in range(self.tabs.count())]
        want_w = max(p.sizeHint().width() for p in pages) + 48
        want_h = max(p.sizeHint().height() for p in pages) + self.tabs.tabBar().sizeHint().height() + 90
        screen = self.screen().availableGeometry() if self.screen() else None
        max_h = int(screen.height() * 0.9) if screen else want_h
        self.resize(max(self.minimumWidth(), want_w), min(want_h, max_h))

    def refresh_default_status(self) -> None:
        if not associations.supported():
            self.default_status.setText(tr("Not available on this system."))
            self.default_button.setEnabled(False)
            return
        st = associations.status()
        self.default_status.setText(associations.describe(st))
        self.default_button.setEnabled(not all(ours for ours, _ in st.values()))

    def make_default_app(self) -> None:
        from .app import logo_pixmap  # here to avoid a circular import

        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        logo_pixmap(256).save(buf, "PNG")
        result = associations.make_default(icon_png=bytes(data))
        self.refresh_default_status()
        if result.needs_settings:
            QMessageBox.information(self, tr("Default app"), result.message)
            QDesktopServices.openUrl(QUrl(associations.WINDOWS_SETTINGS))
        elif not result.ok:
            QMessageBox.warning(self, tr("Default app"), result.message)

    def apply_autostart(self) -> None:
        """Starting with the system is kept by the system itself, not in our settings."""
        want = self.autostart.isChecked()
        if not autostart.supported() or want == self._autostart_was:
            return
        try:
            autostart.set_enabled(want)
        except OSError as e:
            QMessageBox.warning(self, tr("Start with the system"), tr("Couldn't change this: {error}", error=e))

    @staticmethod
    def _pair(check: QCheckBox, box) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(check)
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def result_config(self) -> Config:
        watch = self.watch_dir.text().strip()
        block = self.blocklist.text().strip()
        unfinished = self.incomplete_dir.text().strip()
        return dataclasses.replace(
            self.cfg,
            save_path=Path(self.save_path.text()).expanduser(),
            incomplete_dir=Path(unfinished).expanduser() if self.incomplete_on.isChecked() and unfinished else None,
            prevent_sleep=self.prevent_sleep.isChecked(),
            check_updates=self.check_updates.isChecked(),
            watch_dir=Path(watch).expanduser() if self.watch_on.isChecked() and watch else None,
            confirm_add=self.confirm_add.isChecked(),
            close_to_tray=self.close_to_tray.isChecked(),
            theme=self.theme.currentData(),
            language=self.language.currentData(),
            listen=listen_on(self.port.value()),
            interface=self.interface.currentData(),
            encryption=self.encryption.currentData(),
            dht=self.dht.isChecked(),
            utp=self.utp.isChecked(),
            lsd=self.lsd.isChecked(),
            port_mapping=self.port_mapping.isChecked(),
            download_limit=self.max_down.value() * 1024,
            upload_limit=self.max_up.value() * 1024,
            alt_download_limit=self.alt_down.value() * 1024,
            alt_upload_limit=self.alt_up.value() * 1024,
            alt_enabled=self.alt_enabled.isChecked(),
            alt_schedule=self.alt_schedule.isChecked(),
            alt_from=self.alt_from.time().toString("HH:mm"),
            alt_to=self.alt_to.time().toString("HH:mm"),
            active_downloads=self.active_downloads.value() or -1,
            active_seeds=self.active_seeds.value() or -1,
            seed_ratio=self.ratio.value() if self.stop_at_ratio.isChecked() else None,
            seed_hours=self.hours.value() if self.stop_after.isChecked() else None,
            blocklist=Path(block).expanduser() if block else None,
            anonymous=self.anonymous.isChecked(),
            peer_countries=self.peer_countries.isChecked(),
        )


def confirm_remove(parent, names: list[str]) -> tuple[bool, bool]:
    """Ask before removing. Returns (remove?, also delete files?)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(tr("Remove torrents"))
    box.setTextFormat(Qt.PlainText)  # shows the torrent's name
    if len(names) == 1:
        box.setText(tr("Remove “{name}” from the list?", name=names[0]))
    else:
        box.setText(trn("Remove {n} torrent from the list?", "Remove {n} torrents from the list?", len(names)))
    delete = QCheckBox(tr("Also delete the downloaded files"))
    box.setCheckBox(delete)
    box.setStandardButtons(QMessageBox.Cancel)
    remove = box.addButton(tr("Remove"), QMessageBox.DestructiveRole)
    box.exec()
    return box.clickedButton() is remove, delete.isChecked()
