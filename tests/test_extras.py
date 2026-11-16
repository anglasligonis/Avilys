"""Country lookup, IP blocklist, slow mode, interface binding and trackers."""

from __future__ import annotations

import gzip
import time
from pathlib import Path

import pytest

from avilys import geoip
from avilys.engine import Config, build_settings, in_window, read_blocklist
from test_engine import engine, make_torrent, wait_for

mmdb_writer = pytest.importorskip("mmdb_writer")
netaddr = pytest.importorskip("netaddr")


def make_country_db(path: Path, networks: dict[str, tuple[str, str]]) -> Path:
    w = mmdb_writer.MMDBWriter(ip_version=6, database_type="DBIP-Country-Lite", ipv4_compatible=True)
    for net, (code, name) in networks.items():
        w.insert_network(netaddr.IPSet([net]), {"country": {"iso_code": code, "names": {"en": name}}})
    w.to_db_file(str(path))
    return path


def test_country_lookup(tmp_path):
    db = make_country_db(tmp_path / "bundled.mmdb", {"203.0.113.0/24": ("LT", "Lithuania"),
                                                     "2001:db8::/32": ("DE", "Germany")})
    g = geoip.GeoIP(tmp_path / "state", bundled=db)
    assert g.available and not g.needs_update()
    assert g.country("203.0.113.9") == ("lt", "Lithuania")
    assert g.country("2001:db8::1") == ("de", "Germany")
    assert g.country("198.51.100.1") is None
    assert g.country("not an ip") is None


def test_no_database_means_no_flags(tmp_path):
    g = geoip.GeoIP(tmp_path / "state", bundled=tmp_path / "missing.mmdb")
    assert not g.available and g.needs_update()
    assert g.country("203.0.113.9") is None


def test_download_falls_back_to_last_month(tmp_path, monkeypatch):
    src = make_country_db(tmp_path / "src.mmdb", {"203.0.113.0/24": ("LT", "Lithuania")})
    this_month, last_month = geoip.months_to_try()
    (tmp_path / f"db-{last_month}.mmdb.gz").write_bytes(gzip.compress(src.read_bytes()))
    monkeypatch.setattr(geoip, "URL", tmp_path.as_uri() + "/db-{month}.mmdb.gz")
    g = geoip.GeoIP(tmp_path / "state", bundled=tmp_path / "missing.mmdb")
    geoip.download(g.downloaded)
    g.reload()
    assert g.country("203.0.113.1") == ("lt", "Lithuania")


def test_months_roll_over_the_year():
    jan = time.strptime("2027-01-02", "%Y-%m-%d")
    assert geoip.months_to_try(jan) == ["2027-01", "2026-12"]


def test_blocklist_formats(tmp_path):
    text = "\n".join([
        "# comment",
        "Bad Org:1.2.3.0-1.2.3.255",                         # P2P
        "005.006.007.000 - 005.006.007.255 , 000 , eMule",   # DAT, blocked
        "009.009.009.000 - 009.009.009.255 , 200 , allowed",  # DAT, level > 127: allowed
        "10.0.0.0/8",                                        # CIDR
        "192.0.2.7",                                         # single address
        "garbage line",
    ])
    plain = tmp_path / "list.p2p"
    plain.write_text(text)
    gz = tmp_path / "list.gz"
    gz.write_bytes(gzip.compress(text.encode()))
    expected = [("1.2.3.0", "1.2.3.255"), ("5.6.7.0", "5.6.7.255"), ("10.0.0.0", "10.255.255.255"),
                ("192.0.2.7", "192.0.2.7")]
    assert read_blocklist(plain) == expected
    assert read_blocklist(gz) == expected

    eng = engine(tmp_path, "b", blocklist=plain)
    assert eng.blocked_ranges == 4
    f = eng.ses.get_ip_filter()
    assert f.access("1.2.3.4") == 1 and f.access("10.20.30.40") == 1 and f.access("8.8.8.8") == 0


def test_slow_mode_and_schedule(tmp_path):
    at = lambda hhmm: time.strptime(f"2026-11-15 {hhmm}", "%Y-%m-%d %H:%M")  # noqa: E731
    assert in_window("08:00", "23:00", at("12:00")) and not in_window("08:00", "23:00", at("23:30"))
    assert in_window("22:00", "06:00", at("23:30")) and in_window("22:00", "06:00", at("05:59"))
    assert not in_window("22:00", "06:00", at("12:00"))

    eng = engine(tmp_path, "s", download_limit=0, alt_download_limit=100 * 1024, alt_upload_limit=10 * 1024)
    assert eng.ses.get_settings()["download_rate_limit"] == 0
    eng.apply_config(Config(**{**eng.cfg.__dict__, "alt_enabled": True}))
    s = eng.ses.get_settings()
    assert eng.slow and (s["download_rate_limit"], s["upload_rate_limit"]) == (100 * 1024, 10 * 1024)
    eng.apply_config(Config(**{**eng.cfg.__dict__, "alt_enabled": False}))
    assert not eng.update_speed_mode() and eng.ses.get_settings()["download_rate_limit"] == 0


def test_bind_to_interface():
    cfg = Config(state_dir=Path("."), save_path=Path("."), listen="0.0.0.0:51413,[::]:51413", interface="wg0")
    s = build_settings(cfg)
    assert s["listen_interfaces"] == "wg0:51413" and s["outgoing_interfaces"] == "wg0"
    s = build_settings(Config(state_dir=Path("."), save_path=Path(".")))
    assert s["outgoing_interfaces"] == "" and s["listen_interfaces"].startswith("0.0.0.0:")


def test_add_and_remove_trackers(tmp_path):
    data = tmp_path / "a" / "data"
    data.mkdir(parents=True)
    tfile = make_torrent(data, tmp_path / "t.torrent", size=64 * 1024)
    eng = engine(tmp_path, "a")
    eng.add(str(tfile))
    wait_for(eng, lambda: eng.handles)
    (h,) = eng.handles.values()
    eng.add_tracker(h, "udp://tracker.example.org:1337/announce")
    eng.add_tracker(h, "https://tracker.example.net/announce")
    assert [t["url"] for t in h.trackers()] == ["udp://tracker.example.org:1337/announce",
                                                "https://tracker.example.net/announce"]
    with pytest.raises(ValueError):
        eng.add_tracker(h, "not a url")
    eng.remove_tracker(h, "udp://tracker.example.org:1337/announce")
    assert [t["url"] for t in h.trackers()] == ["https://tracker.example.net/announce"]
    eng.shutdown()
