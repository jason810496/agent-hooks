"""Configuration for the remote hook bridge (``agent-hooks server`` and ``--ui remote``).

The server and client resolve their address/token from CLI flags first, then these
environment variables, then built-in defaults. The database used by the server is the same
one the swift-ui backend uses (see :mod:`app.swift_ui.config`); only the transport differs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.swift_ui.config import default_db_path

SERVER_HOST_ENV_VAR = "AGENT_HOOK_SERVER_HOST"
SERVER_PORT_ENV_VAR = "AGENT_HOOK_SERVER_PORT"
SERVER_TOKEN_ENV_VAR = "AGENT_HOOK_SERVER_TOKEN"
# Client-side "host:port" of the server to dial (used by ``--ui remote``).
SERVER_ADDR_ENV_VAR = "AGENT_HOOK_SERVER_ADDR"

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 48373

PIDFILE_NAME = "server.pid"
LOGFILE_NAME = "server.log"


@dataclass(frozen=True)
class ServerConfig:
    """Bind settings for the host-side broker."""

    host: str
    port: int
    token: str | None


def load_server_config(
    env: Mapping[str, str] | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    token: str | None = None,
) -> ServerConfig:
    """Resolve the server bind settings (CLI flag > env var > default).

    :param env: Optional environment mapping override.
    :type env: Mapping[str, str] | None
    :param host: Bind address from a CLI flag, if given.
    :type host: str | None
    :param port: Bind port from a CLI flag, if given.
    :type port: int | None
    :param token: Shared secret from a CLI flag, if given.
    :type token: str | None
    :return: Resolved :class:`ServerConfig`.
    """
    environment = os.environ if env is None else env
    resolved_host = host or (environment.get(SERVER_HOST_ENV_VAR) or "").strip() or DEFAULT_SERVER_HOST
    resolved_port = port if port is not None else _read_port(environment)
    resolved_token = token if token is not None else _clean_token(environment.get(SERVER_TOKEN_ENV_VAR))
    return ServerConfig(host=resolved_host, port=resolved_port, token=resolved_token)


def load_client_address(env: Mapping[str, str] | None = None) -> tuple[str, int] | None:
    """Parse the client-side ``host:port`` from :data:`SERVER_ADDR_ENV_VAR`.

    :param env: Optional environment mapping override.
    :type env: Mapping[str, str] | None
    :return: ``(host, port)`` or ``None`` when unset/invalid (client then no-ops).
    """
    environment = os.environ if env is None else env
    raw = (environment.get(SERVER_ADDR_ENV_VAR) or "").strip()
    if not raw:
        return None
    host, separator, port = raw.rpartition(":")
    if not separator or not host or not port.isdigit():
        return None
    return host, int(port)


def load_client_token(env: Mapping[str, str] | None = None) -> str | None:
    """Return the shared secret the client should present, if any."""
    environment = os.environ if env is None else env
    return _clean_token(environment.get(SERVER_TOKEN_ENV_VAR))


def pidfile_path() -> Path:
    """Return the server pidfile path (beside the shared database)."""
    return default_db_path().parent / PIDFILE_NAME


def logfile_path() -> Path:
    """Return the server logfile path (beside the shared database)."""
    return default_db_path().parent / LOGFILE_NAME


def _read_port(env: Mapping[str, str]) -> int:
    """Parse the bind port from the environment, falling back to the default."""
    raw = (env.get(SERVER_PORT_ENV_VAR) or "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_SERVER_PORT


def _clean_token(value: str | None) -> str | None:
    """Normalize a token, treating blank as unset."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


__all__ = [
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "SERVER_ADDR_ENV_VAR",
    "SERVER_HOST_ENV_VAR",
    "SERVER_PORT_ENV_VAR",
    "SERVER_TOKEN_ENV_VAR",
    "ServerConfig",
    "load_client_address",
    "load_client_token",
    "load_server_config",
    "logfile_path",
    "pidfile_path",
]
