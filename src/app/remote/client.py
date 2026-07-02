"""Forward a hook invocation to a host-side ``agent-hooks server`` (``--ui remote``).

Instead of touching the SQLite database (impossible from inside a container across the
Docker Desktop VM boundary), this dials the host broker over TCP, hands it the raw hook
stdin, and prints whatever decision the broker returns. It is deliberately fail-open: if
the broker is unset or unreachable the hook exits ``0`` with no output so a sandboxed agent
is never blocked by a UI that happens to be down.
"""

from __future__ import annotations

import socket
import sys
from typing import IO

from agent_hooks.enums import HookProvider
from app.remote.config import load_client_address, load_client_token
from app.remote.protocol import recv_frame, send_frame

CONNECT_TIMEOUT_SECONDS = 5.0


def forward_remote(
    raw_stdin: str,
    provider: HookProvider | str | None,
    *,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    """Forward one hook to the remote broker and emit its decision.

    :param raw_stdin: Raw hook JSON read from stdin.
    :type raw_stdin: str
    :param provider: Hook protocol provider (passed through to the server).
    :type provider: HookProvider | str | None
    :param stdout: Optional stdout override (defaults to :data:`sys.stdout`).
    :type stdout: IO[str] | None
    :param stderr: Optional stderr override (defaults to :data:`sys.stderr`).
    :type stderr: IO[str] | None
    :return: Process exit code. Always ``0`` on any transport failure (fail-open).
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    # Diagnostics go to stderr only: this runs as a hook, so stdout must stay valid JSON.
    def note(message: str) -> None:
        err.write(f"{message}\n")

    address = load_client_address()
    if address is None:
        note("[agent-hooks] AGENT_HOOK_SERVER_ADDR unset; skipping remote hook")
        return 0

    frame: dict[str, object] = {"provider": _provider_value(provider), "stdin": raw_stdin}
    token = load_client_token()
    if token:
        frame["token"] = token

    try:
        with socket.create_connection(address, timeout=CONNECT_TIMEOUT_SECONDS) as sock:
            # Block indefinitely for the response: a human may take minutes to answer. If the
            # server dies the OS surfaces it as a socket error, which we treat as fail-open.
            sock.settimeout(None)
            send_frame(sock, frame)
            response = recv_frame(sock)
    except OSError as exc:
        note(f"[agent-hooks] remote hook unreachable ({exc}); proceeding")
        return 0
    except ValueError as exc:
        note(f"[agent-hooks] remote hook protocol error ({exc}); proceeding")
        return 0

    if response is None:
        note("[agent-hooks] remote hook closed without a response; proceeding")
        return 0
    error = response.get("error")
    if error:
        note(f"[agent-hooks] remote hook error ({error}); proceeding")
        return 0

    out.write(str(response.get("stdout", "")))
    out.flush()
    code = response.get("exit_code", 0)
    return code if isinstance(code, int) else 0


def _provider_value(provider: HookProvider | str | None) -> str | None:
    """Reduce a provider to a plain string for the wire, or ``None``."""
    if provider is None:
        return None
    if isinstance(provider, HookProvider):
        return provider.value
    return str(provider)


__all__ = ["forward_remote"]
