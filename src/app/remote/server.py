"""Host-side TCP broker that runs the local callback for remote (containerized) clients.

``agent-hooks server`` listens on a TCP port on the host. For each connection it runs the
same callback path the local CLI would (``run_callback`` + the swift-ui ``SQLiteTransport``),
so the Swift daemon renders the card unchanged and the user's answer flows back over the
socket. Only host processes ever touch the SQLite database; remote clients speak the socket
protocol and never see the file. That is what makes a sandboxed agent's prompts reach the
host UI safely: WAL-mode SQLite cannot be shared across the macOS <-> Docker VM boundary,
but a TCP round-trip can.

Process control mirrors a tiny daemon manager: ``start`` spawns a detached ``--foreground``
child and records its pid beside the database; ``stop``/``status`` act on that pidfile.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from io import StringIO

from agent_hooks.config import load_runtime_config
from agent_hooks.runner import run_callback
from app.builtin import app as builtin_app
from app.remote.config import (
    SERVER_HOST_ENV_VAR,
    SERVER_PORT_ENV_VAR,
    SERVER_TOKEN_ENV_VAR,
    ServerConfig,
    load_server_config,
    logfile_path,
    pidfile_path,
)
from app.remote.protocol import recv_frame, send_frame
from app.transports import SWIFT_UI, build_transport

_STARTUP_PROBE_SECONDS = 0.4
_STOP_TIMEOUT_SECONDS = 5.0


def _say(message: str) -> None:
    """Emit a CLI/status line to stderr (this package keeps stdout for hook JSON only)."""
    print(message, file=sys.stderr, flush=True)


def run_server_command(args: argparse.Namespace) -> int:
    """Dispatch ``agent-hooks server <action>``.

    :param args: Parsed CLI namespace (``action``, ``host``, ``port``, ``token``,
        ``foreground``).
    :type args: argparse.Namespace
    :return: Process exit code.
    """
    action = args.action
    if action == "start":
        config = load_server_config(host=args.host, port=args.port, token=args.token)
        return _start(config, foreground=bool(getattr(args, "foreground", False)))
    if action == "stop":
        return _stop()
    if action == "status":
        return _status()
    print(f"unknown server action: {action}", file=sys.stderr)
    return 2


class _RemoteServer(socketserver.ThreadingTCPServer):
    """Threaded TCP server; one worker thread per in-flight hook connection."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, config: ServerConfig) -> None:
        """Bind to ``config.host:config.port`` and remember the shared token."""
        self.token = config.token
        super().__init__((config.host, config.port), _Handler)


class _Handler(socketserver.BaseRequestHandler):
    """Run one hook round-trip for a single client connection."""

    def handle(self) -> None:
        """Read the request frame, run the callback, and send the decision back."""
        server: _RemoteServer = self.server  # type: ignore[assignment]
        conn: socket.socket = self.request
        try:
            request = recv_frame(conn)
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if request is None:
            return

        if server.token is not None and request.get("token") != server.token:
            with contextlib.suppress(OSError):
                send_frame(conn, {"exit_code": 1, "stdout": "", "error": "unauthorized"})
            return

        raw = str(request.get("stdin", "") or "")
        provider = request.get("provider")
        code, out, error = _run_callback_capturing(conn, raw, provider)
        with contextlib.suppress(OSError):
            send_frame(conn, {"exit_code": code, "stdout": out, "error": error})


def _run_callback_capturing(
    conn: socket.socket, raw: str, provider: object
) -> tuple[int, str, str | None]:
    """Run the built-in callback with a swift-ui transport, capturing its stdout.

    The transport is given a "client socket closed" cancel predicate so that if the remote
    client disconnects while the user has not yet answered, the pending card is cleared.
    Any exception is swallowed into an ``error`` string so the broker never drops the
    connection without a reply (the client then fails open).
    """

    def client_closed() -> bool:
        try:
            peeked = conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
        except BlockingIOError:
            return False  # still connected, nothing pending
        except OSError:
            return True  # socket errored: treat as gone
        return peeked == b""  # empty read == peer closed

    out = StringIO()
    provider_arg = provider if isinstance(provider, str) else None
    try:
        config = load_runtime_config()
        transport = build_transport(
            SWIFT_UI,
            config=config,
            raw_input=raw,
            provider=provider_arg,
            cancel_check=client_closed,
        )
        code = run_callback(
            builtin_app,
            stdin=StringIO(raw),
            stdout=out,
            transport=transport,
            provider=provider_arg,
        )
        return code, out.getvalue(), None
    except Exception as exc:
        # The broker must always answer the client, so no error escapes this handler.
        return 1, out.getvalue(), f"{type(exc).__name__}: {exc}"


