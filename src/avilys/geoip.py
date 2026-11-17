"""Peer IP -> country, using DB-IP's free "IP to Country Lite" database.

The database is licensed CC BY 4.0 ("IP Geolocation by DB-IP",
https://db-ip.com). Installers ship a copy; Avilys refreshes it about once a
month into its state folder. Without any copy, lookups simply return None."""

from __future__ import annotations

import gzip
import ipaddress
import os
import threading
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import net
from .i18n import tr

try:
    import maxminddb
except ImportError:  # optional: no flags, everything else works
    maxminddb = None

FILE = "dbip-country-lite.mmdb"
BUNDLED = Path(__file__).resolve().parent / "data" / FILE
URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz"
MAX_AGE_DAYS = 35
ATTRIBUTION = "IP Geolocation by DB-IP (db-ip.com), CC BY 4.0"


def _build_time(path: Path) -> float:
    try:
        with maxminddb.open_database(str(path)) as db:
            return float(db.metadata().build_epoch)
    except Exception:
        return -1.0


class GeoIP:
    def __init__(self, state_dir: Path, bundled: Path = BUNDLED):
        self.downloaded = Path(state_dir) / FILE
        self.bundled = bundled
        self.reader = None
        self._lock = threading.Lock()
        self.updating = False
        self.reload()

    @property
    def available(self) -> bool:
        return self.reader is not None

    def reload(self) -> None:
        """Open the newest copy we have (downloaded or bundled)."""
        if maxminddb is None:
            return
        best = max((p for p in (self.downloaded, self.bundled) if p.is_file()),
                   key=_build_time, default=None)
        new = None
        if best is not None:
            try:
                new = maxminddb.open_database(str(best))
            except Exception:
                new = None
        with self._lock:
            old, self.reader = self.reader, new
            self.country.cache_clear()
        if old is not None:
            old.close()

    def age_days(self) -> float | None:
        if self.reader is None:
            return None
        return (time.time() - self.reader.metadata().build_epoch) / 86400

    @lru_cache(maxsize=4096)
    def country(self, ip: str) -> tuple[str, str] | None:
        """('lt', 'Lithuania') for an address, or None if unknown."""
        with self._lock:
            reader = self.reader
            if reader is None:
                return None
            try:
                rec = reader.get(str(ipaddress.ip_address(ip)))
            except (ValueError, maxminddb.InvalidDatabaseError):
                return None
        if not rec or "country" not in rec:
            return None
        c = rec["country"]
        code = c.get("iso_code", "").lower()
        return (code, c.get("names", {}).get("en", code.upper())) if code else None

    # -- monthly refresh ---------------------------------------------------------
    def needs_update(self) -> bool:
        age = self.age_days()
        return maxminddb is not None and (age is None or age > MAX_AGE_DAYS)

    def update_in_background(self, log=lambda msg: None, source_address: str | None = None) -> None:
        """Download this month's database in a thread, then switch to it.
        source_address: send from this address (the adapter Avilys is bound to)."""
        if self.updating or maxminddb is None:
            return
        self.updating = True

        def work():
            try:
                download(self.downloaded, source_address=source_address)
                self.reload()
                log(tr("country database updated"))
            except Exception as e:  # offline, blocked, or not published yet
                log(tr("country database update failed: {error}", error=e))
            finally:
                self.updating = False

        threading.Thread(target=work, name="geoip-update", daemon=True).start()


def months_to_try(now: time.struct_time | None = None) -> list[str]:
    """This month, then last month (a new month's file appears a day or so late)."""
    now = now or time.gmtime()
    prev_year, prev_month = (now.tm_year, now.tm_mon - 1) if now.tm_mon > 1 else (now.tm_year - 1, 12)
    return [f"{now.tm_year}-{now.tm_mon:02d}", f"{prev_year}-{prev_month:02d}"]


def download(dest: Path, timeout: float = 60, source_address: str | None = None) -> Path:
    """Fetch and unpack the newest database to `dest`, replacing it atomically."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for month in months_to_try():
        req = urllib.request.Request(URL.format(month=month), headers={"User-Agent": "Avilys"})
        try:
            with net.urlopen(req, timeout, source_address) as resp:
                data = gzip.decompress(resp.read())
        except Exception as e:
            last_error = e
            continue
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        if maxminddb is not None:
            maxminddb.open_database(str(tmp)).close()  # refuse a broken file
        os.replace(tmp, dest)
        return dest
    raise RuntimeError(f"couldn't download the country database ({last_error})")
