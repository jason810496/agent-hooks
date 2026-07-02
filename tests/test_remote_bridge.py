"""Tests for the remote hook bridge: framing, the fail-open client, and the TCP broker."""

from __future__ import annotations

import json
import socket
import threading
import time
from io import StringIO
from pathlib import Path

import pytest

from app.remote.client import forward_remote
from app.remote.config import ServerConfig
from app.remote.protocol import recv_frame, send_frame
from app.remote.server import _RemoteServer
from app.swift_ui.db import bootstrap_database, connect, now_ms


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a bootstrapped temporary database with a fresh daemon heartbeat."""
    path = tmp_path / "queue.db"
    bootstrap_database(path)
    connection = connect(path)
    try:
        connection.execute(
            "INSERT INTO daemon (id, pid, host, version, heartbeat_at_ms) VALUES (1, ?, ?, ?, ?)",
            (4321, "host", "test", now_ms()),
        )
    finally:
        connection.close()
    return path


def _hook_input_json(cwd: Path) -> str:
    """Return a minimal permission-request payload as JSON."""
    return json.dumps(
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": str(cwd),
        }
    )


def _wait_for_request(db_path: Path, timeout: float = 3.0) -> str:
    """Block until a pending request row appears and return its uid."""
    connection = connect(db_path)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = connection.execute(
                "SELECT request_uid FROM requests WHERE status = 'pending' "
                "ORDER BY created_at_ms DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                return row["request_uid"]
            time.sleep(0.01)
    finally:
        connection.close()
    raise AssertionError("request row never appeared")


def _request_status(db_path: Path, request_uid: str) -> str:
    """Return the current status of a request row."""
    connection = connect(db_path)
    try:
        return connection.execute(
            "SELECT status FROM requests WHERE request_uid = ?", (request_uid,)
        ).fetchone()[0]
    finally:
        connection.close()


def _answer_when_pending(db_path: Path, *, selected_index: int, stop: threading.Event) -> None:
    """Fake Swift UI: insert a response for the first pending request, then return."""
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not stop.is_set():
        try:
            uid = _wait_for_request(db_path, timeout=0.2)
        except AssertionError:
            continue
        connection = connect(db_path)
        try:
            connection.execute(
                "INSERT INTO responses "
                "(request_uid, selected_index, answers_json, cancelled, action, freetext, "
                "responder, created_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, selected_index, None, 0, None, None, "swift_ui", now_ms()),
            )
        finally:
            connection.close()
        return


def _serve(config: ServerConfig) -> tuple[_RemoteServer, threading.Thread, tuple[str, int]]:
    """Start a broker on an ephemeral port in a background thread."""
    server = _RemoteServer(config)
    address = server.server_address  # (host, port) with the OS-chosen port
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    return server, thread, (address[0], address[1])


# --- protocol framing ---------------------------------------------------------------


def test_protocol_round_trip() -> None:
    left, right = socket.socketpair()
    try:
        send_frame(left, {"provider": "claude-code", "stdin": "{}"})
        assert recv_frame(right) == {"provider": "claude-code", "stdin": "{}"}
    finally:
        left.close()
        right.close()


def test_protocol_returns_none_on_clean_close() -> None:
    left, right = socket.socketpair()
    try:
        left.close()
        assert recv_frame(right) is None
    finally:
        right.close()


# --- fail-open client ---------------------------------------------------------------


def test_client_no_address_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_HOOK_SERVER_ADDR", raising=False)
    out, err = StringIO(), StringIO()
    code = forward_remote("{}", "claude-code", stdout=out, stderr=err)
    assert code == 0
    assert out.getvalue() == ""
    assert "unset" in err.getvalue()


def test_client_unreachable_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bind then immediately close a port so it is (almost certainly) refused.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    monkeypatch.setenv("AGENT_HOOK_SERVER_ADDR", f"127.0.0.1:{port}")
    out, err = StringIO(), StringIO()
    code = forward_remote("{}", "claude-code", stdout=out, stderr=err)
    assert code == 0
    assert out.getvalue() == ""
    assert "unreachable" in err.getvalue()


# --- end-to-end broker round-trip ---------------------------------------------------


def test_server_round_trip_returns_decision(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_HOOK_DB_PATH", str(db_path))
    monkeypatch.setenv("AGENT_HOOK_SQLITE_POLL_INTERVAL", "0.05")
    server, thread, (host, port) = _serve(ServerConfig(host="127.0.0.1", port=0, token=None))
    stop = threading.Event()
    ui = threading.Thread(
        target=_answer_when_pending, args=(db_path,), kwargs={"selected_index": 0, "stop": stop}
    )
    ui.daemon = True
    ui.start()
    try:
        monkeypatch.setenv("AGENT_HOOK_SERVER_ADDR", f"{host}:{port}")
        out, err = StringIO(), StringIO()
        code = forward_remote(_hook_input_json(tmp_path), "claude-code", stdout=out, stderr=err)
        assert code == 0
        # The broker ran the real callback and returned a hook decision as JSON.
        decision = json.loads(out.getvalue())
        assert isinstance(decision, dict)
        # The request row was stamped with the SERVER's host (not a container), so the
        # Swift janitor's same-host liveness check applies.
        connection = connect(db_path)
        try:
            row = connection.execute(
                "SELECT owner_host, provider FROM requests ORDER BY created_at_ms DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
        assert row["owner_host"] == socket.gethostname()
        assert row["provider"] == "claude-code"
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_server_cancels_request_on_client_disconnect(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_HOOK_DB_PATH", str(db_path))
    monkeypatch.setenv("AGENT_HOOK_SQLITE_POLL_INTERVAL", "0.05")
    server, thread, (host, port) = _serve(ServerConfig(host="127.0.0.1", port=0, token=None))
    try:
        sock = socket.create_connection((host, port), timeout=3)
        send_frame(sock, {"provider": "claude-code", "stdin": _hook_input_json(tmp_path)})
        uid = _wait_for_request(db_path)
        # Disconnect before answering: the broker must cancel the pending request.
        sock.close()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if _request_status(db_path, uid) == "cancelled":
                break
            time.sleep(0.02)
        assert _request_status(db_path, uid) == "cancelled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_server_rejects_bad_token(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_HOOK_DB_PATH", str(db_path))
    server, thread, (host, port) = _serve(ServerConfig(host="127.0.0.1", port=0, token="secret"))
    try:
        sock = socket.create_connection((host, port), timeout=3)
        send_frame(sock, {"provider": "claude-code", "token": "wrong", "stdin": "{}"})
        response = recv_frame(sock)
        sock.close()
        assert response is not None
        assert response.get("error") == "unauthorized"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
