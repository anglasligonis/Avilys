"""One window per state folder.

When the OS opens a magnet link or .torrent file while avilys is already
running, the new process hands the links to the running window over a local
socket and exits, so two engines never share the same resume files."""

from __future__ import annotations

import getpass
import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name(state_dir: Path) -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    digest = hashlib.sha1(f"{user}|{Path(state_dir).resolve()}".encode()).hexdigest()[:16]
    return f"avilys-{digest}"


def send_to_running(name: str, sources: list[str], timeout_ms: int = 500, ack_ms: int = 5000) -> bool:
    """Give `sources` to an already-running window. False if none is running.

    Waits for the window to acknowledge, because on Windows a named pipe
    closed straight after writing can lose the data before it is read."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(json.dumps(sources).encode() + b"\n")
    sock.flush()
    sock.waitForBytesWritten(2000)
    if ack_ms:
        sock.waitForReadyRead(ack_ms)  # "ok" from the window (or time out)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Listens for links from later launches; emits them via `received`."""

    received = Signal(list)

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        if not self.server.listen(name):
            # A crashed instance can leave a stale socket behind (Unix).
            QLocalServer.removeServer(name)
            self.server.listen(name)
        self.server.newConnection.connect(self._accept)
        self._sockets: set[QLocalSocket] = set()

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            self._sockets.add(sock)
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: (self._read(s), self._drop(s)))
            self._read(sock)  # data may have arrived before we connected readyRead

    def _drop(self, sock: QLocalSocket) -> None:
        if sock in self._sockets:
            self._sockets.discard(sock)
            sock.deleteLater()

    def close(self) -> None:
        """Stop listening and drop open connections (safe to call twice)."""
        for sock in list(self._sockets):
            sock.readyRead.disconnect()
            self._drop(sock)
        self.server.close()

    def _read(self, sock: QLocalSocket) -> None:
        if sock not in self._sockets:
            return
        while sock.canReadLine():
            try:
                sources = json.loads(bytes(sock.readLine()).decode())
            except ValueError:
                continue
            if isinstance(sources, list):
                self.received.emit([str(s) for s in sources])
            if sock.state() == QLocalSocket.ConnectedState:
                sock.write(b"ok\n")  # lets the sender exit knowing we have it
                sock.flush()
