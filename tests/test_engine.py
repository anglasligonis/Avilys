"""End-to-end tests: two real libtorrent sessions on loopback, one seeding
and one downloading. No internet needed (DHT, LSD and UPnP are off)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import libtorrent as lt
import pytest

from avilys.engine import UTP_SOCKET, Config, Engine, forget, saved_torrents


def make_torrent(src_dir: Path, out: Path, size: int = 3 * 1024 * 1024) -> Path:
    payload = src_dir / "payload.bin"
    payload.write_bytes(os.urandom(size))
    fs = lt.file_storage()
    lt.add_files(fs, str(payload))
    ct = lt.create_torrent(fs, piece_size=64 * 1024)
    lt.set_piece_hashes(ct, str(src_dir))
    out.write_bytes(lt.bencode(ct.generate()))
    return out


def engine(tmp: Path, name: str, **overrides) -> Engine:
    cfg = Config(
        state_dir=tmp / name / "state",
        save_path=tmp / name / "data",
        listen="127.0.0.1:0",
        dht=False,
        lsd=False,
        port_mapping=False,
        **overrides,
    )
    return Engine(cfg)


def wait_for(eng: Engine, cond, timeout: float = 30.0, others=()) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for e in (eng, *others):
            e.pump(0.1)
        if cond():
            return
    from conftest import trace_report

    raise AssertionError(f"timed out; events: {list(eng.events)}\nwhat the engines saw:\n{trace_report()}")


def transfer(tmp: Path, **overrides) -> int:
    """Seed a 3 MiB file to a second session; return the OR of the
    peer_info flags seen on the leecher's connections."""
    seed_dir = tmp / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp / "t.torrent")

    # Throttle the seeder so the connection lives long enough to inspect.
    # Loopback peers are normally exempt from rate limits, so put every
    # address in the global (limited) peer class.
    seeder = engine(tmp, "seeder", upload_limit=1024 * 1024, **overrides)
    everyone = lt.ip_filter()
    everyone.add_rule("0.0.0.0", "255.255.255.255", 1 << seeder.ses.global_peer_class_id)
    seeder.ses.set_peer_class_filter(everyone)
    leecher = engine(tmp, "leecher", **overrides)
    seeder.add(str(tfile))
    leecher.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and leecher.handles, others=[leecher])
    wait_for(seeder, lambda: seeder.statuses()[0].is_seeding, others=[leecher])

    (lh,) = leecher.handles.values()
    lh.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    seen = 0

    def done() -> bool:
        nonlocal seen
        for p in lh.get_peer_info():
            seen |= int(p.flags)
        return leecher.statuses()[0].is_seeding

    wait_for(leecher, done, others=[seeder])

    got = (tmp / "leecher" / "data" / "payload.bin").read_bytes()
    assert got == (seed_dir / "payload.bin").read_bytes()
    assert seeder.statuses()[0].total_payload_upload > 0  # the seeder really seeded
    leecher.shutdown()
    seeder.shutdown()
    return seen


ENCRYPTED = int(lt.peer_info.rc4_encrypted) | int(lt.peer_info.plaintext_encrypted)


def test_download_over_tcp_and_utp(tmp_path):
    transfer(tmp_path)


def test_download_utp_only(tmp_path):
    # TCP is off on both ends, so the transfer can only have used uTP,
    # which also checks our hardcoded UTP_SOCKET bit (the GUI's "Transport").
    assert transfer(tmp_path, tcp=False) & UTP_SOCKET


def test_tcp_only_has_no_utp_flag(tmp_path):
    flags = transfer(tmp_path, utp=False)
    assert flags and not flags & UTP_SOCKET


def test_required_encryption_is_rc4(tmp_path):
    flags = transfer(tmp_path, encryption="require")
    assert flags & int(lt.peer_info.rc4_encrypted)


def test_disabled_encryption_is_plaintext(tmp_path):
    flags = transfer(tmp_path, encryption="disable")
    assert flags and not flags & ENCRYPTED


def test_resume_data_survives_restart(tmp_path):
    data = tmp_path / "a" / "data"
    data.mkdir(parents=True)
    tfile = make_torrent(data, tmp_path / "t.torrent", size=256 * 1024)

    first = engine(tmp_path, "a")
    first.add(str(tfile))
    wait_for(first, lambda: first.handles and first.statuses()[0].is_seeding)
    first.shutdown()
    first = None  # release the session before reopening the same state dir

    saved = saved_torrents(tmp_path / "a" / "state")
    assert len(saved) == 1 and saved[0][1].ti.name() == "payload.bin"

    second = engine(tmp_path, "a")
    assert second.resume_all() == 1
    wait_for(second, lambda: second.handles and second.statuses()[0].is_seeding)
    second.shutdown()

    key = saved[0][0]
    assert forget(tmp_path / "a" / "state", key[:8]) == [key]
    assert saved_torrents(tmp_path / "a" / "state") == []


