"""Shared test setup: Qt runs headless, and every GUI test cleans up its
windows so none outlive the QApplication (which crashes PySide at exit)."""

import os

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
