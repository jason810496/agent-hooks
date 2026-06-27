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
    path = Path(db_path)
    if not path.exists():
        return False
    try:
        connection = sqlite3.connect(str(path), timeout=1.0)
    except sqlite3.Error:
        return False
    try:
        connection.execute("PRAGMA busy_timeout=1000")
        row = connection.execute("SELECT heartbeat_at_ms FROM daemon WHERE id = 1").fetchone()
    except sqlite3.Error:
        return False
    finally:
        connection.close()
    if not row or row[0] is None:
        return False
    reference = now_ms() if current_ms is None else current_ms
    return (reference - int(row[0])) <= DAEMON_MAX_AGE_MS


__all__ = [
    "DAEMON_MAX_AGE_MS",
    "SCHEMA_VERSION",
    "bootstrap_database",
    "connect",
    "daemon_is_alive",
    "get_schema_sql",
    "now_ms",
]
