"""Configuration for the swift-ui (SQLite-backed) UI backend.

These knobs are implementation details of the ``--ui swift-ui`` backend: where the shared
database lives and how long to poll/wait for the Swift app to answer. Users opt into the
backend with ``--ui swift-ui`` and never need to set any of these directly.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_FILENAME = "queue.db"
DEFAULT_POLL_INTERVAL_SECONDS = 0.2
DEFAULT_REQUEST_TIMEOUT_SECONDS = 0.0

DB_PATH_ENV_VAR = "AGENT_HOOK_DB_PATH"
POLL_INTERVAL_ENV_VAR = "AGENT_HOOK_SQLITE_POLL_INTERVAL"
REQUEST_TIMEOUT_ENV_VAR = "AGENT_HOOK_REQUEST_TIMEOUT"


def default_db_path() -> Path:
    """Return the default shared SQLite database path under Application Support.

    :return: ``~/Library/Application Support/agent-hooks/queue.db``.
    """
    return Path.home() / "Library" / "Application Support" / "agent-hooks" / DEFAULT_DB_FILENAME


@dataclass(frozen=True)
class SwiftUiConfig:
    """Store the swift-ui backend's database and polling settings."""

    db_path: Path
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS


def load_swift_ui_config(env: Mapping[str, str] | None = None) -> SwiftUiConfig:
    """Build the swift-ui configuration from the environment.

    :param env: Optional environment mapping override.
    :type env: Mapping[str, str] | None
    :return: Resolved swift-ui configuration.
    """
    environment = os.environ if env is None else env
    return SwiftUiConfig(
        db_path=_read_db_path(environment),
        poll_interval_seconds=_read_float(
            environment,
            POLL_INTERVAL_ENV_VAR,
            default=DEFAULT_POLL_INTERVAL_SECONDS,
            allow_zero=False,
        ),
        request_timeout_seconds=_read_float(
            environment,
            REQUEST_TIMEOUT_ENV_VAR,
            default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
            allow_zero=True,
        ),
    )


def _read_db_path(env: Mapping[str, str]) -> Path:
    """Resolve the database path from the environment, falling back to the default."""
    raw_value = env.get(DB_PATH_ENV_VAR)
    if raw_value is None or not raw_value.strip():
        return default_db_path()
    return Path(raw_value).expanduser()


def _read_float(
    env: Mapping[str, str],
    env_var: str,
    *,
    default: float,
    allow_zero: bool,
) -> float:
    """Parse a finite, non-negative float from the environment.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_var: Variable name to read.
    :type env_var: str
    :param default: Value returned when the variable is unset or invalid.
    :type default: float
    :param allow_zero: Whether ``0`` is a valid value (``True`` for the timeout, where
        ``0`` means "wait indefinitely"; ``False`` for the poll interval).
    :type allow_zero: bool
    :return: Parsed float, or the default.
    """
    raw_value = env.get(env_var)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    if not math.isfinite(value):
        return default
    if value < 0 or (value == 0 and not allow_zero):
        return default
    return value


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "SwiftUiConfig",
    "default_db_path",
    "load_swift_ui_config",
]
