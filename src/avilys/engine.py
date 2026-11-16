"""A thin layer over a libtorrent session: settings, adding torrents,
alert handling and resume data, so torrents survive a restart."""

from __future__ import annotations

import errno
import gzip
import ipaddress
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import libtorrent as lt

from . import __version__
from .i18n import tr, trn

# name -> (handshake policy, stream encryption level)
ENCRYPTION = {
    "prefer": (lt.enc_policy.pe_enabled, lt.enc_level.both),
    "require": (lt.enc_policy.pe_forced, lt.enc_level.rc4),
    "disable": (lt.enc_policy.pe_disabled, lt.enc_level.plaintext),
}

ALERT_MASK = (
    lt.alert_category.error
    | lt.alert_category.status
    | lt.alert_category.storage
    | lt.alert_category.port_mapping
)


@dataclass
class Config:
    state_dir: Path
    save_path: Path
    listen: str = "0.0.0.0:6881,[::]:6881"
    dht: bool = True
    utp: bool = True
    tcp: bool = True
    lsd: bool = True  # local service discovery (LAN peers)
    port_mapping: bool = True  # UPnP and NAT-PMP
    encryption: str = "prefer"
    download_limit: int = 0  # bytes/s, 0 = unlimited
    upload_limit: int = 0
    seed_ratio: float | None = None  # stop seeding at this ratio; None = seed forever
    seed_hours: float | None = None  # stop seeding after this long; None = no time limit
    active_downloads: int = 3  # queue: torrents downloading at once (-1 = unlimited)
    active_seeds: int = 5      # queue: torrents seeding at once (-1 = unlimited)
    watch_dir: Path | None = None  # .torrent files dropped here are added automatically
    incomplete_dir: Path | None = None  # unfinished downloads live here, then move to their save folder
    # Alternative ("slow mode") speed limits, on by hand or by a daily schedule
    alt_download_limit: int = 500 * 1024
    alt_upload_limit: int = 100 * 1024
    alt_enabled: bool = False
    alt_schedule: bool = False
    alt_from: str = "08:00"
    alt_to: str = "23:00"
    interface: str | None = None  # bind to this network interface (e.g. a VPN adapter)
    blocklist: Path | None = None  # IP blocklist file (P2P, DAT or CIDR lines; may be .gz)
    anonymous: bool = False  # don't tell peers and trackers which client and version this is
    # Desktop-window preferences (the engine ignores these)
    theme: str = "system"  # "system", "light" or "dark"
    language: str = "system"  # "system", or a code from i18n.LANGUAGES ("en", "lt")
    close_to_tray: bool = True
    peer_countries: bool = True  # flags in the Peers tab (monthly db-ip.com download)
    confirm_add: bool = True  # show the add dialog (save folder, files) before adding
    prevent_sleep: bool = True  # keep the computer awake while something is downloading


# Not exported by the 2.0 Python bindings (peer_info::utp_socket is bit 17).
UTP_SOCKET = 1 << 17

DHT_NODES_METRIC = lt.find_metric_idx("dht.dht_nodes")
# The start of our peer id ("-LT20F0-"): it names the client and its version.
FINGERPRINT = lt.default_settings().get("peer_fingerprint", "-LT2000-")
INCOMING_METRIC = lt.find_metric_idx("net.has_incoming_connections")
PEERS_METRIC = lt.find_metric_idx("peer.num_peers_connected")

# Our own key in a torrent's resume file: where its files go once it finishes
# (set while they are still in the folder for unfinished downloads).
DEST_KEY = b"avilys-destination"

# After this long connected to peers with none connecting to us, say so.
UNREACHABLE_AFTER = 180.0


def seconds(value) -> float:
    """The bindings return durations as timedelta or as plain seconds."""
    return value.total_seconds() if hasattr(value, "total_seconds") else float(value)


def share_ratio(st: lt.torrent_status) -> float:
    return st.all_time_upload / max(st.total_done, 1)


