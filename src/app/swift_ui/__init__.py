"""SQLite IPC layer for the native macOS UI (the ``--ui swift-ui`` backend)."""

from __future__ import annotations

from app.swift_ui.cleanup import install_handlers
from app.swift_ui.db import bootstrap_database, daemon_is_alive, now_ms
from app.swift_ui.queue import resolve_queue
from app.swift_ui.transport import SQLiteTransport

__all__ = [
    "SQLiteTransport",
    "bootstrap_database",
    "daemon_is_alive",
    "install_handlers",
    "now_ms",
    "resolve_queue",
]
