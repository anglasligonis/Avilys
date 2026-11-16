"""Drive the real Qt window (offscreen) through a loopback download."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

import libtorrent as lt  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from avilys.engine import Config  # noqa: E402
from avilys.gui.app import MainWindow, make_app  # noqa: E402
from avilys.gui.models import category  # noqa: E402
from test_engine import engine, make_torrent  # noqa: E402


def spin(app, cond, others=(), timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        for e in others:
            e.pump(0.02)
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def test_window_downloads_filters_and_removes(tmp_path):
    app = make_app([])
    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent")
    # Throttled (loopback included) so the window sees the download in progress.
    seeder = engine(tmp_path, "seeder", upload_limit=2 * 1024 * 1024)
    everyone = lt.ip_filter()
    everyone.add_rule("0.0.0.0", "255.255.255.255", 1 << seeder.ses.global_peer_class_id)
    seeder.ses.set_peer_class_filter(everyone)
    seeder.add(str(tfile))
    spin(app, lambda: seeder.handles and seeder.statuses()[0].is_seeding, [seeder])

    win = MainWindow(gui_config(tmp_path))
    cfg = win.cfg
    win.show()
    assert win.add_sources([str(tfile), "not-a-torrent"]) and len(win.add_sources([])) == 0
    spin(app, lambda: win.model.rowCount() == 1, [seeder])
    # Adding the same torrent again is refused with a clear message
    (dup,) = win.add_sources([str(tfile)])
    assert "already in your list" in dup

    (h,) = win.engine.handles.values()
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))

    def done():
        win.refresh()
        return category(win.model.statuses()[0]) == "Seeding"

    spin(app, done, [seeder])
    # Finishing a download we watched raises exactly one notification
    assert win.notifications == [("Download complete", "payload.bin")]
    win.refresh()
    assert len(win.notifications) == 1

    # Status filters in the sidebar
    win.filters.setCurrentRow(2)  # "Seeding"
    assert win.proxy.rowCount() == 1
    win.filters.setCurrentRow(1)  # "Downloading"
    assert win.proxy.rowCount() == 0
    win.filters.setCurrentRow(0)
    assert win.filters.item(2).text().endswith("1")

    # Table text and the Files tab for the selected torrent
    assert win.proxy.index(0, 2).data() == "100.0%"
    win.table.selectRow(0)
    win.details.setCurrentWidget(win.details.files)
    win.details.refresh()
    assert win.details.files.item(0, 2).text() == "100.0%"
    win.details.setCurrentWidget(win.details.general)
    assert win.details.magnet.text().startswith("magnet:?xt=urn:btih:")

    # Pause / resume from the toolbar
    win.act_pause.trigger()
    assert category(h.status()) == "Paused"
    win.act_resume.trigger()
    assert category(h.status()) != "Paused"

    # Settings apply live
    win.engine.apply_config(Config(**{**cfg.__dict__, "encryption": "require"}))
    assert win.engine.ses.get_settings()["out_enc_policy"] == int(lt.enc_policy.pe_forced)

    # Remove keeps files unless asked
    resume = cfg.state_dir / "torrents"
    win.remove_selected(ask=False)
    spin(app, lambda: win.model.rowCount() == 0)
    win.engine.pump(0.5)
    assert list(resume.glob("*.resume")) == []
    assert (cfg.save_path / "payload.bin").exists()

    win.quit()
    seeder.shutdown()


def gui_config(tmp_path, **changes) -> Config:
    base = dict(state_dir=tmp_path / "gui" / "state", save_path=tmp_path / "gui" / "data",
                listen="127.0.0.1:0", dht=False, lsd=False, port_mapping=False,
                close_to_tray=False, confirm_add=False,
                prevent_sleep=False,   # never touch the machine's real sleep settings
                check_updates=False,   # no requests to GitHub from tests
                peer_countries=False)  # no monthly database download from tests
    return Config(**{**base, **changes})


def make_folder_torrent(root, out):
    """A torrent of a folder with three files (libtorrent adds padding files)."""
    folder = root / "Album"
    (folder / "extras").mkdir(parents=True)
    for name, size in (("01 intro.flac", 300_000), ("02 song.flac", 500_000), ("extras/cover.jpg", 40_000)):
        (folder / name).write_bytes(os.urandom(size))
    fs = lt.file_storage()
    lt.add_files(fs, str(folder))
    ct = lt.create_torrent(fs)
    lt.set_piece_hashes(ct, str(root))
    out.write_bytes(lt.bencode(ct.generate()))
    return out


def test_add_dialog_chooses_files_and_folder(tmp_path):
    from avilys.engine import parse_source
    from avilys.gui.add_dialog import AddTorrentDialog, display_path, real_files

    app = make_app([])
    tfile = make_folder_torrent(tmp_path / "src", tmp_path / "album.torrent")
    atp = parse_source(str(tfile))
    files = real_files(atp.ti)
    assert sorted(display_path(atp.ti, i) for i in files) == ["01 intro.flac", "02 song.flac", "extras/cover.jpg"]

    dlg = AddTorrentDialog(atp, tmp_path / "default", None)
    assert dlg.tree.topLevelItemCount() == 3  # padding files are hidden
    cover = next(i for i in files if display_path(atp.ti, i) == "extras/cover.jpg")
    dlg.set_checked(cover, False)
    assert "Selected 781.2 KiB" in dlg.footer.text()  # 800,000 bytes
    dlg.set_all(Qt.Unchecked)  # none selected: can't add
    assert not dlg.add_button.isEnabled()
    dlg.set_all(Qt.Checked)
    dlg.set_checked(cover, False)
    dlg.save_path.setText(str(tmp_path / "Music"))
    atp, save = dlg.result_params()
    assert save == tmp_path / "Music"

    win = MainWindow(gui_config(tmp_path))
    win.engine.add_params(atp, save)
    spin(app, lambda: win.model.rowCount() == 1)
    (h,) = win.engine.handles.values()
    prios = h.get_file_priorities()
    assert [prios[i] for i in files] == [0 if i == cover else 4 for i in files]
    assert h.status().save_path == str(tmp_path / "Music")

    # The Files tab hides padding files too, and maps rows to the right files
    win.table.selectRow(0)
    win.details.setCurrentWidget(win.details.files)
    win.details.refresh()
    assert win.details.files.rowCount() == 3
    win.quit()


def test_dark_and_light_themes(tmp_path):
    from PySide6.QtGui import QPalette

    from avilys.gui import theme

    app = make_app([], theme_choice="dark")
    assert theme.current_name == "dark"
    assert app.palette().color(QPalette.Window).lightness() < 60
    win = MainWindow(gui_config(tmp_path, theme="dark"))
    win.set_preferences(theme="light")
    win.apply_theme()
    assert theme.current_name == "light"
    assert app.palette().color(QPalette.Window).lightness() > 200
    assert theme.resolve("system") in ("light", "dark")
    win.quit()


def test_second_launch_hands_links_to_running_window(tmp_path):
    from avilys.gui.single import InstanceServer, send_to_running, server_name

    app = make_app([])
    name = server_name(tmp_path / "state")
    assert name != server_name(tmp_path / "other")  # one window per state folder
    assert not send_to_running(name, ["x"], timeout_ms=200)  # nothing running yet

    server = InstanceServer(name)
    got = []
    server.received.connect(got.append)
    magnet = "magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10"
    # Send from a real second process, the way a clicked magnet link arrives,
    # and let it exit straight away (Windows named pipes lose data otherwise).
    sender = subprocess.Popen([sys.executable, "-c", (
        "import sys, json; from PySide6.QtCore import QCoreApplication; app = QCoreApplication([]);"
        "from avilys.gui.single import send_to_running;"
        "sys.exit(0 if send_to_running(sys.argv[1], json.loads(sys.argv[2])) else 3)"),
        name, json.dumps([magnet, "C:\\files\\x.torrent"])])
    spin(app, lambda: got and sender.poll() is not None, timeout=20)
    assert sender.returncode == 0
    assert got == [[magnet, "C:\\files\\x.torrent"]]
    server.close()
    server.deleteLater()
    spin(app, lambda: True)  # let Qt finish deleting before the next test


def test_app_icon_renders():
    make_app([])
    from avilys.gui.app import app_icon

    sizes = app_icon().availableSizes()
    assert any(s.width() == 256 for s in sizes)


def throttled_seeder(tmp_path, tfile, rate=2 * 1024 * 1024):
    seeder = engine(tmp_path, "seeder", upload_limit=rate)
    everyone = lt.ip_filter()
    everyone.add_rule("0.0.0.0", "255.255.255.255", 1 << seeder.ses.global_peer_class_id)
    seeder.ses.set_peer_class_filter(everyone)
    seeder.add(str(tfile))
    return seeder


def test_peers_flags_pieces_and_speed_graph(tmp_path):
    from avilys.geoip import GeoIP
    from test_extras import make_country_db

    app = make_app([])
    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent")
    seeder = throttled_seeder(tmp_path, tfile, rate=1024 * 1024)
    spin(app, lambda: seeder.handles and seeder.statuses()[0].is_seeding, [seeder])

    win = MainWindow(gui_config(tmp_path))
    # Loopback peers appear as Lithuanian in this test database
    win.geo = GeoIP(tmp_path, bundled=make_country_db(tmp_path / "c.mmdb", {"127.0.0.0/8": ("LT", "Lithuania")}))
    win.details.geo = win.geo
    win.details.show_countries = True
    win.add_sources([str(tfile)])
    spin(app, lambda: (win.refresh(), win.model.rowCount() == 1)[1], [seeder])
    (h,) = win.engine.handles.values()
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    win.table.selectRow(0)
    win.details.setCurrentWidget(win.details.peers)

    def has_peer():
        win.refresh()
        return win.details.peers.rowCount() > 0 and win.details.peers.item(0, 0).text()

    spin(app, has_peer, [seeder])
    cell = win.details.peers.item(0, 0)
    assert cell.text() == "Lithuania" and not cell.icon().isNull()

    win.details.setCurrentWidget(win.details.pieces_page)
    win.details.refresh()
    assert " of " in win.details.piece_info.text() and win.details.piece_bar.pieces
    assert not win.details.piece_bar.grab().isNull()

    spin(app, lambda: (win.refresh(), max(win.total_speed.down) > 0)[1], [seeder])
    win.details.setCurrentWidget(win.details.speed)
    win._record_speeds(win.engine.statuses())
    assert win.details.speed.title == "payload.bin"  # the selected torrent's graph
    assert not win.details.speed.grab().isNull()
    win.quit()
    seeder.shutdown()


def test_magnet_file_picker(tmp_path):
    from test_engine import seeding_pair

    app = make_app([])
    seeder, _, tfile = seeding_pair(tmp_path, files={"keep.bin": 300_000, "skip.bin": 300_000})
    win = MainWindow(gui_config(tmp_path))
    magnet = lt.make_magnet_uri(lt.torrent_info(str(tfile)))
    key = win.engine.add_params(lt.parse_magnet_uri(magnet), choose_files=True)
    spin(app, lambda: key in win.engine.handles, [seeder])
    win.engine.handles[key].connect_peer(("127.0.0.1", seeder.ses.listen_port()))

    spin(app, lambda: (win.refresh(), bool(win._file_pickers))[1], [seeder])
    dlg = win._file_pickers[0]
    assert dlg.windowTitle() == "Choose files" and dlg.tree.topLevelItemCount() == 2
    skip = next(it.data(0, Qt.UserRole) for it in dlg._items() if it.text(0) == "skip.bin")
    dlg.set_checked(skip, False)
    dlg.accept()
    h = win.engine.handles[key]
    keep = next(it.data(0, Qt.UserRole) for it in dlg._items() if it.text(0) == "keep.bin")
    # libtorrent applies priorities in the background
    spin(app, lambda: (lambda p: p[keep] == 4 and p[skip] == 0)(h.get_file_priorities()), [seeder])
    spin(app, lambda: (win.refresh(), h.status().is_finished)[1], [seeder])
    assert (win.cfg.save_path / "pack" / "keep.bin").stat().st_size == 300_000
    win.quit()
    seeder.shutdown()


def test_settings_tabs_round_trip(tmp_path):
    from avilys.gui.dialogs import SettingsDialog

    make_app([])
    cfg = gui_config(tmp_path, listen="0.0.0.0:6881,[::]:6881", seed_ratio=1.5, active_downloads=-1, alt_schedule=True, alt_from="22:00",
                     alt_to="06:30", watch_dir=tmp_path / "watch", blocklist=tmp_path / "list.p2p",
                     incomplete_dir=tmp_path / "unfinished")
    dlg = SettingsDialog(cfg)
    # "&&" is how Qt shows a literal "&" in a tab name
    assert [dlg.tabs.tabText(i).replace("&&", "&") for i in range(dlg.tabs.count())] == \
        ["General", "Connection", "Speed", "Queue & seeding", "Privacy"]
    assert dlg.result_config() == cfg  # opening and saving changes nothing
    dlg.stop_after.setChecked(True)
    dlg.hours.setValue(12)
    dlg.watch_on.setChecked(False)
    dlg.active_seeds.setValue(0)
    dlg.incomplete_on.setChecked(False)
    dlg.prevent_sleep.setChecked(True)
    assert not dlg.anonymous.isChecked()
    dlg.anonymous.setChecked(True)
    new = dlg.result_config()
    assert new.anonymous
    assert (new.seed_hours, new.watch_dir, new.active_seeds) == (12, None, -1)
    assert new.incomplete_dir is None and new.prevent_sleep


def test_slow_mode_button_and_watch_folder(tmp_path):
    app = make_app([])
    win = MainWindow(gui_config(tmp_path, alt_download_limit=50 * 1024))
    win.slow_button.click()
    assert win.engine.slow and win.engine.ses.get_settings()["download_rate_limit"] == 50 * 1024
    assert "Slow mode is on" in win.slow_button.toolTip()
    win.slow_button.click()
    assert not win.engine.slow

    watch = tmp_path / "watch"
    watch.mkdir()
    win.set_preferences(watch_dir=watch)
    (tmp_path / "src").mkdir()
    make_torrent(tmp_path / "src", watch / "dropped.torrent", size=64 * 1024)
    win._scan_watch_folder()
    spin(app, lambda: win.model.rowCount() == 1)
    assert (watch / "dropped.torrent.added").exists()
    win.quit()


def test_about_shows_the_poem(tmp_path):
    from avilys import __version__
    from avilys.gui.about import AboutDialog

    make_app([])
    win = MainWindow(gui_config(tmp_path))
    dlg = AboutDialog(win)
    texts = [w.text() for w in dlg.findChildren(type(dlg.poem))]
    assert "Seven Seas" in texts and "by KS" in texts
    assert dlg.poem.text() == (
        "Seven seas of fiber under neon rain,\n"
        "every song on lease, every book on loan.\n"
        "He drops a magnet in the static, feeds the swarm:\n"
        "what you can’t keep, you never owned."
    )
    assert any(f"Version {__version__}" in t for t in texts)
    assert any("DB-IP" in t for t in texts)  # the database licence asks for credit
    assert win.act_about.shortcut().toString() == "F1"
    assert not dlg.grab().isNull()
    win.quit()


def test_files_tab_opens_and_reveals_files(tmp_path, monkeypatch):
    from avilys.gui import details as details_mod

    app = make_app([])
    cfg = gui_config(tmp_path)
    # A complete multi-file torrent already sitting in the save folder
    tfile = make_folder_torrent(cfg.save_path, tmp_path / "album.torrent")
    win = MainWindow(cfg)
    win.add_sources([str(tfile)])
    spin(app, lambda: (win.refresh(), win.model.rowCount() == 1 and win.engine.statuses()[0].is_seeding)[1])
    win.table.selectRow(0)
    win.details.setCurrentWidget(win.details.files)
    win.details.refresh()

    opened, revealed, messages = [], [], []
    win.details.opener, win.details.revealer = opened.append, revealed.append
    monkeypatch.setattr(details_mod.QMessageBox, "information", lambda *a: messages.append(a[2]))
    rows = {win.details.files.item(r, 0).text(): r for r in range(win.details.files.rowCount())}

    # Double-click opens the file itself
    win.details.files.doubleClicked.emit(win.details.files.model().index(rows["02 song.flac"], 0))
    assert opened == [cfg.save_path / "Album" / "02 song.flac"] and opened[0].exists()
    # Right-click > Show in folder points at the file inside its subfolder
    win.details.show_in_folder(rows["extras/cover.jpg"])
    assert revealed == [cfg.save_path / "Album" / "extras" / "cover.jpg"]

    # A skipped file that isn't on disk explains itself instead of failing
    (cfg.save_path / "Album" / "01 intro.flac").unlink()
    h = win.engine.handles[next(iter(win.engine.handles))]
    h.file_priority(win.details._file_rows[rows["01 intro.flac"]], 0)
    spin(app, lambda: 0 in list(h.get_file_priorities()))
    win.details.open_file(rows["01 intro.flac"])
    assert len(opened) == 1 and "Don't download" in messages[-1]
    win.quit()


def test_reveal_uses_the_platform_file_manager(tmp_path, monkeypatch):
    from avilys.gui import files

    f = tmp_path / "Some Folder" / "episode.mkv"
    f.parent.mkdir()
    f.write_bytes(b"x")
    calls = []

    # Windows: Explorer with the file selected
    monkeypatch.setattr(files.sys, "platform", "win32")
    monkeypatch.setattr(files.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    assert files.reveal(f)
    assert calls[-1] == f'explorer /select,"{f}"'

    # Linux: the freedesktop FileManager1 interface, falling back to opening the folder
    monkeypatch.setattr(files.sys, "platform", "linux")
    ok = type("R", (), {"returncode": 0})()
    monkeypatch.setattr(files.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), ok)[1])
    assert files.reveal(f)
    assert "org.freedesktop.FileManager1.ShowItems" in calls[-1]
    assert any(arg.startswith("array:string:file://") and arg.endswith("episode.mkv") for arg in calls[-1])

    opened = []
    monkeypatch.setattr(files, "open_path", lambda p: (opened.append(p), True)[1])
    monkeypatch.setattr(files.subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    assert files.reveal(f) and opened == [f.parent]
    # Missing file: open the nearest folder that exists
    assert files.reveal(tmp_path / "Some Folder" / "gone" / "x.mkv") and opened[-1] == f.parent


def test_window_layout_is_remembered(tmp_path):
    app = make_app([])
    cfg = gui_config(tmp_path)
    win = MainWindow(cfg)
    win.show()
    win.resize(760, 600)  # fits the 800x800 screen the headless tests run on
    win.move(40, 60)
    win.table.horizontalHeader().resizeSection(1, 133)
    win.table.sortByColumn(4, Qt.DescendingOrder)
    win.split.setSizes([180, 300])
    win.details.setCurrentWidget(win.details.trackers)
    spin(app, lambda: True)
    sizes = win.split.sizes()
    win.quit()

    win = MainWindow(cfg)
    win.show()
    spin(app, lambda: True)
    header = win.table.horizontalHeader()
    assert (win.width(), win.height()) == (760, 600)
    assert header.sectionSize(1) == 133
    assert (header.sortIndicatorSection(), header.sortIndicatorOrder()) == (4, Qt.DescendingOrder)
    assert win.proxy.sortColumn() == 4
    assert win.split.sizes() == sizes
    assert win.details.currentWidget() is win.details.trackers
    win.quit()

    # A file we can't read just means the default layout
    (cfg.state_dir / "window.json").write_text("{not json")
    win = MainWindow(cfg)
    assert (win.width(), win.height()) == (1280, 820)
    win.quit()


def test_computer_stays_awake_only_while_downloading(tmp_path, monkeypatch):
    from avilys import power

    if sys.platform == "win32":  # the real thing: Windows reports the state we just set
        import ctypes

        blocker = power.SleepBlocker()
        blocker.set(True)
        before = ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(power.ES_CONTINUOUS))
        assert before & power.ES_SYSTEM_REQUIRED
        blocker.set(True)
        blocker.set(False)
        after = ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(power.ES_CONTINUOUS))
        assert not after & power.ES_SYSTEM_REQUIRED

    started, stopped = [], []

    class Helper:
        pid = 4242

        def __init__(self, cmd, **kw):
            started.append(cmd)

        def poll(self):
            return None

        def terminate(self):
            stopped.append(self.pid)

    monkeypatch.setattr(power.sys, "platform", "linux")
    monkeypatch.setattr(power.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(power.subprocess, "Popen", Helper)
    monkeypatch.setattr(power.os, "killpg", lambda pid, sig: stopped.append(pid), raising=False)
    blocker = power.SleepBlocker()
    blocker.set(True)
    blocker.set(True)  # already on: nothing more to start
    assert len(started) == 1 and started[0][:2] == ["systemd-inhibit", "--what=sleep:idle"]
    assert started[0][-1] == str(os.getpid())  # the helper ends when Avilys does
    blocker.set(False)
    assert stopped == [4242] and not blocker.active

    # The window asks for it only while something is downloading
    app = make_app([])
    win = MainWindow(gui_config(tmp_path, prevent_sleep=True))
    asked = []
    win.sleep_blocker.set = asked.append
    win.add_sources(["magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=x"])
    spin(app, lambda: (win.refresh(), win.model.rowCount() == 1)[1])
    assert asked and not any(asked)  # a magnet still looking for peers isn't a download
    win.quit()


def test_start_with_the_system(tmp_path, monkeypatch):
    from avilys.gui import app as app_mod
    from avilys.gui import autostart

    if sys.platform.startswith("linux"):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("APPIMAGE", "/opt/apps/Avilys 1.1.AppImage")
        assert not autostart.enabled()
        autostart.set_enabled(True)
        entry = (tmp_path / "config" / "autostart" / "avilys.desktop").read_text()
        assert 'Exec="/opt/apps/Avilys 1.1.AppImage" --minimized' in entry
        assert autostart.enabled()
        autostart.set_enabled(False)
        assert not autostart.enabled()
    elif sys.platform == "win32" and os.environ.get("CI"):  # the real registry: throwaway machines only
        autostart.set_enabled(True)
        assert autostart.enabled()
        autostart.set_enabled(False)
        assert not autostart.enabled()

    # "--minimized" starts in the tray and isn't mistaken for a torrent
    calls = []
    monkeypatch.setattr(app_mod, "run", lambda **kw: calls.append(kw) or 0)
    monkeypatch.setattr(sys, "argv", ["avilys", "--minimized", "magnet:?xt=urn:btih:abc"])
    assert app_mod.main() == 0
    assert calls == [{"sources": ["magnet:?xt=urn:btih:abc"], "minimized": True}]


def test_port_indicator(tmp_path):
    make_app([])
    win = MainWindow(gui_config(tmp_path))
    port = win.engine.ses.listen_port()
    assert win.lbl_port.text() == f"Port {port}"  # nothing known yet
    # The engine decides (see test_reachable_from_outside); here, what the window says
    win.engine.reachable = lambda: True
    win.refresh()
    assert win.lbl_port.text() == f"● Port {port} · reachable" and win.lbl_port.property("role") == "good"
    win.engine.reachable = lambda: False
    win.refresh()
    assert "no incoming connections" in win.lbl_port.text() and win.lbl_port.property("role") == "warning"
    assert f"open port {port}" in win.lbl_port.toolTip()
    win.engine.reachable = lambda: None
    win.refresh()
    assert win.lbl_port.text() == f"Port {port}" and not win.lbl_port.property("role")
    win.quit()


def test_torrent_errors_are_shown_and_can_be_retried(tmp_path):
    from avilys.engine import has_error

    app = make_app([])
    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent", size=256 * 1024)
    seeder = engine(tmp_path, "seeder")
    seeder.add(str(tfile))
    spin(app, lambda: seeder.handles and seeder.statuses()[0].is_seeding, [seeder])

    win = MainWindow(gui_config(tmp_path))
    blocker = win.cfg.save_path / "payload.bin"  # a folder sits where the file belongs
    blocker.mkdir()
    assert win.add_sources([str(tfile)]) == []
    spin(app, lambda: win.engine.handles, [seeder])
    (h,) = win.engine.handles.values()
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))  # Windows only notices once data arrives
    spin(app, lambda: (win.refresh(), win.model.rowCount() == 1 and has_error(win.model.statuses()[0]))[1], [seeder])

    assert category(win.model.statuses()[0]) == "Error"
    assert win.proxy.index(0, 3).data() == "Error"
    assert win.proxy.index(0, 3).data(Qt.ToolTipRole).startswith("payload.bin\n")
    # One notification, however often the window refreshes
    win.refresh()
    assert [title for title, _ in win.notifications] == ["Torrent stopped"]
    assert win.notifications[0][1].startswith("payload.bin: ")

    # The sidebar counts it and can show only the broken ones
    errors_row = next(i for i in range(win.filters.count()) if win.filters.item(i).data(Qt.UserRole) == "Errors")
    assert win.filters.item(errors_row).text().endswith("1")
    win.filters.setCurrentRow(errors_row)
    assert win.proxy.rowCount() == 1
    win.filters.setCurrentRow(1)  # "Downloading"
    assert win.proxy.rowCount() == 0
    win.filters.setCurrentRow(0)

    # The General tab says what went wrong and offers to try again
    win.table.selectRow(0)
    win.details.setCurrentWidget(win.details.general)
    win.details.refresh()
    assert not win.details.error_row.isHidden()
    assert win.details.error.text().startswith("Stopped: ") and "payload.bin" in win.details.error.text()

    blocker.rmdir()
    win.details.retry.click()
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    spin(app, lambda: (win.refresh(), category(win.model.statuses()[0]) == "Seeding")[1], [seeder])
    win.details.refresh()
    assert win.details.error_row.isHidden()
    assert win.filters.item(errors_row).text().endswith("0")
    assert [title for title, _ in win.notifications] == ["Torrent stopped", "Download complete"]
    win.quit()
    seeder.shutdown()


def test_new_version_pop_up(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from avilys import __version__
    from avilys.gui import app as app_mod
    from test_update import fake_github, release

    app = make_app([])
    win = MainWindow(gui_config(tmp_path))
    win.show()
    opened, told = [], []
    monkeypatch.setattr(app_mod.files, "open_url", opened.append)
    monkeypatch.setattr(app_mod.QMessageBox, "information", lambda parent, title, text: told.append(text))
    monkeypatch.setattr(app_mod.QMessageBox, "warning", lambda parent, title, text: told.append(text))

    def wait_for_box():
        spin(app, lambda: win.update_box is not None)
        box = win.update_box
        return box, {b.text(): b for b in box.buttons()}

    with fake_github(release("v99.0.0")) as (url, seen):
        win.updates.url = url
        win.updates.check()  # the automatic daily check
        box, buttons = wait_for_box()
        assert box.text() == f"Avilys 99.0.0 is available. You have {__version__}."
        assert set(buttons) == {"Open download page", "Skip this version", "Later"}
        buttons["Open download page"].click()
        spin(app, lambda: win.update_box is None)
        assert opened == ["https://github.com/anglasligonis/Avilys/releases/tag/v99.0.0"]

        win.updates.check()
        box, buttons = wait_for_box()
        buttons["Skip this version"].click()
        spin(app, lambda: win.update_box is None)
        assert win.cfg.skipped_version == "99.0.0"

        # A skipped version stays quiet in the daily check...
        n = len(seen)
        win.updates.check()
        spin(app, lambda: len(seen) > n and not win.updates.busy)
        app.processEvents()
        assert win.update_box is None
        # ...but asking with "Check now" still shows it
        win.check_for_updates(manual=True)
        box, buttons = wait_for_box()
        buttons["Later"].click()
        spin(app, lambda: win.update_box is None)
        assert opened == ["https://github.com/anglasligonis/Avilys/releases/tag/v99.0.0"]

    # Nothing newer: only "Check now" says so
    with fake_github(release(f"v{__version__}")) as (url, seen):
        win.updates.url = url
        win.check_for_updates(manual=True)
        spin(app, lambda: told)
        assert told[-1] == f"You have the latest version ({__version__})."

    # Offline: only "Check now" says so; the daily check just notes it in the log
    win.updates.url = "http://127.0.0.1:9/releases/latest"
    win.check_for_updates(manual=True)
    spin(app, lambda: len(told) == 2)
    assert told[-1].startswith("Couldn't check for updates: ")
    assert win.update_box is None
    win.quit()


def test_update_check_follows_the_setting(tmp_path):
    from avilys.gui.dialogs import SettingsDialog

    make_app([])
    win = MainWindow(gui_config(tmp_path))
    assert not win.updates.timer.isActive()  # tests turn it off
    win.quit()
    win = MainWindow(gui_config(tmp_path, check_updates=True))
    assert win.updates.timer.isActive()
    dlg = SettingsDialog(win.cfg, on_check_updates=lambda: None)
    assert dlg.check_updates.isChecked() and dlg.check_now.isEnabled()
    dlg.check_updates.setChecked(False)
    assert dlg.result_config().check_updates is False
    win.updates.stop()
    win.quit()