def is_stopped(st: lt.torrent_status) -> bool:
    """Paused by the user (not merely waiting in the queue)."""
    return bool(st.flags & lt.torrent_flags.paused) and not st.flags & lt.torrent_flags.auto_managed


def has_error(st: lt.torrent_status) -> bool:
    """Has this torrent stopped because of a problem? libtorrent reports that
    in two ways. Most errors put the torrent in an error state. A failed write
    it thinks may pass (a full disk, no permission) instead switches the
    torrent to "upload mode": no error is set, it just stops downloading."""
    return bool(st.errc.value()) or bool(st.flags & lt.torrent_flags.upload_mode)


# Error numbers worth a plain sentence. Windows reports its own codes in the
# "system" category; everything else uses errno.
_DISK_FULL = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}
_NO_PERMISSION = {errno.EACCES, errno.EPERM, errno.EROFS}
_MISSING = {errno.ENOENT}
_WIN_DISK_FULL = {112, 39}   # ERROR_DISK_FULL, ERROR_HANDLE_DISK_FULL
_WIN_NO_PERMISSION = {5, 19}  # ERROR_ACCESS_DENIED, ERROR_WRITE_PROTECT
_WIN_MISSING = {2, 3}         # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND


def describe_error(value: int, category: str, message: str, windows: bool | None = None) -> str:
    """A plain sentence for a torrent's error; libtorrent's own text otherwise."""
    windows = sys.platform == "win32" if windows is None else windows
    if category == "system" and windows:
        full, denied, missing = _WIN_DISK_FULL, _WIN_NO_PERMISSION, _WIN_MISSING
    elif category in ("system", "generic"):
        full, denied, missing = _DISK_FULL, _NO_PERMISSION, _MISSING
    else:
        full = denied = missing = frozenset()
    if value in full:
        return tr("The disk is full")
    if value in denied:
        return tr("Avilys isn't allowed to write to the save folder")
    if value in missing:
        return tr("Files are missing")
    message = message.strip()
    return message[:1].upper() + message[1:] if message else tr("Error {code}", code=value)


def error_text(st: lt.torrent_status, disk_error: tuple[int, str, str] | None = None) -> str:
    """Why a torrent stopped, or "" if it has no error. `disk_error` is the
    last failed disk operation the engine saw for it: (code, category, message)."""
    if st.errc.value():
        return describe_error(st.errc.value(), st.errc.category().name(), st.errc.message())
    if st.flags & lt.torrent_flags.upload_mode:
        # No error is set in upload mode; the failed write is all we know.
        return describe_error(*disk_error) if disk_error else tr("Couldn't write to the save folder")
    return ""


