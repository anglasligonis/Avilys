"""Plain-text rendering of torrent status. No curses, just ANSI redraws."""

from __future__ import annotations

import libtorrent as lt

from .engine import has_error
from .engine import share_ratio as ratio
from .i18n import num, tr

STATE_NAMES = {
    lt.torrent_status.states.queued_for_checking: "queued",
    lt.torrent_status.states.checking_files: "checking",
    lt.torrent_status.states.checking_resume_data: "checking",
    lt.torrent_status.states.downloading_metadata: "metadata",
    lt.torrent_status.states.downloading: "download",
    lt.torrent_status.states.finished: "finished",
    lt.torrent_status.states.seeding: "seeding",
}

CONTROL_CHARS = {code: f"\\x{code:02x}" for code in (*range(32), *range(127, 160))}


def terminal_text(text: str) -> str:
    """Render terminal control characters as visible escape sequences."""
    return text.translate(CONTROL_CHARS)


def size(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{num(n, 1)} {unit}"
        n /= 1024
    return ""


def rate(n: float) -> str:
    return f"{size(n)}/s" if n > 0 else "-"


def eta(st: lt.torrent_status) -> str:
    if not st.has_metadata:
        return "?"
    left = st.total_wanted - st.total_wanted_done
    if left <= 0:
        return "done"
    if st.download_payload_rate <= 0:
        return "∞"
    secs = int(left / st.download_payload_rate)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return tr("{h}h {m:02d}m", h=h, m=m)
    return tr("{m}m {s:02d}s", m=m, s=s) if m else tr("{s}s", s=s)




def state_name(st: lt.torrent_status) -> str:
    if has_error(st):
        return "error"
    if st.flags & lt.torrent_flags.paused:
        return "queued" if st.flags & lt.torrent_flags.auto_managed else "paused"
    return STATE_NAMES.get(st.state, str(st.state))


def bar(progress: float, width: int = 20) -> str:
    filled = int(progress * width)
    return "█" * filled + "░" * (width - filled)


HEADER = f"{'NAME':<32} {'STATE':<9} {'PROGRESS':<27} {'DOWN':>11} {'UP':>11} {'PEERS':>7} {'RATIO':>6} {'ETA':>8}"


def row(st: lt.torrent_status) -> str:
    name = terminal_text(st.name) if st.name else str(st.info_hashes.get_best())[:16]
    if len(name) > 32:
        name = name[:31] + "…"
    progress = f"{bar(st.progress)} {st.progress * 100:5.1f}%"
    peers = f"{st.num_seeds}/{st.num_peers}"
    return (
        f"{name:<32} {state_name(st):<9} {progress:<27} {rate(st.download_payload_rate):>11} "
        f"{rate(st.upload_payload_rate):>11} {peers:>7} {ratio(st):>6.2f} {eta(st):>8}"
    )


def render(statuses: list[lt.torrent_status], events, footer: str = "") -> str:
    lines = [HEADER]
    lines += [row(st) for st in sorted(statuses, key=lambda s: s.name)] or ["(no torrents yet)"]
    total_down = sum(s.download_payload_rate for s in statuses)
    total_up = sum(s.upload_payload_rate for s in statuses)
    lines.append("")
    lines.append(f"total ↓ {rate(total_down)}  ↑ {rate(total_up)}   {terminal_text(footer)}")
    if events:
        lines.append("")
        lines += [terminal_text(event) for event in events]
    return "\n".join(lines)
