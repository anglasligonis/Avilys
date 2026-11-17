"""One window per state folder.

When the OS opens a magnet link or .torrent file while avilys is already
running, the new process hands the links to the running window over a local
socket and exits, so two engines never share the same resume files.

Only the same user's window may take the links. The name of the socket is
easy to work out, so another account on the same computer could otherwise
listen on it first, receive every link opened, and keep Avilys from starting.
On Linux and macOS the socket lives in a folder only this user can enter. On
Windows, where pipe names are shared by everyone, the sender checks that the
pipe belongs to a process of the same user before handing anything over."""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MAX_UNIX_PATH = 100  # sockaddr_un holds 104-108 bytes depending on the system


def private_dir(path: Path) -> bool:
    """Is `path` a real folder (not a link) that only this user can use?"""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o077


def socket_dirs(state_dir: Path):
    """Folders for the socket that no other user can write to (Unix), best
    first: the session's runtime folder, our own folder in the temp folder,
    then the state folder (always ours, though its path may be long)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and private_dir(Path(runtime)):
        yield Path(runtime)
    own = Path(tempfile.gettempdir()) / f"avilys-{os.getuid()}"
    try:
        own.mkdir(mode=0o700)
    except OSError:  # it exists (ours or someone else's), or no temp folder
        pass
    if private_dir(own):
        yield own
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    yield Path(state_dir)


def server_name(state_dir: Path) -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    digest = hashlib.sha1(f"{user}|{Path(state_dir).resolve()}".encode()).hexdigest()[:16]
    name = f"avilys-{digest}"
    if sys.platform == "win32":
        return name
    # Never a bare name: Qt would put it in the shared temp folder. If no
    # private folder has a path short enough, listening fails and each launch
    # opens its own window, which is safe.
    paths = [str(d / name) for d in socket_dirs(state_dir)]
    return next((p for p in paths if len(p) <= MAX_UNIX_PATH), paths[-1])


# -- who is on the other end? ------------------------------------------------------
def _peer_uid(fd: int) -> int | None:
    import socket
    import struct

    if not hasattr(socket, "SO_PEERCRED"):  # Linux only; elsewhere the private folder must do
        return None
    s = socket.socket(fileno=os.dup(fd))
    try:
        creds = s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        return struct.unpack("3i", creds)[1]  # (pid, uid, gid)
    finally:
        s.close()


def _win_user_sid(token_handle) -> bytes | None:
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    TokenUser = 1
    size = wintypes.DWORD(0)
    advapi.GetTokenInformation(token_handle, TokenUser, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if not advapi.GetTokenInformation(token_handle, TokenUser, buf, size, ctypes.byref(size)):
        return None
    sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER.User.Sid
    advapi.GetLengthSid.restype = wintypes.DWORD
    length = advapi.GetLengthSid(ctypes.c_void_p(sid))
    return ctypes.string_at(sid, length)


def _win_process_sid(pid: int | None) -> bytes | None:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    PROCESS_QUERY_LIMITED_INFORMATION, TOKEN_QUERY = 0x1000, 0x0008
    if pid is None:
        process, close_process = kernel.GetCurrentProcess(), False
    else:
        process, close_process = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid), True
        if not process:
            return None
    token = wintypes.HANDLE()
    try:
        if not advapi.OpenProcessToken(wintypes.HANDLE(process), TOKEN_QUERY, ctypes.byref(token)):
            return None
        try:
            return _win_user_sid(token)
        finally:
            kernel.CloseHandle(token)
    finally:
        if close_process:
            kernel.CloseHandle(wintypes.HANDLE(process))


def _win_pipe_server_pid(handle: int) -> int | None:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pid = wintypes.ULONG()
    if not kernel.GetNamedPipeServerProcessId(wintypes.HANDLE(handle), ctypes.byref(pid)):
        return None
    return pid.value


def server_is_ours(sock: QLocalSocket) -> bool:
    """Does the window at the other end run as the same user as we do?
    When the system can't tell us, trust the private socket folder (Unix)."""
    fd = int(sock.socketDescriptor())
    if fd < 0:
        return False
    try:
        if sys.platform == "win32":
            pid = _win_pipe_server_pid(fd)
            mine = _win_process_sid(None)
            return pid is not None and mine is not None and _win_process_sid(pid) == mine
        uid = _peer_uid(fd)
        return uid is None or uid == os.getuid()
    except (OSError, AttributeError, ValueError):
        return False


def send_to_running(name: str, sources: list[str], timeout_ms: int = 500, ack_ms: int = 5000) -> bool:
    """Give `sources` to an already-running window. False if none is running
    (or the one listening belongs to someone else).

    Waits for the window to acknowledge, because on Windows a named pipe
    closed straight after writing can lose the data before it is read."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(timeout_ms):
        return False
    if not server_is_ours(sock):
        sock.abort()
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
        # Only this user may connect (a 0700 socket on Unix, a pipe ACL on Windows)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
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
