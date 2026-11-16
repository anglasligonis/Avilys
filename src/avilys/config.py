"""Settings saved between runs as JSON in the state dir (used by the GUI)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .engine import ENCRYPTION, Config, listen_port
from .i18n import LANGUAGES

FILE = "settings.json"
SAVED = ("save_path", "listen", "dht", "utp", "lsd", "port_mapping", "encryption",
         "download_limit", "upload_limit", "seed_ratio", "seed_hours", "active_downloads",
         "active_seeds", "watch_dir", "alt_download_limit", "alt_upload_limit", "alt_enabled",
         "alt_schedule", "alt_from", "alt_to", "interface", "blocklist", "incomplete_dir", "anonymous",
         "theme", "language", "close_to_tray", "confirm_add", "peer_countries", "prevent_sleep")
PATHS = ("watch_dir", "blocklist", "incomplete_dir")  # optional paths
THEMES = ("system", "light", "dark")


def load(state_dir: Path) -> Config:
    cfg = Config(state_dir=state_dir, save_path=Path.home() / "Downloads")
    try:
        data = json.loads((state_dir / FILE).read_text())
    except (OSError, ValueError):
        return cfg
    changes = {k: data[k] for k in SAVED if k in data}
    if "save_path" in changes:
        changes["save_path"] = Path(changes["save_path"])
    for key in PATHS:
        if changes.get(key):
            changes[key] = Path(changes[key])
    if changes.get("encryption") not in ENCRYPTION:
        changes.pop("encryption", None)
    if changes.get("theme") not in THEMES:
        changes.pop("theme", None)
    if changes.get("language") not in ("system", *LANGUAGES):
        changes.pop("language", None)
    try:
        return dataclasses.replace(cfg, **changes)
    except TypeError:
        return cfg


def save(cfg: Config) -> None:
    data = {k: getattr(cfg, k) for k in SAVED}
    data["save_path"] = str(cfg.save_path)
    for key in PATHS:
        data[key] = str(getattr(cfg, key)) if getattr(cfg, key) else None
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.state_dir / FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def port_of(listen: str) -> int:
    """'0.0.0.0:6881,[::]:6881' -> 6881"""
    return listen_port(listen)


def listen_on(port: int) -> str:
    return f"0.0.0.0:{port},[::]:{port}"
