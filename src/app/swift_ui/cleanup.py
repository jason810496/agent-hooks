"""Mark a hook's pending request cancelled when the process is interrupted.

When the user answers a permission prompt directly in the session (for example by
pressing ESC), Claude Code terminates the blocking hook subprocess. These handlers
make a best-effort attempt to flip the still-pending request to ``cancelled`` so the
Swift app clears the card immediately. A hard ``SIGKILL`` cannot be trapped; that
case is covered by the Swift janitor via the dead ``owner_pid`` and stale heartbeat.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import signal
import sqlite3
import threading
from pathlib import Path

_lock = threading.Lock()
_pending: dict[str, str] = {}
_installed = False


def register_pending(db_path: str | Path, request_uid: str) -> None:
    """Record a request as awaiting a response so it can be cancelled on exit.

    :param db_path: Database holding the request row.
    :type db_path: str | Path
    :param request_uid: Unique id of the pending request.
    :type request_uid: str
    """
    with _lock:
        _pending[request_uid] = str(db_path)


def resolve_pending(request_uid: str) -> None:
    """Drop a request from the pending set once it is answered or expired.

    :param request_uid: Unique id of the request to forget.
    :type request_uid: str
    """
    with _lock:
        _pending.pop(request_uid, None)


def _mark_all_cancelled() -> None:
    """Best-effort flip every still-pending request to ``cancelled``."""
    with _lock:
        items = list(_pending.items())
        _pending.clear()
    for request_uid, db_path in items:
        try:
            connection = sqlite3.connect(db_path, timeout=1.0, isolation_level=None)
            try:
                connection.execute("PRAGMA busy_timeout=1000")
                connection.execute(
                    "UPDATE requests SET status = 'cancelled' "
                    "WHERE request_uid = ? AND status = 'pending'",
                    (request_uid,),
                )
            finally:
                connection.close()
        except sqlite3.Error:
            pass


def _handle_signal(signum: int, frame: object) -> None:
    """Cancel pending requests, then re-raise the signal with default handling."""
    del frame
    _mark_all_cancelled()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def install_handlers() -> None:
    """Install the atexit and termination-signal cleanup handlers once."""
    global _installed
    if _installed:
        return
    _installed = True
    atexit.register(_mark_all_cancelled)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        # signal.signal only works on the main thread and some signals are
        # platform-specific; skip quietly when unavailable.
        with contextlib.suppress(ValueError, OSError, AttributeError):
            signal.signal(sig, _handle_signal)


__all__ = ["install_handlers", "register_pending", "resolve_pending"]