def test_magnet_is_saved_before_metadata(tmp_path):
    eng = engine(tmp_path, "m")
    ih = "c9e15763f722f23e98a29decdfae341b98d53056"
    eng.add(f"magnet:?xt=urn:btih:{ih}&dn=test")
    wait_for(eng, lambda: (tmp_path / "m" / "state" / "torrents" / f"{ih}.resume").exists())
    eng.shutdown()


def test_bad_source_rejected(tmp_path):
    eng = engine(tmp_path, "x")
    with pytest.raises(ValueError):
        eng.add(str(tmp_path / "missing.torrent"))


def test_alerts_for_removed_torrents_are_harmless(tmp_path):
    """Removing a torrent before its pending alerts are handled must not
    break alert processing (seen when a torrent is removed as it finishes)."""
    data = tmp_path / "a" / "data"
    data.mkdir(parents=True)
    tfile = make_torrent(data, tmp_path / "t.torrent", size=256 * 1024)
    eng = engine(tmp_path, "a")
    eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles and eng.statuses()[0].is_seeding)
    (h,) = eng.handles.values()
    h.force_recheck()  # queues more alerts for this torrent...
    eng.remove(h)      # ...which arrive after it is gone
    eng.pump(1.0)
    eng.pump(0.5)
    assert eng.handles == {}
    assert list((tmp_path / "a" / "state" / "torrents").glob("*.resume")) == []
    eng.shutdown()


def seeding_pair(tmp_path, size=2 * 1024 * 1024, files=None):
    """A seeder with a finished torrent and an empty leecher, both on loopback."""
    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    if files:
        folder = seed_dir / "pack"
        folder.mkdir()
        for name, n in files.items():
            (folder / name).write_bytes(os.urandom(n))
        fs = lt.file_storage()
        lt.add_files(fs, str(folder))
        ct = lt.create_torrent(fs)
        lt.set_piece_hashes(ct, str(seed_dir))
        tfile = tmp_path / "t.torrent"
        tfile.write_bytes(lt.bencode(ct.generate()))
    else:
        tfile = make_torrent(seed_dir, tmp_path / "t.torrent", size=size)
    seeder = engine(tmp_path, "seeder")
    leecher = engine(tmp_path, "leecher")
    seeder.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and seeder.statuses()[0].is_seeding)
    return seeder, leecher, tfile


def test_magnet_waits_for_file_choice(tmp_path):
    seeder, leecher, tfile = seeding_pair(
        tmp_path, files={"keep.bin": 300_000, "skip.bin": 300_000})
    magnet = lt.make_magnet_uri(lt.torrent_info(str(tfile)))
    key = leecher.add_params(lt.parse_magnet_uri(magnet), choose_files=True)
    wait_for(leecher, lambda: leecher.handles, others=[seeder])
    leecher.handles[key].connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(leecher, lambda: key in leecher.files_ready, others=[seeder])

    h = leecher.handles[key]
    assert set(h.get_file_priorities()) == {0}  # nothing downloads until chosen
    fs = h.torrent_file().files()
    keep = next(i for i in range(fs.num_files()) if fs.file_path(i).endswith("keep.bin"))
    h.prioritize_files([4 if i == keep else 0 for i in range(fs.num_files())])
    wait_for(leecher, lambda: leecher.statuses()[0].is_finished, others=[seeder])
    assert (tmp_path / "leecher" / "data" / "pack" / "keep.bin").stat().st_size == 300_000
    skipped = tmp_path / "leecher" / "data" / "pack" / "skip.bin"
    assert not skipped.exists() or skipped.stat().st_size < 300_000 or not any(skipped.read_bytes())
    leecher.shutdown()
    seeder.shutdown()


def test_seeding_time_limit_stops_seeding(tmp_path):
    data = tmp_path / "a" / "data"
    data.mkdir(parents=True)
    tfile = make_torrent(data, tmp_path / "t.torrent", size=64 * 1024)
    eng = engine(tmp_path, "a", seed_hours=1 / 3600)  # one second
    eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles and eng.statuses()[0].is_seeding)

    def stopped():
        eng.enforce_seeding_limits()
        st = eng.statuses()[0]
        return bool(st.flags & lt.torrent_flags.paused) and not st.flags & lt.torrent_flags.auto_managed

    wait_for(eng, stopped, timeout=15)
    eng.shutdown()


