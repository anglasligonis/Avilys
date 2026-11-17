"""Regression tests for untrusted torrents, metadata and terminal output."""

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

import libtorrent as lt
import pytest

from avilys import cli, config, display
from avilys.engine import ALERT_MASK, CHOOSE_KEY, Config, build_settings
from test_engine import engine, seeding_pair, wait_for


@pytest.mark.parametrize("staged", [False, True])
def test_download_preserves_an_existing_file(tmp_path, staged):
    seeder, leecher, torrent = seeding_pair(tmp_path)
    existing = leecher.cfg.save_path / "payload.bin"
    existing.write_bytes(b"user data")
    if staged:
        leecher.apply_config(replace(leecher.cfg, incomplete_dir=tmp_path / "unfinished"))
    key = leecher.add(str(torrent))
    wait_for(leecher, lambda: key in leecher.handles, others=[seeder])
    handle = leecher.handles[key]
    destination = leecher.destination(handle)
    assert destination.parent == existing.parent
    if staged:
        # Also protect a file placed at the destination while downloading.
        (destination / "payload.bin").write_bytes(b"arrived later")
    handle.connect_peer(("127.0.0.1", seeder.ses.listen_port()))
    wait_for(leecher, lambda: handle.status().is_seeding, others=[seeder])
    if staged:
        wait_for(leecher, lambda: any("couldn't move files" in event for event in leecher.events))
        assert (destination / "payload.bin").read_bytes() == b"arrived later"
    downloaded = Path(handle.status().save_path) / "payload.bin"
    assert downloaded.read_bytes() == (seeder.cfg.save_path / "payload.bin").read_bytes()
    assert existing.read_bytes() == b"user data"
    leecher.shutdown()
    seeder.shutdown()


@pytest.mark.parametrize("restart_at", ["before metadata", "after metadata", "legacy resume"])
def test_pending_file_choice_survives_restart(tmp_path, restart_at):
    seeder, leecher, torrent = seeding_pair(tmp_path, files={"keep.bin": 65536, "skip.bin": 65536})
    # A v1-only magnet acquires a v2 hash when it fetches hybrid metadata.
    magnet = f"magnet:?xt=urn:btih:{lt.torrent_info(str(torrent)).info_hashes().v1}"
    key = leecher.add_params(lt.parse_magnet_uri(magnet), choose_files=True)
    peer = ("127.0.0.1", seeder.ses.listen_port())
    wait_for(leecher, lambda: key in leecher.handles, others=[seeder])
    if restart_at == "after metadata":
        leecher.handles[key].connect_peer(peer)
        wait_for(leecher, lambda: bool(leecher.files_ready), others=[seeder])
    leecher.shutdown()
    if restart_at == "legacy resume":
        (resume_file,) = leecher.torrents_dir.glob("*.resume")
        entry = lt.bdecode(resume_file.read_bytes())
        del entry[CHOOSE_KEY]
        resume_file.write_bytes(lt.bencode(entry))
    del leecher

    leecher = engine(tmp_path, "leecher")
    assert leecher.resume_all() == 1
    wait_for(leecher, lambda: bool(leecher.handles), others=[seeder])
    (handle,) = leecher.handles.values()
    handle.connect_peer(peer)
    wait_for(leecher, lambda: bool(leecher.files_ready), others=[seeder])
    assert len(leecher.handles) == 1
    assert set(handle.get_file_priorities()) == {0}
    assert handle.status().total_done == 0
    files = handle.torrent_file().files()
    leecher.choose_files(handle, [4 if files.file_path(i).endswith("keep.bin") else 0
                                  for i in range(files.num_files())])
    wait_for(leecher, lambda: handle.status().is_finished and not leecher.has_pending_file_choices(),
             others=[seeder])
    assert (Path(handle.status().save_path) / "pack" / "keep.bin").exists()
    leecher.shutdown()
    del leecher

    leecher = engine(tmp_path, "leecher")
    assert leecher.resume_all() == 1
    wait_for(leecher, lambda: bool(leecher.handles), others=[seeder])
    assert not leecher.has_pending_file_choices()
    leecher.shutdown()
    seeder.shutdown()


@pytest.mark.parametrize("redirect", [False, True])
def test_tracker_requests_obey_ip_filter(tmp_path, redirect):
    requests = []

    class Tracker(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if redirect:
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.2:{self.server.server_port}/announce")
                self.end_headers()
                return
            body = lt.bencode({"interval": 120, "peers": b""})
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Tracker) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            tracker = f"http://localhost:{server.server_port}/announce"
            magnet = "magnet:?xt=urn:btih:c9e15763f722f23e98a29decdfae341b98d53056&tr=" + quote(tracker, safe="")
            opts = {}
            if redirect:
                blocklist = tmp_path / "blocklist"
                blocklist.write_text("127.0.0.2\n")
                opts["blocklist"] = blocklist
            blocked = engine(tmp_path, "blocked", allow_local_network=redirect, **opts)
            ip_filter = blocked.ses.get_ip_filter()
            for address in ("127.0.0.1", "10.20.30.40", "169.254.169.254", "::1", "fe80::1", "fd00::1"):
                assert ip_filter.access(address) == (0 if redirect else 1)
            assert ip_filter.access("8.8.8.8") == 0
            blocked.ses.apply_settings({"alert_mask": int(ALERT_MASK | lt.alert_category.tracker)})
            errors = []
            handle_alert = blocked._handle_alert

            def capture(alert):
                if isinstance(alert, lt.tracker_error_alert):
                    errors.append(alert.message())
                handle_alert(alert)

            blocked._handle_alert = capture
            blocked.add(magnet)
            wait_for(blocked, lambda: any("IP filter" in error for error in errors))
            blocked.shutdown()
            if redirect:
                assert len(requests) == 1  # the original request reached the permitted tracker
                return
            assert requests == []

            permitted = engine(tmp_path, "allowed", allow_local_network=True)
            permitted.add(magnet)
            wait_for(permitted, lambda: bool(requests))
            assert requests[0].startswith("/announce?")
            permitted.shutdown()
        finally:
            server.shutdown()
            thread.join()


def test_cli_honors_saved_network_adapter(tmp_path, monkeypatch):
    settings = Config(state_dir=tmp_path / "state", save_path=tmp_path / "data", interface="vpn-device")
    config.save(settings)
    used = []

    def capture(cfg):
        used.append(build_settings(cfg))
        raise SystemExit

    monkeypatch.setattr(cli, "Engine", capture)
    with pytest.raises(SystemExit):
        cli.main(["--state-dir", str(settings.state_dir), "start", "--port", "51413"])
    assert used[0]["listen_interfaces"] == "vpn-device:51413"
    assert used[0]["outgoing_interfaces"] == "vpn-device"


def test_terminal_escapes_magnet_name_and_events(tmp_path, capsys):
    eng = engine(tmp_path, "terminal")
    raw = "\x1b[31mtest\x9b31m"
    eng.add("magnet:?xt=urn:btih:c9e15763f722f23e98a29decdfae341b98d53056&dn=" + quote(raw))
    wait_for(eng, lambda: bool(eng.statuses()))
    screen = display.render(eng.statuses(), ["line\r\n\x1b[H"])
    assert "\x1b" not in screen and "\x9b" not in screen and "\r" not in screen
    assert r"\x1b[31mtest" in screen and r"line\x0d\x0a\x1b[H" in screen
    eng.shutdown()

    assert cli.cmd_list(eng.cfg.state_dir) == 0
    listed = capsys.readouterr().out
    assert "\x1b" not in listed and "\x9b" not in listed
    assert r"\x1b[31mtest" in listed
