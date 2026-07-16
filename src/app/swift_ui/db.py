"""Open, bootstrap, and probe the shared SQLite IPC database."""

from __future__ import annotations

import sqlite3
import time
from functools import cache
from pathlib import Path
from typing import Final

SCHEMA_PATH: Final = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION: Final = 3
CONNECT_TIMEOUT_SECONDS: Final = 5.0
BUSY_TIMEOUT_MS: Final = 5000
# A daemon heartbeat older than this is treated as "no daemon running".
DAEMON_MAX_AGE_MS: Final = 15_000
CODEX_USER_INPUT_MIN_UI_VERSION: Final = (0, 3, 1)


def now_ms() -> int:
    """Return the current wall-clock time in integer milliseconds.

    :return: Milliseconds since the Unix epoch.
    """
    return int(time.time() * 1000)


@cache
def get_schema_sql() -> str:
    """Return the cached canonical schema SQL.

    :return: Contents of the packaged ``schema.sql``.
    """
    return SCHEMA_PATH.read_text(encoding="utf-8")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open an autocommit WAL connection, creating the parent directory if needed.

    :param db_path: Path to the SQLite database file.
    :type db_path: str | Path
    :return: Configured SQLite connection with ``sqlite3.Row`` rows.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        str(path),
        timeout=CONNECT_TIMEOUT_SECONDS,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def bootstrap_database(db_path: str | Path) -> Path:
    """Create the schema when the database is new or behind ``SCHEMA_VERSION``.

    :param db_path: Path to the SQLite database file.
    :type db_path: str | Path
    :return: The resolved database path.
    """
    connection = connect(db_path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if int(version) < SCHEMA_VERSION:
            connection.executescript(get_schema_sql())
    finally:
        connection.close()
    return Path(db_path)


def _read_daemon_metadata(db_path: str | Path) -> tuple[str | None, int] | None:
    """Read the Swift daemon version and heartbeat without creating the database.

    :param db_path: Path to the SQLite database file.
    :type db_path: str | Path
    :return: The daemon version and heartbeat, or ``None`` when unavailable.
    """
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        connection = sqlite3.connect(str(path), timeout=1.0)
    except sqlite3.Error:
        return None
    try:
        connection.execute("PRAGMA busy_timeout=1000")
        row = connection.execute(
            "SELECT version, heartbeat_at_ms FROM daemon WHERE id = 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if not row or row[1] is None:
        return None
    version = row[0] if isinstance(row[0], str) else None
    try:
        heartbeat_at_ms = int(row[1])
    except (TypeError, ValueError):
        return None
    return version, heartbeat_at_ms


def _heartbeat_is_fresh(heartbeat_at_ms: int, *, current_ms: int | None = None) -> bool:
    """Return whether a daemon heartbeat is within the accepted age window."""
    reference = now_ms() if current_ms is None else current_ms
    return (reference - heartbeat_at_ms) <= DAEMON_MAX_AGE_MS


def _version_tuple(version: str | None) -> tuple[int, int, int] | None:
    """Parse a three-component semantic version, ignoring prerelease metadata."""
    if version is None:
        return None
    core = version.split("+", maxsplit=1)[0].split("-", maxsplit=1)[0]
    parts = core.split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError:
        return None
    if any(part < 0 for part in (major, minor, patch)):
        return None
    return major, minor, patch


def daemon_is_alive(db_path: str | Path, *, current_ms: int | None = None) -> bool:
    """Return whether the Swift daemon has heartbeated recently.

    The check never creates the database file: a missing file, a missing
    ``daemon`` table, or a stale heartbeat all read as "no daemon running" so the
    hook can fall back to AppleScript instead of blocking forever.

    :param db_path: Path to the SQLite database file.
    :type db_path: str | Path
    :param current_ms: Override for the current time in milliseconds (testing).
    :type current_ms: int | None
    :return: ``True`` when a fresh daemon heartbeat exists.
    """
    metadata = _read_daemon_metadata(db_path)
    return metadata is not None and _heartbeat_is_fresh(metadata[1], current_ms=current_ms)


def daemon_supports_codex_user_input(
    db_path: str | Path,
    *,
    current_ms: int | None = None,
) -> bool:
    """Return whether the live Swift UI can render Codex user-input requests.

    This capability check prevents the app-server proxy from handing a Codex
    question to an older UI that would display it as a generic deny-only card.

    :param db_path: Path to the SQLite database file.
    :type db_path: str | Path
    :param current_ms: Override for the current time in milliseconds (testing).
    :type current_ms: int | None
    :return: ``True`` for a fresh, compatible Swift UI daemon.
    """
    metadata = _read_daemon_metadata(db_path)
    if metadata is None or not _heartbeat_is_fresh(metadata[1], current_ms=current_ms):
        return False
    version = _version_tuple(metadata[0])
    return version is not None and version >= CODEX_USER_INPUT_MIN_UI_VERSION


__all__ = [
    "CODEX_USER_INPUT_MIN_UI_VERSION",
    "DAEMON_MAX_AGE_MS",
    "SCHEMA_VERSION",
    "bootstrap_database",
    "connect",
    "daemon_is_alive",
    "daemon_supports_codex_user_input",
    "get_schema_sql",
    "now_ms",
]