def test_queue_limits_reach_libtorrent(tmp_path):
    eng = engine(tmp_path, "q", active_downloads=7, active_seeds=-1)
    s = eng.ses.get_settings()
    assert (s["active_downloads"], s["active_seeds"], s["active_limit"]) == (7, -1, -1)


def test_watch_folder_adds_and_marks_files(tmp_path):
    watch = tmp_path / "watch"
    watch.mkdir()
    (tmp_path / "src").mkdir()
    make_torrent(tmp_path / "src", watch / "good.torrent", size=64 * 1024)
    (watch / "broken.torrent").write_bytes(b"not bencoded")
    eng = engine(tmp_path, "w", watch_dir=watch)
    assert eng.scan_watch_dir() == ["payload.bin"]
    assert sorted(p.name for p in watch.iterdir()) == ["broken.torrent.invalid", "good.torrent.added"]
    assert eng.scan_watch_dir() == []  # each file is picked up once
    wait_for(eng, lambda: eng.handles)
    eng.shutdown()


def test_move_sequential_and_per_torrent_limits(tmp_path):
    data = tmp_path / "a" / "data"
    data.mkdir(parents=True)
    tfile = make_torrent(data, tmp_path / "t.torrent", size=64 * 1024)
    eng = engine(tmp_path, "a")
    eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles and eng.statuses()[0].is_seeding)
    (h,) = eng.handles.values()

    eng.set_sequential(h, True)
    assert h.flags() & lt.torrent_flags.sequential_download
    eng.set_limits(h, 100 * 1024, 50 * 1024)
    assert (h.download_limit(), h.upload_limit()) == (100 * 1024, 50 * 1024)
    eng.set_limits(h, 0, 0)
    assert h.download_limit() <= 0 and h.upload_limit() <= 0

    target = tmp_path / "elsewhere"
    eng.move(h, target)
    wait_for(eng, lambda: (target / "payload.bin").exists() and h.status().save_path == str(target))
    assert not (data / "payload.bin").exists()
    eng.shutdown()


def throttle(eng):
    """Rate limits normally skip loopback peers; make them apply."""
    everyone = lt.ip_filter()
    everyone.add_rule("0.0.0.0", "255.255.255.255", 1 << eng.ses.global_peer_class_id)
    eng.ses.set_peer_class_filter(everyone)


def test_unfinished_downloads_use_their_own_folder(tmp_path):
    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent", size=1024 * 1024)
    seeder = engine(tmp_path, "seeder", upload_limit=256 * 1024)
    throttle(seeder)
    seeder.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and seeder.statuses()[0].is_seeding)

    staging, final, later = tmp_path / "unfinished", tmp_path / "leecher" / "data", tmp_path / "films"
    leecher = engine(tmp_path, "leecher", incomplete_dir=staging)
    key = leecher.add(str(tfile))
    wait_for(leecher, lambda: leecher.handles, others=[seeder])
    h = leecher.handles[key]
    assert h.status().save_path == str(staging) and leecher.destination(h) == final
    # "Move to" on an unfinished download only changes where it will end up
    leecher.move(h, later)
    assert h.status().save_path == str(staging) and leecher.destination(h) == later

    # The destination is kept in the resume file, so it survives a restart
    resume = tmp_path / "leecher" / "state" / "torrents" / f"{key}.resume"
    wait_for(leecher, lambda: resume.exists() and b"avilys-destination" in resume.read_bytes())
    leecher.shutdown()
    leecher = None
    leecher = engine(tmp_path, "leecher", incomplete_dir=staging)
    assert leecher.resume_all() == 1
    wait_for(leecher, lambda: leecher.handles, others=[seeder])
    h = leecher.handles[key]
    assert leecher.destination(h) == later

    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(leecher, lambda: (later / "payload.bin").exists() and h.status().save_path == str(later),
             others=[seeder])
    assert (later / "payload.bin").read_bytes() == (seed_dir / "payload.bin").read_bytes()
    assert not (staging / "payload.bin").exists()
    wait_for(leecher, lambda: b"avilys-destination" not in resume.read_bytes())
    leecher.shutdown()
    seeder.shutdown()


