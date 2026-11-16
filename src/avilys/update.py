"""Is there a newer release on GitHub? One small request to GitHub's public
API; nothing about the user or their torrents is sent."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from .i18n import tr

RELEASES_PAGE = "https://github.com/anglasligonis/Avilys/releases"
LATEST_API = "https://api.github.com/repos/anglasligonis/Avilys/releases/latest"
CHECK_EVERY = 24 * 3600  # seconds between automatic checks
FIRST_CHECK_AFTER = 15   # seconds after start, so startup isn't slowed


@dataclass
class Release:
    version: str  # "1.2.0" (no leading v)
    url: str      # the release's page on GitHub


def parse_version(text: str) -> tuple[int, ...] | None:
    """'v1.2.0' -> (1, 2, 0). None if it doesn't look like a version."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))  # 1.2 == 1.2.0
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def fetch_latest(url: str = LATEST_API, timeout: float = 15) -> Release:
    """The newest published release. Raises RuntimeError if it can't be found."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Avilys"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # offline, blocked, rate-limited, no releases yet
        raise RuntimeError(str(e)) from None
    tag = str(data.get("tag_name", ""))
    if data.get("draft") or data.get("prerelease") or parse_version(tag) is None:
        raise RuntimeError(tr("no published release found"))
    page = str(data.get("html_url", ""))
    if not page.startswith(RELEASES_PAGE + "/"):  # only ever link to our own releases
        page = RELEASES_PAGE
    return Release(tag.lstrip("v"), page)
