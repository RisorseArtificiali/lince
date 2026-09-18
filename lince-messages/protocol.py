"""Small, versioned wire contract shared by the client and host service."""
from __future__ import annotations

import json
import socket
import unicodedata

VERSION = 1
MAX_FRAME = 65536
# Replies can contain a full request plus a result, or the bounded host registry.
# Keep inbound frames small while allowing every valid stored item to be read.
MAX_RESPONSE_FRAME = 2 * 1024 * 1024
MAX_TEXT = 16384
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


class ProtocolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require(condition, code="invalid_request", message="Invalid request"):
    if not condition:
        raise ProtocolError(code, message)


def text(value, *, limit=MAX_TEXT):
    require(isinstance(value, str), message="Expected text")
    require(all(c in "\n\t" or unicodedata.category(c) not in {"Cc", "Cs", "Cf"} for c in value),
            message="Control characters are not allowed")
    require(0 < len(value.encode("utf-8")) <= limit, message="Expected nonempty bounded text")
    return value


def fields(args, required=(), optional=()):
    require(isinstance(args, dict), message="args must be an object")
    require(set(required) <= args.keys() <= set(required) | set(optional),
            message="Missing or unknown argument")


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def receive(stream, *, max_frame=MAX_FRAME):
    data = stream.readline(max_frame + 1)
    require(len(data) <= max_frame and data.endswith(b"\n"), message="Invalid or oversized frame")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError):
        raise ProtocolError("invalid_request", "Invalid JSON") from None


def call(endpoint, token, op, args=None):
    payload = encode({"v": VERSION, "token": token, "op": op, "args": args or {}})
    require(len(payload) <= MAX_FRAME, message="Request exceeds wire limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(str(endpoint))
        connection.sendall(payload)
        with connection.makefile("rb") as stream:
            response = receive(stream, max_frame=MAX_RESPONSE_FRAME)
    if not response.get("ok"):
        error = response.get("error", {})
        raise ProtocolError(error.get("code", "protocol_error"), error.get("message", "Service error"))
    return response["result"]