def test_finished_files_already_in_the_save_folder_stay_there(tmp_path):
    data = tmp_path / "a" / "data"
    data.mkdir(parents=True)
    tfile = make_torrent(data, tmp_path / "t.torrent", size=64 * 1024)
    eng = engine(tmp_path, "a", incomplete_dir=tmp_path / "unfinished")
    eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles and eng.statuses()[0].is_seeding)
    assert eng.statuses()[0].save_path == str(data)
    eng.shutdown()


def test_reachable_from_outside(tmp_path):
    eng = engine(tmp_path, "r")
    assert eng.reachable() is None                    # nothing known yet
    eng._note_connections(incoming=False, peers=4, now=1000.0)
    assert eng.reachable(now=1060.0) is None          # give it a few minutes
    assert eng.reachable(now=1000.0 + 181) is False   # peers, but none came to us
    eng._note_connections(incoming=False, peers=0, now=1200.0)
    assert eng.reachable(now=5000.0) is None          # no peers: nothing to judge by
    eng._note_connections(incoming=True, peers=3, now=5000.0)
    assert eng.reachable() is True
    # The real counters replace what we fed in: nobody has connected to this session
    def counted():
        eng.request_stats()
        return eng.incoming is False

    wait_for(eng, counted)
    assert eng.reachable() is None
    eng.shutdown()


def assert_same_file(got: Path, want: Path, piece: int = 64 * 1024) -> None:
    """Compare two files, saying which pieces differ instead of dumping them."""
    a, b = got.read_bytes(), want.read_bytes()
    assert len(a) == len(b), f"{got.name}: {len(a)} bytes, expected {len(b)}"
    bad = [i // piece for i in range(0, len(b), piece) if a[i:i + piece] != b[i:i + piece]]
    empty = [i for i in bad if not any(a[i * piece:(i + 1) * piece])]
    assert not bad, f"{got.name}: pieces {bad} differ (all zeros: {empty})"


def blocked_download(tmp_path, name="e"):
    """A download that can't be written: a folder sits where its file belongs.
    Linux notices when it checks the files, Windows when the first data arrives,
    so a seeder supplies some. Returns the engine, the folder and the seeder."""
    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent", size=256 * 1024)
    seeder = engine(tmp_path, "seeder")
    seeder.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and seeder.statuses()[0].is_seeding)
    eng = engine(tmp_path, name)
    blocker = eng.cfg.save_path / "payload.bin"
    blocker.mkdir()
    key = eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles, others=[seeder])
    eng.handles[key].connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    return eng, blocker, seeder


def test_error_stops_a_torrent_and_trying_again_recovers(tmp_path):
    from avilys import display
    from avilys.engine import has_error

    eng, blocker, seeder = blocked_download(tmp_path)
    # The status can show the stop a moment before the event naming the file is read
    wait_for(eng, lambda: has_error(eng.statuses()[0]) and eng.error_file(eng.statuses()[0]), others=[seeder])
    st = eng.statuses()[0]
    assert eng.error_text(st) and display.state_name(st) == "error"
    assert eng.error_file(st) == "payload.bin"
    # Linux fails checking the files (an error state: paused). Windows fails
    # writing, which libtorrent answers by quietly not downloading any more.
    assert st.flags & lt.torrent_flags.paused or st.flags & lt.torrent_flags.upload_mode

    blocker.rmdir()  # the user fixes the problem...
    (h,) = eng.handles.values()
    eng.resume(h)    # ...and tries again
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(eng, lambda: h.status().is_seeding, others=[seeder])
    assert eng.error_text(h.status()) == "" and not has_error(h.status())
    eng.shutdown()
    seeder.shutdown()
    assert_same_file(blocker, tmp_path / "seeder" / "data" / "payload.bin")


@pytest.mark.skipif(not Path("/dev/full").exists(), reason="needs /dev/full, a file that refuses writes")
def test_write_error_while_downloading_recovers(tmp_path):
    """The other way to fail: the files check out, then writing fails mid-download."""
    from avilys.engine import has_error

    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent", size=512 * 1024)
    seeder = engine(tmp_path, "seeder")
    seeder.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and seeder.statuses()[0].is_seeding)
    eng = engine(tmp_path, "e")
    target = eng.cfg.save_path / "payload.bin"
    os.symlink("/dev/full", target)
    key = eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles, others=[seeder])
    h = eng.handles[key]
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(eng, lambda: has_error(h.status()), others=[seeder])
    assert h.status().state == lt.torrent_status.states.downloading and eng.error_text(h.status())

    target.unlink()
    eng.resume(h)
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(eng, lambda: h.status().is_seeding, others=[seeder])
    assert target.read_bytes() == (seed_dir / "payload.bin").read_bytes()
    eng.shutdown()
    seeder.shutdown()


