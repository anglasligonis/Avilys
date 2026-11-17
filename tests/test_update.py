"""The update check: version comparison, and reading GitHub's answer (from a
local stand-in server, so the tests stay offline)."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from avilys import update


def test_versions_compare_as_numbers():
    assert update.parse_version("v1.10.0") == (1, 10, 0)
    assert update.parse_version("1.2") == (1, 2)
    assert update.parse_version("nightly") is None and update.parse_version("v1.2.0-beta") is None
    assert update.is_newer("v1.10.0", "1.9.3")      # not compared as text
    assert update.is_newer("1.2", "1.1.9")
    assert not update.is_newer("1.2", "1.2.0")       # the same version, written two ways
    assert not update.is_newer("1.0.1", "1.1.0")
    assert not update.is_newer("garbage", "1.0.0")


@contextmanager
def fake_github(answer, status=200):
    """Serves `answer` as JSON for any request; yields (url, request headers seen)."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append({**dict(self.headers), "_from": self.client_address[0]})
            body = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/releases/latest", seen
    finally:
        server.shutdown()
        server.server_close()


def release(tag="v1.2.0", **extra):
    return {"tag_name": tag, "html_url": f"{update.RELEASES_PAGE}/tag/{tag}",
            "draft": False, "prerelease": False, **extra}


def test_reads_the_latest_release():
    with fake_github(release()) as (url, seen):
        got = update.fetch_latest(url)
    assert got == update.Release("1.2.0", f"{update.RELEASES_PAGE}/tag/v1.2.0")
    # Only what any browser would send: no identifiers, nothing about torrents
    assert seen[0]["User-Agent"] == "Avilys"
    assert not any(k.lower() in ("cookie", "authorization") for k in seen[0])


def test_links_only_to_our_own_releases_page():
    with fake_github(release(html_url="https://example.com/download")) as (url, _):
        assert update.fetch_latest(url).url == update.RELEASES_PAGE


@pytest.mark.parametrize("answer, status", [
    (release(draft=True), 200),
    (release(prerelease=True), 200),
    (release(tag="latest-nightly"), 200),
    ({"message": "Not Found"}, 404),  # no releases yet
    ({"message": "API rate limit exceeded"}, 403),
])
def test_no_usable_release_is_an_error(answer, status):
    with fake_github(answer, status) as (url, _):
        with pytest.raises(RuntimeError):
            update.fetch_latest(url)


def test_offline_is_an_error():
    with pytest.raises(RuntimeError):
        update.fetch_latest("http://127.0.0.1:9/releases/latest", timeout=2)  # nothing listens on port 9


def test_bound_to_an_adapter_the_check_leaves_only_through_it():
    """With "Use only this network adapter", the check is sent from that
    adapter's address. If the address isn't there (VPN down), it fails
    rather than going out some other way."""
    with fake_github(release()) as (url, seen):
        assert update.fetch_latest(url, source_address="127.0.0.2").version == "1.2.0"
        assert seen[-1]["_from"] == "127.0.0.2"
        with pytest.raises(RuntimeError):
            update.fetch_latest(url, timeout=2, source_address="192.0.2.1")  # not an address of ours
        assert len(seen) == 1


def test_no_check_while_the_chosen_adapter_is_down():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from avilys.gui.app import make_app
    from avilys.gui.updates import UpdateChecker
    from avilys.net import AdapterNotConnected

    app = make_app([])
    checker = UpdateChecker()
    got = []
    checker.finished.connect(lambda *a: got.append(a))
    with fake_github(release()) as (url, seen):
        checker.url = url

        def down():
            raise AdapterNotConnected("network adapter wg0 isn't connected")

        checker.source = down
        checker.check(manual=True)
        app.processEvents()
        assert got == [(None, "network adapter wg0 isn't connected", True)] and seen == []
        assert not checker.busy
