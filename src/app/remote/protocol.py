"""Length-prefixed JSON framing shared by the remote client and server.

Each message is a 4-byte big-endian unsigned length followed by that many bytes of UTF-8
JSON. One request frame and one response frame make up a hook round-trip:

    request:  {"provider": "claude-code" | null, "token": "<secret>"?, "stdin": "<raw>"}
    response: {"exit_code": <int>, "stdout": "<decision json>", "error": <str|null>}
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

# Guard against a peer advertising an absurd length. Hook payloads are small (a few KB);
# 16 MiB is generous while still bounding memory.
MAX_FRAME_BYTES = 16 * 1024 * 1024
_HEADER = struct.Struct(">I")


def send_frame(sock: socket.socket, obj: dict[str, Any]) -> None:
    """Encode ``obj`` as JSON and write it as one length-prefixed frame.

    :param sock: Connected socket to write to.
    :type sock: socket.socket
    :param obj: JSON-serializable message.
    :type obj: dict[str, Any]
    :raises ValueError: When the encoded frame exceeds :data:`MAX_FRAME_BYTES`.
    """
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_FRAME_BYTES:
        raise ValueError("frame too large")
    sock.sendall(_HEADER.pack(len(data)) + data)


def recv_frame(sock: socket.socket) -> dict[str, Any] | None:
    """Read one length-prefixed JSON frame.

    :param sock: Connected socket to read from.
    :type sock: socket.socket
    :return: The decoded message, or ``None`` when the peer closed cleanly first.
    :raises ValueError: When the advertised length exceeds :data:`MAX_FRAME_BYTES`.
    :raises json.JSONDecodeError: When the body is not valid JSON.
    """
    header = _recv_exactly(sock, _HEADER.size)
    if header is None:
        return None
    (length,) = _HEADER.unpack(header)
    if length > MAX_FRAME_BYTES:
        raise ValueError("frame too large")
    body = _recv_exactly(sock, length)
    if body is None:
        return None
    decoded = json.loads(body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("frame is not a JSON object")
    return decoded


def _recv_exactly(sock: socket.socket, count: int) -> bytes | None:
    """Read exactly ``count`` bytes, or ``None`` if the peer closes first."""
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


__all__ = ["MAX_FRAME_BYTES", "recv_frame", "send_frame"]
