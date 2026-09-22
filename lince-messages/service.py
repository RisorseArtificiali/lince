"""Bounded Unix socket service; public clients have no host execution surface."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import secrets
import socketserver
import stat
import threading

from protocol import MAX_RESPONSE_FRAME, ProtocolError, encode, receive, require
from store import Store
from transport import TerminalTransport


class Handler(socketserver.StreamRequestHandler):
    timeout = 5

    def handle(self):
        shutdown = False
        try:
            envelope = receive(self.rfile)
            result = self.server.store.handle(envelope)
            shutdown = envelope["op"] == "host.shutdown"
            response = {"v": 1, "ok": True, "result": result}
            data = encode(response)
            require(len(data) <= MAX_RESPONSE_FRAME, "response_limit", "Use a smaller page")
        except ProtocolError as exc:
            data = encode({"v": 1, "ok": False, "error": {"code": exc.code, "message": str(exc)}})
        except (OSError, ValueError, TypeError):
            data = encode({"v": 1, "ok": False, "error": {"code": "invalid_request", "message": "Malformed request"}})
        except Exception:
            # Never return database paths, SQL or credentials over the public endpoint.
            data = encode({"v": 1, "ok": False, "error": {"code": "internal", "message": "Service operation failed"}})
        try:
            self.wfile.write(data)
        except OSError:
            pass
        if shutdown:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 64

    def __init__(self, endpoint, store):
        self.store = store
        self.slots = threading.BoundedSemaphore(64)
        super().__init__(str(endpoint), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
            "unsafe_directory", "Messaging directory must be owned by the current user with mode 0700")


def serve(private: Path, public: Path, session: str):
    os.umask(0o077)
    private_directory(private)
    private_directory(public)
    # Lock prevents unlinking an endpoint still owned by a running service.
    lock_fd = os.open(private / "service.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        credential = private / "admin.token"
        if not credential.exists():
            fd = os.open(credential, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_urlsafe(32))
        require(not credential.is_symlink(), "unsafe_path", "Credential must not be a symlink")
        store = Store(None, credential.read_text(), TerminalTransport(session))
        endpoint = public / "mailbox.sock"
        if endpoint.exists():
            require(endpoint.is_socket(), "unsafe_path", "Endpoint is not a socket")
            endpoint.unlink()
        try:
            with Server(endpoint, store) as server:
                os.chmod(endpoint, 0o600)
                stop = threading.Event()
                def deliver():
                    while not stop.wait(0.5):
                        store.flush()
                worker = threading.Thread(target=deliver, daemon=True)
                worker.start()
                try:
                    server.serve_forever(poll_interval=0.2)
                finally:
                    stop.set()
                    worker.join(timeout=5)
        finally:
            store.close()
            endpoint.unlink(missing_ok=True)
    finally:
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--private", required=True, type=Path)
    parser.add_argument("--public", required=True, type=Path)
    args = parser.parse_args()
    serve(args.private, args.public, args.session)


if __name__ == "__main__":
    main()