def _run_foreground(config: ServerConfig) -> int:
    """Serve in the foreground until SIGTERM/SIGINT. Used by ``--foreground`` / launchd."""
    try:
        server = _RemoteServer(config)
    except OSError as exc:
        print(f"agent-hooks server failed to bind {config.host}:{config.port}: {exc}", file=sys.stderr)
        return 1

    def _request_shutdown(signum: int, frame: object) -> None:
        del signum, frame
        # serve_forever() blocks this (main) thread, so shutdown() must run elsewhere.
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, _request_shutdown)

    _say(
        f"agent-hooks server listening on {config.host}:{config.port} "
        f"(token {'set' if config.token else 'unset'})"
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


def _start(config: ServerConfig, *, foreground: bool) -> int:
    """Start the broker: run in-process when ``foreground``, else spawn a detached child."""
    if foreground:
        return _run_foreground(config)

    existing = _read_pid()
    if existing is not None and _pid_alive(existing):
        _say(f"agent-hooks server already running (pid {existing})")
        return 0

    pidfile = pidfile_path()
    logfile = logfile_path()
    pidfile.parent.mkdir(parents=True, exist_ok=True)

    # Pass the resolved settings via env (not argv) so the token never shows up in `ps`.
    child_env = dict(os.environ)
    child_env[SERVER_HOST_ENV_VAR] = config.host
    child_env[SERVER_PORT_ENV_VAR] = str(config.port)
    if config.token:
        child_env[SERVER_TOKEN_ENV_VAR] = config.token
    else:
        child_env.pop(SERVER_TOKEN_ENV_VAR, None)

    log_handle = open(logfile, "ab", buffering=0)  # noqa: SIM115 - handed to the child process
    try:
        process = subprocess.Popen(
            [sys.argv[0], "server", "start", "--foreground"],
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_handle.close()

    pidfile.write_text(str(process.pid))
    time.sleep(_STARTUP_PROBE_SECONDS)
    if process.poll() is not None:
        with contextlib.suppress(OSError):
            pidfile.unlink()
        _say(f"agent-hooks server failed to start; see {logfile}")
        return 1

    _say(
        f"agent-hooks server started (pid {process.pid}) on {config.host}:{config.port}; "
        f"logs at {logfile}"
    )
    return 0


def _stop() -> int:
    """Stop the running broker via its pidfile."""
    pid = _read_pid()
    if pid is None:
        _say("agent-hooks server is not running (no pidfile)")
        return 0
    if not _pid_alive(pid):
        with contextlib.suppress(OSError):
            pidfile_path().unlink()
        _say("agent-hooks server is not running (removed stale pidfile)")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        _say(f"failed to stop agent-hooks server (pid {pid}): {exc}")
        return 1
    deadline = time.monotonic() + _STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    with contextlib.suppress(OSError):
        pidfile_path().unlink()
    _say(f"agent-hooks server stopped (pid {pid})")
    return 0


def _status() -> int:
    """Report whether the broker is running."""
    pid = _read_pid()
    if pid is not None and _pid_alive(pid):
        _say(f"agent-hooks server is running (pid {pid})")
        return 0
    _say("agent-hooks server is not running")
    return 1


def _read_pid() -> int | None:
    """Return the pid recorded in the pidfile, or ``None`` when absent/invalid."""
    try:
        text = pidfile_path().read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _pid_alive(pid: int) -> bool:
    """Return whether ``pid`` names a live process."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


__all__ = ["run_server_command"]