def test_failed_write_that_only_stops_the_download_is_an_error_too(tmp_path):
    """A full disk or a folder we may not write to doesn't put the torrent in
    libtorrent's error state: it just stops downloading ("upload mode"). That
    must still show as an error, with the reason, and be retryable."""
    resource = pytest.importorskip("resource")  # not on Windows; the folder test covers it there
    import signal

    from avilys import display
    from avilys.engine import describe_error, error_text, has_error

    seed_dir = tmp_path / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, tmp_path / "t.torrent", size=512 * 1024)
    seeder = engine(tmp_path, "seeder")
    seeder.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and seeder.statuses()[0].is_seeding)
    eng = engine(tmp_path, "e")
    key = eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles, others=[seeder])
    h = eng.handles[key]

    # Stand in for a full disk: this process may not write files past 64 KiB.
    old_signal = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024, limit[1]))
    try:
        h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
        wait_for(eng, lambda: has_error(h.status()) and key in eng.disk_errors, others=[seeder])
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, limit)
        signal.signal(signal.SIGXFSZ, old_signal)
    st = h.status()
    assert display.state_name(st) == "error" and eng.error_text(st)
    # Nearly always the quiet kind. Now and then the size limit trips some other
    # disk operation first and libtorrent sets a real error; both must recover.
    if not st.errc.value():
        assert st.flags & lt.torrent_flags.upload_mode
        assert eng.error_text(st) == describe_error(*eng.disk_errors[key])  # the failed write explains it
        assert "too large" in eng.error_text(st).lower()
        assert error_text(st) == "Couldn't write to the save folder"  # without the reason, e.g. after a restart

    eng.resume(h)
    assert key not in eng.disk_errors
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(eng, lambda: h.status().is_seeding, others=[seeder])
    assert not has_error(h.status())
    assert (eng.cfg.save_path / "payload.bin").read_bytes() == (seed_dir / "payload.bin").read_bytes()
    eng.shutdown()
    seeder.shutdown()


def test_errors_are_described_plainly():
    import errno

    from avilys.engine import describe_error

    assert describe_error(errno.ENOSPC, "system", "No space left on device", windows=False) == "The disk is full"
    assert describe_error(112, "system", "There is not enough space on the disk", windows=True) == "The disk is full"
    assert describe_error(errno.EACCES, "generic", "Permission denied", windows=True) == \
        "Avilys isn't allowed to write to the save folder"
    assert describe_error(5, "system", "Access is denied", windows=True) == \
        "Avilys isn't allowed to write to the save folder"
    assert describe_error(errno.ENOENT, "system", "No such file or directory", windows=False) == "Files are missing"
    # Windows code 112 means something else elsewhere: don't guess
    assert describe_error(112, "system", "host is down", windows=False) == "Host is down"
    assert describe_error(7, "libtorrent", "", windows=False) == "Error 7"