def listen_port(listen: str) -> int:
    """'0.0.0.0:6881,[::]:6881' -> 6881"""
    try:
        return int(listen.split(",")[0].rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 6881


def in_window(start: str, end: str, now: time.struct_time | None = None) -> bool:
    """Is the time of day inside start..end ("HH:MM")? Windows may cross midnight."""
    now = now or time.localtime()
    try:
        a = [int(x) for x in start.split(":")]
        b = [int(x) for x in end.split(":")]
    except ValueError:
        return False
    t, lo, hi = now.tm_hour * 60 + now.tm_min, a[0] * 60 + a[1], b[0] * 60 + b[1]
    return lo <= t < hi if lo <= hi else (t >= lo or t < hi)


def build_settings(cfg: Config, slow: bool = False) -> dict:
    policy, level = ENCRYPTION[cfg.encryption]
    if cfg.interface:  # only this adapter: if it goes down (VPN off), nothing leaks out another way
        listen = f"{cfg.interface}:{listen_port(cfg.listen)}"
    else:
        listen = cfg.listen
    return {
        "user_agent": f"avilys/{__version__} libtorrent/{lt.__version__}",
        # Anonymous mode: libtorrent stops sending the client name to peers and
        # trackers, and uses a new peer id for every connection. The id's
        # fingerprint is ours to drop, leaving an id that names no client.
        "anonymous_mode": cfg.anonymous,
        "peer_fingerprint": "" if cfg.anonymous else FINGERPRINT,
        "listen_interfaces": listen,
        "outgoing_interfaces": cfg.interface or "",
        "alert_mask": int(ALERT_MASK),
        "enable_dht": cfg.dht,
        "enable_lsd": cfg.lsd,
        "enable_upnp": cfg.port_mapping,
        "enable_natpmp": cfg.port_mapping,
        "enable_outgoing_utp": cfg.utp,
        "enable_incoming_utp": cfg.utp,
        "enable_outgoing_tcp": cfg.tcp,
        "enable_incoming_tcp": cfg.tcp,
        "out_enc_policy": int(policy),
        "in_enc_policy": int(policy),
        "allowed_enc_level": int(level),
        "download_rate_limit": cfg.alt_download_limit if slow else cfg.download_limit,
        "upload_rate_limit": cfg.alt_upload_limit if slow else cfg.upload_limit,
        "active_downloads": cfg.active_downloads,
        "active_seeds": cfg.active_seeds,
        # The overall cap must not be lower than the two limits together.
        "active_limit": -1 if -1 in (cfg.active_downloads, cfg.active_seeds)
        else max(15, cfg.active_downloads + cfg.active_seeds),
    }


def _ip(text: str) -> str:
    """Normalise an address; eMule .dat files write 001.002.003.004."""
    text = text.strip()
    if text.count(".") == 3 and ":" not in text:
        text = ".".join(str(int(p)) for p in text.split("."))
    return str(ipaddress.ip_address(text))


def read_blocklist(path: Path) -> list[tuple[str, str]]:
    """Parse an IP blocklist: P2P ("name:1.2.3.0-1.2.3.255"), eMule DAT
    ("1.2.3.0 - 1.2.3.255 , 000 , name"), CIDR ("1.2.3.0/24") or single IPs.
    Gzipped files work too. Unparseable lines are skipped."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    ranges = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        try:
            if "," in line:  # DAT: range , level , description
                parts = [p.strip() for p in line.split(",")]
                if len(parts) > 1 and parts[1].isdigit() and int(parts[1]) > 127:
                    continue  # level above 127 means "allowed"
                line = parts[0]
            elif ":" in line and "-" in line.rsplit(":", 1)[1]:  # P2P: name:range
                line = line.rsplit(":", 1)[1]
            if "/" in line:
                net = ipaddress.ip_network(line.strip(), strict=False)
                ranges.append((str(net[0]), str(net[-1])))
            elif "-" in line:
                a, b = line.split("-", 1)
                ranges.append((_ip(a), _ip(b)))
            else:
                ip = _ip(line)
                ranges.append((ip, ip))
        except ValueError:
            continue
    return ranges


def key_of(handle: lt.torrent_handle) -> str:
    """Stable hex id for a torrent (v1 info-hash, or truncated v2)."""
    return str(handle.info_hashes().get_best())


def parse_source(source: str) -> lt.add_torrent_params:
    """Turn a magnet link or a .torrent path into add_torrent_params."""
    source = source.strip()
    if source.startswith("magnet:"):
        try:
            return lt.parse_magnet_uri(source)
        except RuntimeError as e:
            raise ValueError(tr("not a valid magnet link ({error})", error=e)) from None
    path = Path(source).expanduser()
    if not path.is_file():
        raise ValueError(tr("not a magnet link or a .torrent file: {source}", source=source))
    atp = lt.add_torrent_params()
    try:
        atp.ti = lt.torrent_info(str(path))
    except RuntimeError as e:
        raise ValueError(tr("{name} isn't a valid .torrent file ({error})", name=path.name, error=e)) from None
    return atp


def params_key(atp: lt.add_torrent_params) -> str:
    """The same id as key_of(), before the torrent is added."""
    hashes = atp.ti.info_hashes() if atp.ti is not None else atp.info_hashes
    return str(hashes.get_best())


def params_name(atp: lt.add_torrent_params) -> str:
    if atp.ti is not None:
        return atp.ti.name()
    return atp.name or params_key(atp)


def already_added(atp: lt.add_torrent_params) -> str:
    return tr("“{name}” is already in your list", name=params_name(atp))


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.torrents_dir = cfg.state_dir / "torrents"
        self.torrents_dir.mkdir(parents=True, exist_ok=True)
        cfg.save_path.mkdir(parents=True, exist_ok=True)
        self.session_file = cfg.state_dir / "session.dat"

        params = lt.session_params()
        if self.session_file.is_file():  # reuse the DHT routing table
            try:
                params = lt.read_session_params(
                    self.session_file.read_bytes(), lt.save_state_flags_t.save_dht_state
                )
            except Exception:
                pass
        params.settings = build_settings(cfg)
        self.ses = lt.session(params)

        self.handles: dict[str, lt.torrent_handle] = {}
        self.events: deque[str] = deque(maxlen=8)
        self.dht_nodes = 0
        self.incoming = False  # a peer has connected to us: the port is reachable
        self._peers_since: float | None = None  # when we first had peers without one connecting in
        self._destinations: dict[str, str] = {}  # key -> save folder to move to when finished
        self.disk_errors: dict[str, tuple[int, str, str]] = {}  # key -> last failed disk operation
        self._error_files: dict[str, str] = {}  # key -> the file that operation was on
        self.slow = self._want_slow()
        self.blocked_ranges = 0
        if self.slow:
            self.ses.apply_settings(build_settings(cfg, True))
        if cfg.blocklist:
            self.load_blocklist()
        self.port_mapped = False
        self._pending_saves = 0
        self._removed: set[str] = set()  # keys whose late resume data must be dropped
        self._adding: set[str] = set()   # added, waiting for add_torrent_alert
        self._choose_files: set[str] = set()  # magnets whose files the user picks on arrival
        self.files_ready: list[str] = []  # metadata arrived for these; the UI shows a file picker

    def apply_config(self, cfg: Config) -> None:
        """Change settings while running (save_path affects new torrents)."""
        cfg.save_path.mkdir(parents=True, exist_ok=True)
        old_blocklist = self.cfg.blocklist
        self.cfg = cfg
        self.slow = self._want_slow()
        self.ses.apply_settings(build_settings(cfg, self.slow))
        if cfg.blocklist != old_blocklist:
            self.load_blocklist()

    # -- slow mode (alternative speed limits) ---------------------------------
    def _want_slow(self) -> bool:
        c = self.cfg
        return c.alt_enabled or (c.alt_schedule and in_window(c.alt_from, c.alt_to))

    def update_speed_mode(self) -> bool:
        """Switch limits when slow mode or its schedule changes. Returns slow."""
        want = self._want_slow()
        if want != self.slow:
            self.slow = want
            self.ses.apply_settings(build_settings(self.cfg, want))
            self.log(tr("slow mode on") if want else tr("slow mode off"))
        return self.slow

    # -- IP blocklist -----------------------------------------------------------
    def load_blocklist(self) -> int:
        """(Re)load cfg.blocklist into the session. Returns the number of ranges."""
        f = lt.ip_filter()
        count = 0
        path = self.cfg.blocklist
        if path:
            try:
                ranges = read_blocklist(Path(path))
            except OSError as e:
                self.log(tr("blocklist: {error}", error=e))
                ranges = []
            for start, end in ranges:
                f.add_rule(start, end, 1)  # 1 = blocked
            count = len(ranges)
            self.log(trn("blocklist: {n} range blocked", "blocklist: {n} ranges blocked", count))
        self.ses.set_ip_filter(f)
        self.blocked_ranges = count
        return count

    # -- trackers ---------------------------------------------------------------
    def add_tracker(self, h: lt.torrent_handle, url: str) -> None:
        url = url.strip()
        if not url.lower().startswith(("http://", "https://", "udp://")):
            raise ValueError(tr("not a tracker address: {url}", url=url))
        tier = max((t["tier"] for t in h.trackers()), default=-1) + 1
        h.add_tracker({"url": url, "tier": tier})
        h.force_reannounce()
        self.save_resume(h)

    def remove_tracker(self, h: lt.torrent_handle, url: str) -> None:
        h.replace_trackers([{"url": t["url"], "tier": t["tier"]} for t in h.trackers() if t["url"] != url])
        self.save_resume(h)

    # -- adding ---------------------------------------------------------
    def add(self, source: str, save_path: Path | None = None) -> str:
        return self.add_params(parse_source(source), save_path)

    def has(self, atp: lt.add_torrent_params) -> bool:
        key = params_key(atp)
        return key in self.handles or key in self._adding

    def add_params(self, atp: lt.add_torrent_params, save_path: Path | None = None,
                   choose_files: bool = False) -> str:
        """Add prepared params (maybe with file priorities set). Returns the key.

        choose_files: for a magnet link, download nothing once its file list
        arrives and report it in `files_ready`, so the user can pick files."""
        if self.has(atp):
            raise ValueError(already_added(atp))
        if save_path is not None or not atp.save_path:
            atp.save_path = str(save_path or self.cfg.save_path)
        Path(atp.save_path).mkdir(parents=True, exist_ok=True)
        key = params_key(atp)
        staging = self.cfg.incomplete_dir
        if staging and Path(staging) != Path(atp.save_path) and not self._has_files(atp):
            # Download into the folder for unfinished downloads; the files
            # move to the chosen folder when the torrent finishes.
            self._destinations[key] = atp.save_path
            atp.save_path = str(staging)
            Path(staging).mkdir(parents=True, exist_ok=True)
        self._adding.add(key)
        if choose_files and atp.ti is None:
            # Files default to "don't download", so nothing starts before the
            # user has chosen (setting priorities after the fact is too late
            # on a fast connection).
            atp.flags |= lt.torrent_flags.default_dont_download
            self._choose_files.add(key)
        self.ses.async_add_torrent(atp)
        return key

    @staticmethod
    def _has_files(atp: lt.add_torrent_params) -> bool:
        """Is some of this torrent already in its save folder (e.g. re-adding a finished one)?"""
        if atp.ti is None:
            return False
        fs = atp.ti.files()
        return any((Path(atp.save_path) / fs.file_path(i)).is_file() for i in range(fs.num_files()))

    def resume_all(self) -> int:
        """Re-add every torrent saved by a previous run."""
        count = 0
        for f in sorted(self.torrents_dir.glob("*.resume")):
            try:
                data = f.read_bytes()
                atp = lt.read_resume_data(data)
                dest = lt.bdecode(data).get(DEST_KEY)
            except Exception as e:
                self.log(tr("skipping corrupt resume file {name}: {error}", name=f.name, error=e))
                continue
            if not atp.save_path:
                atp.save_path = str(self.cfg.save_path)
            if dest:
                self._destinations[params_key(atp)] = os.fsdecode(dest)
            self.ses.async_add_torrent(atp)
            count += 1
        return count

    # -- alerts ---------------------------------------------------------
    def log(self, msg: str) -> None:
        self.events.append(f"{time.strftime('%H:%M:%S')} {msg}")

    def pump(self, timeout: float = 0.0) -> None:
        """Wait up to `timeout` seconds for alerts, then handle them all."""
        if timeout:
            self.ses.wait_for_alert(int(timeout * 1000))
        for a in self.ses.pop_alerts():
            try:
                self._handle_alert(a)
            except RuntimeError as err:  # never let one stale alert drop the rest
                self.log(tr("ignored {what}: {error}", what=type(a).__name__, error=err))

    def _handle_alert(self, a: lt.alert) -> None:
        if isinstance(a, lt.add_torrent_alert):
            self._adding.discard(params_key(a.params))
            if a.error.value():
                self.log(tr("add failed: {error}", error=a.error.message()))
                return
            h = a.handle
            self.handles[key_of(h)] = h
            self.save_resume(h)  # persist right away so it survives a crash
        elif isinstance(a, (lt.metadata_received_alert, lt.torrent_finished_alert)):
            if not a.handle.is_valid():
                return  # removed before we got to this alert
            name = a.handle.status().name
            self.log(tr("metadata received: {name}", name=name) if isinstance(a, lt.metadata_received_alert)
                     else tr("finished, now seeding: {name}", name=name))
            key = key_of(a.handle)
            if isinstance(a, lt.metadata_received_alert) and key in self._choose_files:
                # Everything is at "don't download" (see add_params) until the user picks files.
                self._choose_files.discard(key)
                self.files_ready.append(key)
            if isinstance(a, lt.torrent_finished_alert):
                self._move_to_destination(a.handle)
            self.save_resume(a.handle)
        elif isinstance(a, lt.save_resume_data_alert):
            self._pending_saves -= 1
            # Key off the params, not the handle: the handle is already
            # invalid if the torrent was removed while this save was in flight.
            key = str(a.params.info_hashes.get_best())
            if key in self._removed or set(key) == {"0"}:
                return
            entry = lt.write_resume_data(a.params)
            if key in self._destinations:
                entry[DEST_KEY] = os.fsencode(self._destinations[key])
            data = lt.bencode(entry)
            target = self.torrents_dir / f"{key}.resume"
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)  # atomic: never leave a half-written file
        elif isinstance(a, lt.save_resume_data_failed_alert):
            self._pending_saves -= 1
        elif isinstance(a, lt.storage_moved_alert):
            self.log(a.message())
            if a.handle.is_valid():
                key = key_of(a.handle)
                dest = self._destinations.get(key)
                if dest and Path(a.handle.status().save_path) == Path(dest):
                    del self._destinations[key]  # it has arrived
                self.save_resume(a.handle)
        elif isinstance(a, lt.storage_moved_failed_alert):
            self.log(tr("couldn't move files: {error}", error=a.message()))
        elif isinstance(a, lt.torrent_removed_alert):
            self.handles.pop(str(a.info_hashes.get_best()), None)
        elif isinstance(a, lt.session_stats_alert):
            values = a.values
            if isinstance(values, dict):
                get = lambda name, idx: values.get(name, 0)  # noqa: E731
            else:
                get = lambda name, idx: values[idx]  # noqa: E731
            self.dht_nodes = int(get("dht.dht_nodes", DHT_NODES_METRIC))
            self._note_connections(bool(get("net.has_incoming_connections", INCOMING_METRIC)),
                                   int(get("peer.num_peers_connected", PEERS_METRIC)))
        elif isinstance(a, lt.file_error_alert):
            self.log(a.message())
            if a.handle.is_valid():  # kept to explain a torrent that stops downloading
                self.disk_errors[key_of(a.handle)] = (
                    a.error.value(), a.error.category().name(), a.error.message())
                self._error_files[key_of(a.handle)] = Path(a.filename()).name
        elif isinstance(
            a,
            (lt.torrent_error_alert, lt.listen_failed_alert,
             lt.fastresume_rejected_alert, lt.portmap_error_alert),
        ):
            self.log(a.message())
        elif isinstance(a, (lt.listen_succeeded_alert, lt.portmap_alert)):
            if isinstance(a, lt.portmap_alert):
                self.port_mapped = True
            self.log(a.message())

    # -- control --------------------------------------------------------
    def save_resume(self, h: lt.torrent_handle) -> None:
        if h.is_valid():
            h.save_resume_data(lt.torrent_handle.save_info_dict)
            self._pending_saves += 1

    def save_all(self) -> None:
        for h in self.handles.values():
            if h.need_save_resume_data():
                self.save_resume(h)

    def pause(self, h: lt.torrent_handle) -> None:
        """Pause for good: take it out of the queue so it stays paused."""
        h.unset_flags(lt.torrent_flags.auto_managed)
        h.pause()
        self.save_resume(h)

    stop_seeding = pause

    def resume(self, h: lt.torrent_handle) -> None:
        """Start again; for a torrent stopped by an error, this is "try again"."""
        st = h.status()
        if st.errc.value():
            h.clear_error()
            if st.state in (lt.torrent_status.states.checking_files,
                            lt.torrent_status.states.checking_resume_data):
                h.force_recheck()  # the check itself failed: it has to start over
        if st.flags & lt.torrent_flags.upload_mode:
            h.unset_flags(lt.torrent_flags.upload_mode)  # download again
        self.disk_errors.pop(key_of(h), None)
        self._error_files.pop(key_of(h), None)
        h.set_flags(lt.torrent_flags.auto_managed)  # back under the queue's control
        h.resume()
        self.save_resume(h)

    def remove(self, h: lt.torrent_handle, delete_files: bool = False) -> None:
        """Drop a torrent from the session and forget it; optionally delete its data."""
        key = key_of(h)
        self._removed.add(key)
        self.ses.remove_torrent(h, lt.session.delete_files if delete_files else 0)
        (self.torrents_dir / f"{key}.resume").unlink(missing_ok=True)
        self.handles.pop(key, None)
        self._destinations.pop(key, None)
        self.disk_errors.pop(key, None)
        self._error_files.pop(key, None)

    def enforce_seed_ratio(self) -> None:
        """Stop seeding torrents that reached the ratio or the seeding time."""
        ratio, hours = self.cfg.seed_ratio, self.cfg.seed_hours
        if ratio is None and hours is None:
            return
        for h in list(self.handles.values()):
            st = h.status()
            if not st.is_seeding or is_stopped(st):
                continue
            if ratio is not None and share_ratio(st) >= ratio:
                self.pause(h)
                self.log(tr("ratio {ratio} reached, stopped: {name}", ratio=ratio, name=st.name))
            elif hours is not None and seconds(st.seeding_duration) >= hours * 3600:
                self.pause(h)
                self.log(tr("seeded for {hours} h, stopped: {name}", hours=f"{hours:g}", name=st.name))

    enforce_seeding_limits = enforce_seed_ratio

    def scan_watch_dir(self) -> list[str]:
        """Add every .torrent in the watch folder, then rename it so it is
        picked up only once: .torrent.added, or .torrent.invalid if broken.
        Returns the names added."""
        folder = self.cfg.watch_dir
        if folder is None or not Path(folder).is_dir():
            return []
        added = []
        for f in sorted(Path(folder).glob("*.torrent")):
            try:
                atp = parse_source(str(f))
                if not self.has(atp):
                    self.add_params(atp)
                    added.append(params_name(atp))
                done = f.with_name(f.name + ".added")
            except (ValueError, OSError) as e:
                self.log(tr("watch folder: {error}", error=e))
                done = f.with_name(f.name + ".invalid")
            try:
                f.replace(done)
            except OSError as e:  # e.g. still being written; try again next scan
                self.log(tr("watch folder: can't rename {name}: {error}", name=f.name, error=e))
        return added

    # -- per-torrent actions --------------------------------------------------
    def move(self, h: lt.torrent_handle, folder: Path) -> None:
        """Move a torrent's files to another folder (it keeps seeding from there).
        One that is still in the folder for unfinished downloads stays there,
        and goes to `folder` when it finishes."""
        key = key_of(h)
        if key in self._destinations and not h.status().is_finished:
            self._destinations[key] = str(folder)
        else:
            self._destinations.pop(key, None)
            Path(folder).mkdir(parents=True, exist_ok=True)
            h.move_storage(str(folder))
        self.save_resume(h)

    def error_text(self, st: lt.torrent_status) -> str:
        """Why this torrent stopped, or "" if nothing is wrong with it."""
        return error_text(st, self.disk_errors.get(str(st.info_hashes.get_best())))

    def error_file(self, st: lt.torrent_status) -> str:
        """The name of the file the problem is with, or "" if not known."""
        key = str(st.info_hashes.get_best())
        h = self.handles.get(key)
        if st.errc.value() and st.error_file >= 0 and h is not None and st.has_metadata:
            fs = h.torrent_file().files()
            if st.error_file < fs.num_files():
                return Path(fs.file_path(st.error_file)).name
        return self._error_files.get(key, "") if has_error(st) else ""

    def destination(self, h: lt.torrent_handle) -> Path:
        """Where a torrent's files end up: its save folder, or the folder it
        moves to when it finishes."""
        return Path(self._destinations.get(key_of(h)) or h.status().save_path)

    def _move_to_destination(self, h: lt.torrent_handle) -> None:
        dest = self._destinations.get(key_of(h))
        if not dest:
            return
        if Path(h.status().save_path) == Path(dest):
            del self._destinations[key_of(h)]
            return
        try:
            Path(dest).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.log(tr("couldn't move files: {error}", error=e))
            return
        h.move_storage(dest)  # storage_moved_alert clears the entry

    # -- is the port reachable? ---------------------------------------------------
    def _note_connections(self, incoming: bool, peers: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.incoming = incoming
        if incoming or peers == 0:
            self._peers_since = None
        elif self._peers_since is None:
            self._peers_since = now

    def reachable(self, now: float | None = None) -> bool | None:
        """True once a peer has connected to us from outside; False after a
        few minutes connected to peers without that; None while unknown."""
        if self.incoming:
            return True
        now = time.monotonic() if now is None else now
        if self._peers_since is not None and now - self._peers_since >= UNREACHABLE_AFTER:
            return False
        return None

    def set_sequential(self, h: lt.torrent_handle, on: bool) -> None:
        (h.set_flags if on else h.unset_flags)(lt.torrent_flags.sequential_download)
        self.save_resume(h)

    def set_limits(self, h: lt.torrent_handle, down: int, up: int) -> None:
        """Per-torrent limits in bytes/s; 0 = no limit (the global limits still apply)."""
        h.set_download_limit(down or -1)
        h.set_upload_limit(up or -1)
        self.save_resume(h)

    def request_stats(self) -> None:
        """Ask for a session_stats_alert (updates dht_nodes on the next pump)."""
        self.ses.post_session_stats()

    def statuses(self) -> list[lt.torrent_status]:
        return [h.status() for h in self.handles.values() if h.is_valid()]

    def shutdown(self, timeout: float = 10.0) -> None:
        """Pause, flush resume data for every torrent, save DHT state."""
        self.ses.pause()
        self.save_all()
        deadline = time.monotonic() + timeout
        while self._pending_saves > 0 and time.monotonic() < deadline:
            self.pump(0.5)
        # The 2.0 Python bindings have no session_state(); save_state() writes
        # the same bencoded layout that read_session_params() loads.
        state = self.ses.save_state(lt.save_state_flags_t.save_dht_state)
        self.session_file.write_bytes(lt.bencode(state))


# -- offline helpers (no session needed) --------------------------------
def saved_torrents(state_dir: Path) -> list[tuple[str, lt.add_torrent_params]]:
    out = []
    for f in sorted((state_dir / "torrents").glob("*.resume")):
        try:
            out.append((f.stem, lt.read_resume_data(f.read_bytes())))
        except Exception:
            continue
    return out


def forget(state_dir: Path, prefix: str) -> list[str]:
    """Delete resume files whose info-hash starts with `prefix`."""
    matches = [f for f in (state_dir / "torrents").glob("*.resume") if f.stem.startswith(prefix.lower())]
    for f in matches:
        f.unlink()
    return [f.stem for f in matches]
