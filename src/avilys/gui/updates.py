"""Checks for a new version in the background and reports it to the window."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QTimer, Signal

from .. import update


class UpdateChecker(QObject):
    """Asks GitHub in a worker thread; `finished` carries the result back to
    the window's thread: (Release or None, error text, manual?)."""

    finished = Signal(object, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.url = update.LATEST_API  # swappable in tests
        self.busy = False
        self.timer = QTimer(self, interval=update.CHECK_EVERY * 1000, timeout=lambda: self.check())

    def start(self, first_after: float = update.FIRST_CHECK_AFTER) -> None:
        """Check soon after startup, then once a day."""
        QTimer.singleShot(int(first_after * 1000), self, lambda: self.check())
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def check(self, manual: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        url = self.url

        def work():
            try:
                result, error = update.fetch_latest(url), ""
            except RuntimeError as e:
                result, error = None, str(e)
            self.busy = False
            self.finished.emit(result, error, manual)  # queued to the window's thread

        threading.Thread(target=work, name="update-check", daemon=True).start()