def what_others_see(tmp_path, name, **overrides):
    """Download from a seeder and announce to a tracker; return the client
    names and peer-id prefixes the seeder saw, and the tracker's User-Agents."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    agents = []

    class Tracker(BaseHTTPRequestHandler):
        def do_GET(self):
            agents.append(self.headers.get("User-Agent"))
            body = lt.bencode({"interval": 1800, "peers": b""})
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    tracker = HTTPServer(("127.0.0.1", 0), Tracker)
    threading.Thread(target=tracker.serve_forever, daemon=True).start()

    root = tmp_path / name
    seed_dir = root / "seeder" / "data"
    seed_dir.mkdir(parents=True)
    tfile = make_torrent(seed_dir, root / "t.torrent", size=1024 * 1024)
    seeder = engine(root, "seeder", upload_limit=128 * 1024)
    throttle(seeder)  # slow, so the connection lasts long enough to look at
    seeder.add(str(tfile))
    wait_for(seeder, lambda: seeder.handles and seeder.statuses()[0].is_seeding)
    (sh,) = seeder.handles.values()

    leecher = engine(root, "leecher", **overrides)
    key = leecher.add(str(tfile))
    wait_for(leecher, lambda: leecher.handles, others=[seeder])
    h = leecher.handles[key]
    leecher.add_tracker(h, f"http://127.0.0.1:{tracker.server_address[1]}/announce")
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    clients, ids = set(), set()

    def looked():
        for p in sh.get_peer_info():
            clients.add(p.client.decode(errors="replace") if isinstance(p.client, bytes) else p.client)
            ids.add(bytes.fromhex(str(p.pid))[:8])
        return agents and leecher.statuses()[0].is_seeding

    wait_for(leecher, looked, others=[seeder])
    leecher.shutdown()
    seeder.shutdown()
    tracker.shutdown()
    tracker.server_close()
    return clients, ids, agents


def test_anonymous_mode_hides_the_client(tmp_path):
    from avilys.engine import FINGERPRINT

    # Normally peers and trackers are told it's Avilys, and the peer id says libtorrent
    clients, ids, agents = what_others_see(tmp_path, "normal")
    assert any(c.startswith("avilys/") for c in clients)
    assert ids == {FINGERPRINT.encode()}
    assert agents and all(a.startswith("avilys/") for a in agents)

    clients, ids, agents = what_others_see(tmp_path, "anonymous", anonymous=True)
    assert clients and not any("avilys" in c.lower() or "libtorrent" in c.lower() for c in clients)
    assert ids and FINGERPRINT.encode() not in ids
    # libtorrent gives trackers a generic name instead of ours
    assert agents and not any("avilys" in (a or "").lower() or "libtorrent" in (a or "").lower() for a in agents)

    # The switch applies while running
    eng = engine(tmp_path, "live")
    assert not eng.ses.get_settings()["anonymous_mode"]
    eng.apply_config(Config(**{**eng.cfg.__dict__, "anonymous": True}))
    s = eng.ses.get_settings()
    assert s["anonymous_mode"] and s["peer_fingerprint"] == ""
    eng.apply_config(Config(**{**eng.cfg.__dict__, "anonymous": False}))
    s = eng.ses.get_settings()
    assert not s["anonymous_mode"] and s["peer_fingerprint"] == FINGERPRINT
    eng.shutdown()


def test_mark_of_the_web_format(tmp_path):
    from avilys.engine import mark_downloaded

    f = tmp_path / "setup.exe"
    f.write_bytes(b"MZ")
    assert not mark_downloaded(f, windows=False)
    # On Windows this is an alternate data stream of the file; elsewhere the
    # same name is an ordinary file, which is enough to check what is written.
    assert mark_downloaded(f, windows=True)
    with open(f"{f}:Zone.Identifier", newline="") as zone:
        assert zone.read() == "[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=about:internet\r\n"
    assert f.read_bytes() == b"MZ"  # the file itself is untouched


def test_finished_files_are_marked_as_downloaded(tmp_path):
    """Every file of a torrent is marked once complete, so Windows warns before
    a downloaded program runs; files not downloaded are left alone."""
    seeder, leecher, tfile = seeding_pair(tmp_path, files={"song.flac": 300_000, "setup.exe": 200_000,
                                                          "skipped.txt": 100_000})
    marked = []
    leecher.marker = lambda path: marked.append(Path(path).name) or True
    atp = lt.add_torrent_params()
    atp.ti = lt.torrent_info(str(tfile))
    fs = atp.ti.files()
    names = [Path(fs.file_path(i)).name for i in range(fs.num_files())]
    atp.file_priorities = [0 if n == "skipped.txt" else 4 for n in names]
    key = leecher.add_params(atp)
    wait_for(leecher, lambda: key in leecher.handles, others=[seeder])
    h = leecher.handles[key]
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(leecher, lambda: h.status().is_finished and {"song.flac", "setup.exe"} <= set(marked),
             others=[seeder])
    assert "skipped.txt" not in marked and not any(n.startswith(".pad") for n in marked)
    leecher.shutdown()
    seeder.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Mark of the Web is a Windows (NTFS) feature")
def test_downloads_carry_the_mark_of_the_web_on_windows(tmp_path):
    seeder, leecher, tfile = seeding_pair(tmp_path, size=256 * 1024)
    leecher.add(str(tfile))
    wait_for(leecher, lambda: leecher.handles, others=[seeder])
    (h,) = leecher.handles.values()
    h.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    zone = tmp_path / "leecher" / "data" / "payload.bin:Zone.Identifier"
    wait_for(leecher, lambda: h.status().is_seeding and os.path.exists(zone), others=[seeder])
    with open(zone) as f:
        assert "ZoneId=3" in f.read()
    leecher.shutdown()
    seeder.shutdown()
