"""Shared test setup: Qt runs headless, and every GUI test cleans up its
windows so none outlive the QApplication (which crashes PySide at exit)."""

import os
import time
import weakref
from collections import deque

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def retry_dropped_peers_quickly(monkeypatch):
    """Tests reach their loopback peers with a single connect_peer(). If that
    first connection closes before the test has seen what it waits for (a
    connection over loopback uTP that fails, a handshake that times out on a
    slow Windows runner), libtorrent keeps the peer but waits
    min_reconnect_time (60 s by default) before connecting again, and another
    connect_peer() doesn't shorten that wait. Every 30 s wait then times out.
    With 1 s, libtorrent connects again by itself, as it would on a real swarm
    with peers to spare."""
    try:
        from avilys import engine
    except ImportError:
        return
    build = engine.build_settings
    monkeypatch.setattr(engine, "build_settings",
                        lambda *a, **kw: {**build(*a, **kw), "min_reconnect_time": 1})


@pytest.fixture(autouse=True)
def close_leftover_windows():
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in QApplication.topLevelWidgets():
        w.close()
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


# -- why did a wait time out? ---------------------------------------------------------
# Loopback connections in these tests fail now and then on the Windows runner
# only. Each engine keeps its last connection and peer alerts, and a wait that
# times out prints them (with each torrent's peer counts), so a failure says
# what libtorrent saw instead of just "timed out".
_engines: list = []


@pytest.fixture(autouse=True)
def trace_connections(monkeypatch):
    try:
        import libtorrent as lt

        from avilys import engine
    except ImportError:
        yield
        return
    _engines.clear()
    extra = int(lt.alert_category.connect | lt.alert_category.peer | lt.alert_category.error)
    build = engine.build_settings  # already wrapped by retry_dropped_peers_quickly
    monkeypatch.setattr(engine, "build_settings", lambda *a, **kw: (
        lambda s: {**s, "alert_mask": s["alert_mask"] | extra})(build(*a, **kw)))
    init, handle = engine.Engine.__init__, engine.Engine._handle_alert
    start = time.monotonic()

    def traced_init(self, cfg, *a, **kw):
        self.trace = deque(maxlen=40)
        _engines.append(weakref.ref(self))
        init(self, cfg, *a, **kw)

    def traced_handle(self, a):
        n = type(a).__name__
        if any(k in n for k in ("peer", "connect", "listen", "udp_error", "torrent_error", "file_error",
                                "paused", "resumed", "state_changed", "blocked")):
            self.trace.append(f"{time.monotonic() - start:7.2f}s {n}: {a.message()[:200]}")
        return handle(self, a)

    monkeypatch.setattr(engine.Engine, "__init__", traced_init)
    monkeypatch.setattr(engine.Engine, "_handle_alert", traced_handle)
    yield
    _engines.clear()


def trace_report() -> str:
    """What every engine of this test saw, for a timed-out wait's message."""
    import libtorrent as lt

    out = []
    for ref in _engines:
        eng = ref()
        if eng is None:
            continue
        try:
            eng.pump()
            out.append(f"engine {eng.cfg.state_dir.parent.name} (port {eng.ses.listen_port()}):")
            for h in list(eng.handles.values()):
                st = h.status()
                out.append(f"  torrent {st.name}: {st.state} paused={bool(st.flags & lt.torrent_flags.paused)} "
                           f"error={st.errc.message() if st.errc.value() else '-'} peers={st.num_peers} "
                           f"connecting={len([p for p in h.get_peer_info() if p.flags & p.connecting])} "
                           f"known={st.list_peers} candidates={st.connect_candidates}")
        except RuntimeError as e:
            out.append(f"  (engine gone: {e})")
            continue
        out.extend("  " + line for line in getattr(eng, "trace", ()))
    return "\n".join(out) or "(no engines)"
