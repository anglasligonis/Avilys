"""Command line: `avilys start`, `avilys list`, `avilys remove`."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

import libtorrent as lt

from . import __version__, display
from .engine import Config, Engine, forget, saved_torrents


def default_state_dir() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "avilys"
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "avilys"


def kib(value: str) -> int:
    return int(float(value) * 1024)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="avilys", description="Avilys: a small BitTorrent client on libtorrent.")
    p.add_argument("--version", action="version", version=f"avilys {__version__} (libtorrent {lt.__version__})")
    p.add_argument("--state-dir", type=Path, default=default_state_dir(), help="where resume data lives (default: %(default)s)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start", help="add torrents/magnets (optional) and run until Ctrl+C")
    s.add_argument("sources", nargs="*", help="magnet links or .torrent files")
    s.add_argument("-d", "--save-path", type=Path, default=Path.home() / "Downloads")
    s.add_argument("-p", "--port", type=int, default=6881, help="listen port, TCP and UDP (default: %(default)s)")
    s.add_argument("--encryption", choices=["prefer", "require", "disable"], default="prefer")
    s.add_argument("--no-dht", action="store_true")
    s.add_argument("--no-utp", action="store_true")
    s.add_argument("--no-lsd", action="store_true", help="disable local peer discovery")
    s.add_argument("--no-port-mapping", action="store_true", help="disable UPnP / NAT-PMP")
    s.add_argument("--max-down", type=kib, default=0, metavar="KIB/S")
    s.add_argument("--max-up", type=kib, default=0, metavar="KIB/S")
    s.add_argument("--seed-ratio", type=float, metavar="R", help="stop seeding a torrent once its ratio reaches R (0 = never seed)")
    s.add_argument("--exit-when-done", action="store_true", help="quit once everything is downloaded (and has hit --seed-ratio, if set)")
    s.add_argument("--interval", type=float, default=1.0, help="screen refresh, seconds")

    sub.add_parser("gui", help="open the desktop window (needs: pip install 'avilys[gui]')")
    sub.add_parser("list", help="show saved torrents without starting the client")

    r = sub.add_parser("remove", help="forget a saved torrent (downloaded files are kept)")
    r.add_argument("info_hash", help="info-hash or a unique prefix of at least 6 characters")
    return p


def cmd_list(state_dir: Path) -> int:
    saved = saved_torrents(state_dir)
    if not saved:
        print("no saved torrents")
    for key, atp in saved:
        name = atp.ti.name() if atp.ti else atp.name or "(metadata pending)"
        print(f"{key}  {name}  -> {atp.save_path}")
    return 0


def cmd_remove(state_dir: Path, prefix: str) -> int:
    if len(prefix) < 6:
        print("give at least 6 characters of the info-hash", file=sys.stderr)
        return 2
    keys = [k for k, _ in saved_torrents(state_dir) if k.startswith(prefix.lower())]
    if len(keys) != 1:
        print(f"{len(keys)} torrents match {prefix!r}; need exactly one", file=sys.stderr)
        return 1
    forget(state_dir, keys[0])
    print(f"removed {keys[0]} (files left in place)")
    return 0


def all_done(engine: Engine, seed_ratio: float | None) -> bool:
    sts = engine.statuses()
    if not sts:
        return False
    for st in sts:
        if not st.is_finished:
            return False
        if seed_ratio is not None and not (st.flags & lt.torrent_flags.paused):
            return False  # still seeding towards the ratio
    return True


def _interrupt(*_):
    raise KeyboardInterrupt


def cmd_start(args) -> int:
    cfg = Config(
        state_dir=args.state_dir,
        save_path=args.save_path.expanduser().resolve(),
        listen=f"0.0.0.0:{args.port},[::]:{args.port}",
        dht=not args.no_dht,
        utp=not args.no_utp,
        lsd=not args.no_lsd,
        port_mapping=not args.no_port_mapping,
        encryption=args.encryption,
        download_limit=args.max_down,
        upload_limit=args.max_up,
        seed_ratio=args.seed_ratio,
    )
    engine = Engine(cfg)
    resumed = engine.resume_all()
    if resumed:
        engine.log(f"resumed {resumed} torrent(s) from {cfg.state_dir}")
    for src in args.sources:
        try:
            engine.add(src)
        except (ValueError, RuntimeError) as e:
            print(f"avilys: {e}", file=sys.stderr)
            return 2

    # Treat SIGTERM like Ctrl+C so resume data is always flushed.
    signal.signal(signal.SIGTERM, _interrupt)
    tty = sys.stdout.isatty()
    last_draw = last_save = 0.0
    try:
        while True:
            engine.pump(0.25)
            now = time.monotonic()
            engine.enforce_seed_ratio()
            if now - last_save > 60:  # periodic checkpoint
                engine.save_all()
                last_save = now
            if now - last_draw >= args.interval:
                last_draw = now
                screen = display.render(engine.statuses(), engine.events, "Ctrl+C to quit")
                if tty:
                    sys.stdout.write("\x1b[H\x1b[J" + screen + "\n")
                else:
                    sys.stdout.write(screen + "\n\n")
                sys.stdout.flush()
            if args.exit_when_done and all_done(engine, args.seed_ratio):
                break
    except KeyboardInterrupt:
        pass
    print("\nsaving state…", flush=True)
    engine.shutdown()
    print(display.render(engine.statuses(), []))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        return cmd_list(args.state_dir)
    if args.command == "remove":
        return cmd_remove(args.state_dir, args.info_hash)
    if args.command == "gui":
        try:
            from .gui.app import run
        except ImportError as e:
            print(f"avilys: the GUI needs PySide6: pip install 'avilys[gui]' ({e})", file=sys.stderr)
            return 2
        return run(args.state_dir)
    return cmd_start(args)


if __name__ == "__main__":
    sys.exit(main())
