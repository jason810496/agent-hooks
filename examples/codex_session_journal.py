"""Persist Codex lifecycle events into a local JSONL session journal."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent_hooks import (
    AgentHook,
    HookProvider,
    HookResponse,
    PostToolUseEvent,
    SessionStartEvent,
    StopEvent,
    UserPromptSubmitEvent,
)

DEFAULT_JOURNAL_DIRECTORY = ".agent-hooks/session-journal"

app = AgentHook(fallback_handler=None, provider=HookProvider.CODEX)


def now_timestamp() -> str:
    """Return the current UTC timestamp.

    :return: ISO 8601 UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def compact_text(text: str, *, limit: int = 240) -> str:
    """Compact multi-line text into one bounded line.

    :param text: Raw text value to compact.
    :type text: str
    :param limit: Maximum output length.
    :type limit: int
    :return: One-line compacted text preview.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def normalize_session_id(session_id: str) -> str:
    """Return a filesystem-safe session identifier.

    :param session_id: Raw session identifier from the hook payload.
    :type session_id: str
    :return: Sanitized identifier suitable for a filename.
    """
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in session_id
    )
    return cleaned or "unknown-session"


def resolve_journal_directory(cwd: str) -> Path:
    """Resolve the directory used for session journal files.

    :param cwd: Working directory from the callback payload.
    :type cwd: str
    :return: Directory where journal files should be stored.
    """
    configured_directory = os.environ.get("AGENT_HOOK_SESSION_JOURNAL_DIR", "").strip()
    base_directory = Path(cwd) if cwd else Path.cwd()
    if configured_directory:
        journal_directory = Path(configured_directory).expanduser()
        if not journal_directory.is_absolute():
            journal_directory = base_directory / journal_directory
        return journal_directory
    return base_directory / DEFAULT_JOURNAL_DIRECTORY


def resolve_journal_path(session_id: str, cwd: str) -> Path:
    """Resolve the JSONL file path for one session.

    :param session_id: Session identifier from the hook payload.
    :type session_id: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :return: JSONL path for the session journal.
    """
    journal_directory = resolve_journal_directory(cwd)
    return journal_directory / f"{normalize_session_id(session_id)}.jsonl"


def append_session_record(session_id: str, cwd: str, record: dict[str, object]) -> None:
    """Append one record to the file-backed session journal.

    :param session_id: Session identifier from the hook payload.
    :type session_id: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :param record: JSON-serializable record to append.
    :type record: dict[str, object]
    """
    journal_path = resolve_journal_path(session_id, cwd)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, separators=(",", ":"))
        handle.write("\n")


@app.session_start()
def session_start_handler(hook_event: SessionStartEvent) -> HookResponse:
    """Record the start of a Codex session.

    :param hook_event: Session-start event from Codex.
    :type hook_event: SessionStartEvent
    :return: Empty response payload.
    """
    append_session_record(
        hook_event.session_id,
        hook_event.cwd,
        {
            "timestamp": now_timestamp(),
            "event": "SessionStart",
            "cwd": hook_event.cwd,
            "model": hook_event.model,
            "permission_mode": hook_event.permission_mode,
            "transcript_path": hook_event.transcript_path,
        },
    )
    return HookResponse()


@app.user_prompt_submit()
def user_prompt_submit_handler(hook_event: UserPromptSubmitEvent) -> HookResponse:
    """Record a user prompt submission.

    :param hook_event: User prompt event from Codex.
    :type hook_event: UserPromptSubmitEvent
    :return: Empty response payload.
    """
    append_session_record(
        hook_event.session_id,
        hook_event.cwd,
        {
            "timestamp": now_timestamp(),
            "event": "UserPromptSubmit",
            "prompt": compact_text(hook_event.prompt, limit=500),
            "source": hook_event.source,
            "last_assistant_message": compact_text(hook_event.last_assistant_message),
        },
    )
    return HookResponse()


@app.post_tool_use()
def post_tool_use_handler(hook_event: PostToolUseEvent) -> HookResponse:
    """Record a post-tool-use event.

    :param hook_event: Post-tool-use event from Codex.
    :type hook_event: PostToolUseEvent
    :return: Empty response payload.
    """
    append_session_record(
        hook_event.session_id,
        hook_event.cwd,
        {
            "timestamp": now_timestamp(),
            "event": "PostToolUse",
            "tool_name": hook_event.tool_name,
            "tool_use_id": hook_event.tool_use_id,
            "command": compact_text(hook_event.tool_input.command),
            "prompt": compact_text(hook_event.tool_input.prompt),
            "last_assistant_message": compact_text(hook_event.last_assistant_message),
        },
    )
    return HookResponse()


@app.stop()
def stop_handler(hook_event: StopEvent) -> HookResponse:
    """Record the end of a Codex session.

    :param hook_event: Stop event from Codex.
    :type hook_event: StopEvent
    :return: Empty response payload.
    """
    append_session_record(
        hook_event.session_id,
        hook_event.cwd,
        {
            "timestamp": now_timestamp(),
            "event": "Stop",
            "last_assistant_message": compact_text(hook_event.last_assistant_message, limit=500),
        },
    )
    return HookResponse()
