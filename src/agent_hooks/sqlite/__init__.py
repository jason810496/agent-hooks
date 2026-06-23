"""SQLite IPC layer for the native macOS UI (opt-in ``AGENT_HOOK_UI=sqlite``)."""

from __future__ import annotations

from agent_hooks.sqlite.cleanup import install_handlers
from agent_hooks.sqlite.db import bootstrap_database, daemon_is_alive, now_ms
from agent_hooks.sqlite.queue import resolve_queue
from agent_hooks.sqlite.transport import SQLiteTransport

__all__ = [
    "SQLiteTransport",
    "bootstrap_database",
    "daemon_is_alive",
    "install_handlers",
    "now_ms",
    "resolve_queue",
]
