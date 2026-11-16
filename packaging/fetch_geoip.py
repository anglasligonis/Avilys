"""Download this month's DB-IP country database into packaging/build/ so the
installers ship with working country flags (IP Geolocation by DB-IP, CC BY 4.0)."""

import sys
from pathlib import Path

from avilys import geoip

if __name__ == "__main__":
    dest = Path(__file__).resolve().parent / "build" / geoip.FILE
    geoip.download(dest)
    g = geoip.GeoIP(dest.parent, bundled=dest)
    print(f"wrote {dest} ({dest.stat().st_size // 1024} KiB, {g.age_days():.0f} days old); "
          f"8.8.8.8 -> {g.country('8.8.8.8')}")
    sys.exit(0 if g.country("8.8.8.8") else 1)
