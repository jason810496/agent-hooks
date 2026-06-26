"""Record per-session state into the shared SQLite database.

The Swift app renders a live "Sessions" panel from the ``sessions`` table. Because each hook
invocation is a short-lived process, this module is called once per event (from
``_build_swift_ui_transport``) to upsert the owning session's row. It writes the *round* state
(working / idle / failed) plus the agent process identity (``os.getppid()`` + hostname); the
Swift app derives live/dead from process liveness so aliveness is never persisted.

Recording is best-effort: any database error is swallowed so it can never break the hook
response (mirrors :meth:`SQLiteTransport.send_notification`).
"""

from __future__ import annotations

import os
import socket
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from agent_hooks.models.schemas.hooks import HookPayload
from app.swift_ui.db import connect, now_ms
from app.swift_ui.queue import resolve_queue

STATUS_WORKING = "working"
STATUS_IDLE = "idle"
STATUS_FAILED = "failed"

# Events that begin / continue a round (the session is actively working).
_WORKING_EVENTS = frozenset({"UserPromptSubmit", "PreToolUse", "PermissionRequest", "PostToolUse"})


@dataclass(frozen=True)
class _SessionState:
    """Merged column values to write for one session after an event."""

    queue: str
    cwd: str
    model: str | None
    transcript_path: str | None
    status: str
    tool_name: str | None
    round_started_ms: int | None
    last_round_ms: int | None
    error_text: str | None


def record_session_event(db_path: str | Path, payload: HookPayload) -> None:
    """Upsert the session row for one hook event.

    :param db_path: Path to the shared SQLite database.
    :type db_path: str | Path
    :param payload: Normalized payload for the event being handled.
    :type payload: HookPayload
    """
    session_id = payload.session_id
    if not session_id:
        return
    provider = payload.provider.value
    event = payload.raw_event_name
    pid = os.getppid()
    host = socket.gethostname()
    now = now_ms()
    try:
        connection = connect(db_path)
        try:
            existing = connection.execute(
                "SELECT status, tool_name, round_started_ms, last_round_ms, error_text, "
                "transcript_path, model, queue, cwd FROM sessions "
                "WHERE session_id = ? AND provider = ?",
                (session_id, provider),
            ).fetchone()
            state = _next_state(event, payload, existing, now)
            connection.execute(
                "INSERT INTO sessions ("
                " session_id, provider, queue, cwd, model, transcript_path,"
                " session_pid, session_host, status, last_event, tool_name,"
                " round_started_ms, last_round_ms, error_text, updated_at_ms"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(session_id, provider) DO UPDATE SET"
                "  queue = excluded.queue,"
                "  cwd = excluded.cwd,"
                "  model = excluded.model,"
                "  transcript_path = excluded.transcript_path,"
                "  session_pid = excluded.session_pid,"
                "  session_host = excluded.session_host,"
                "  status = excluded.status,"
                "  last_event = excluded.last_event,"
                "  tool_name = excluded.tool_name,"
                "  round_started_ms = excluded.round_started_ms,"
                "  last_round_ms = excluded.last_round_ms,"
                "  error_text = excluded.error_text,"
                "  updated_at_ms = excluded.updated_at_ms",
                (
                    session_id,
                    provider,
                    state.queue,
                    state.cwd,
                    state.model,
                    state.transcript_path,
                    pid,
                    host,
                    state.status,
                    event,
                    state.tool_name,
                    state.round_started_ms,
                    state.last_round_ms,
                    state.error_text,
                    now,
                ),
            )
        finally:
            connection.close()
    except sqlite3.Error:
        return


def _next_state(
    event: str,
    payload: HookPayload,
    existing: sqlite3.Row | None,
    now: int,
) -> _SessionState:
    """Merge the prior row with this event into the columns to persist."""
    prev_status = existing["status"] if existing else STATUS_IDLE
    prev_tool = existing["tool_name"] if existing else None
    prev_round_started = existing["round_started_ms"] if existing else None
    prev_last_round = existing["last_round_ms"] if existing else None
    prev_error = existing["error_text"] if existing else None
    prev_transcript = existing["transcript_path"] if existing else None
    prev_model = existing["model"] if existing else None
    prev_queue = existing["queue"] if existing else ""
    prev_cwd = existing["cwd"] if existing else ""

    # Identity / location fields prefer the freshest non-empty payload value.
    cwd = payload.cwd or prev_cwd
    queue = resolve_queue(payload.cwd) if payload.cwd else (prev_queue or cwd)
    model = payload.model or prev_model
    transcript_path = payload.transcript_path or prev_transcript

    status = prev_status
    tool_name = prev_tool
    round_started = prev_round_started
    last_round = prev_last_round
    error_text = prev_error

    if event == "SessionStart":
        status = STATUS_IDLE
        round_started = None
        tool_name = None
        error_text = None
    elif event == "UserPromptSubmit":
        status = STATUS_WORKING
        round_started = now
        error_text = None
    elif event in _WORKING_EVENTS:
        status = STATUS_WORKING
        if payload.tool_name:
            tool_name = payload.tool_name
        if round_started is None:
            round_started = now
    elif event == "Stop":
        status = STATUS_IDLE
        last_round = (now - round_started) if round_started is not None else prev_last_round
        round_started = None
        tool_name = None
        error_text = None
    elif event == "StopFailure":
        status = STATUS_FAILED
        last_round = (now - round_started) if round_started is not None else prev_last_round
        round_started = None
        error_text = payload.error_details or payload.error or "Last round failed"
    # Any other event (e.g. Notification) only refreshes identity + heartbeat fields.

    return _SessionState(
        queue=queue,
        cwd=cwd,
        model=model,
        transcript_path=transcript_path,
        status=status,
        tool_name=tool_name,
        round_started_ms=round_started,
        last_round_ms=last_round,
        error_text=error_text,
    )


__all__ = ["record_session_event"]
