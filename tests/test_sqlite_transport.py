"""Tests for the SQLite-backed display transport and the ``--ui`` transport factory."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agent_hooks.config import load_runtime_config
from agent_hooks.enums import DialogButton, HookEventName, HookProvider, TransportStatus
from agent_hooks.models.schemas.display import (
    AskUserQuestionDialogSpec,
    AskUserQuestionEntry,
    AskUserQuestionOption,
    DialogSpec,
    NotificationSpec,
)
from agent_hooks.models.schemas.hooks import HookPayload, ToolInput
from app.swift_ui import cleanup
from app.swift_ui.db import bootstrap_database, connect, now_ms
from app.swift_ui.transport import SQLiteTransport

PERMISSION_BUTTONS = (DialogButton.DENY, DialogButton.ALLOW_ONCE, DialogButton.ALWAYS_ALLOW)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a bootstrapped temporary database path."""
    path = tmp_path / "queue.db"
    bootstrap_database(path)
    return path


def _payload(
    *,
    cwd: str,
    event_name: HookEventName = HookEventName.PERMISSION_REQUEST,
    tool_name: str = "Bash",
    raw: dict | None = None,
    tool_input_raw: dict | None = None,
    raw_notification_type: str = "",
) -> HookPayload:
    """Build a minimal normalized payload for transport tests."""
    return HookPayload(
        raw=raw or {},
        provider=HookProvider.CLAUDE_CODE,
        event_name=event_name,
        raw_notification_type=raw_notification_type,
        session_id="sess-1",
        cwd=cwd,
        tool_name=tool_name,
        tool_use_id="tool-1",
        tool_input=ToolInput(raw=tool_input_raw or {}),
    )


def _run_blocking(fn: Callable[[], Any]) -> tuple[threading.Thread, dict[str, Any]]:
    """Run a blocking transport call in a worker thread, returning the thread and a box."""
    box: dict[str, Any] = {}

    def target() -> None:
        box["result"] = fn()

    thread = threading.Thread(target=target)
    thread.start()
    return thread, box


def _wait_for_request(db_path: Path, timeout: float = 3.0) -> str:
    """Block until a pending request row appears and return its uid."""
    connection = connect(db_path)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = connection.execute(
                "SELECT request_uid FROM requests WHERE status = 'pending' "
                "ORDER BY created_at_ms DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                return row["request_uid"]
            time.sleep(0.01)
    finally:
        connection.close()
    raise AssertionError("request row never appeared")


def _insert_response(
    db_path: Path,
    request_uid: str,
    *,
    selected_index: int | None = None,
    answers: dict[str, str] | None = None,
    cancelled: bool = False,
    action: str | None = None,
    freetext: str | None = None,
) -> None:
    """Insert a Swift-side response row for one request."""
    connection = connect(db_path)
    try:
        connection.execute(
            "INSERT INTO responses "
            "(request_uid, selected_index, answers_json, cancelled, action, freetext, responder, "
            "created_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_uid,
                selected_index,
                json.dumps(answers) if answers is not None else None,
                1 if cancelled else 0,
                action,
                freetext,
                "swift_ui",
                now_ms(),
            ),
        )
    finally:
        connection.close()


def _heartbeat(db_path: Path, request_uid: str) -> int:
    """Return the current heartbeat timestamp for a request."""
    connection = connect(db_path)
    try:
        return connection.execute(
            "SELECT heartbeat_at_ms FROM requests WHERE request_uid = ?", (request_uid,)
        ).fetchone()[0]
    finally:
        connection.close()


def test_show_dialog_maps_selected_button(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path)), db_path=db_path, poll_interval=0.02
    )
    dialog = DialogSpec(
        title="t", message="m", buttons=PERMISSION_BUTTONS, default_button=DialogButton.ALLOW_ONCE
    )
    thread, box = _run_blocking(lambda: transport.show_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(db_path, uid, selected_index=2)
    thread.join(timeout=3)

    result = box["result"]
    assert result.button == DialogButton.ALWAYS_ALLOW
    assert result.transport.status == TransportStatus.SUCCEEDED


def test_show_dialog_cancel_returns_no_button(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path)), db_path=db_path, poll_interval=0.02
    )
    dialog = DialogSpec(
        title="t", message="m", buttons=PERMISSION_BUTTONS, default_button=DialogButton.ALLOW_ONCE
    )
    thread, box = _run_blocking(lambda: transport.show_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(db_path, uid, cancelled=True)
    thread.join(timeout=3)

    assert box["result"].button is None


def test_permission_choice_persists_only_selected_suggestion(db_path: Path, tmp_path: Path) -> None:
    from agent_hooks.providers.claude_code.payload import build_hook_payload
    from agent_hooks.providers.claude_code.permissions import build_permission_choice_response
    from agent_hooks.providers.claude_code.presentation import build_permission_choice_dialog

    raw = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "cwd": str(tmp_path),
        "permission_suggestions": [
            {"id": "s-narrow", "rules": [{"toolName": "Bash", "ruleContent": "git status"}]},
            {"id": "s-broad", "rules": [{"toolName": "Bash", "ruleContent": "git *"}]},
        ],
    }
    payload = build_hook_payload(raw)
    dialog = build_permission_choice_dialog(payload)
    # choices == (Allow once, s-narrow[suggestion_index=0], s-broad[suggestion_index=1])
    transport = SQLiteTransport(payload=payload, db_path=db_path, poll_interval=0.02)
    thread, box = _run_blocking(lambda: transport.show_permission_choice_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(db_path, uid, selected_index=2)
    thread.join(timeout=3)

    choice = box["result"].choice
    assert choice is not None
    assert choice.suggestion_index == 1

    response = build_permission_choice_response(payload, choice)
    updates = response.hook_specific_output.decision.updated_permissions
    assert len(updates) == 1
    assert updates[0].source["id"] == "s-broad"


def test_permission_choice_records_options_json(db_path: Path, tmp_path: Path) -> None:
    from agent_hooks.providers.claude_code.payload import build_hook_payload
    from agent_hooks.providers.claude_code.presentation import build_permission_choice_dialog

    raw = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "cwd": str(tmp_path),
        "permission_suggestions": [
            {"id": "s-broad", "rules": [{"toolName": "Bash", "ruleContent": "git *"}]},
        ],
    }
    payload = build_hook_payload(raw)
    dialog = build_permission_choice_dialog(payload)
    transport = SQLiteTransport(payload=payload, db_path=db_path, poll_interval=0.02)
    thread, box = _run_blocking(lambda: transport.show_permission_choice_dialog(dialog))
    uid = _wait_for_request(db_path)

    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT kind, options_json, suggestions_json FROM requests WHERE request_uid = ?",
            (uid,),
        ).fetchone()
    finally:
        connection.close()
    options = json.loads(row["options_json"])
    assert row["kind"] == "permission_choice"
    # First choice allows once; the broad suggestion is rendered as its exact rule.
    assert options["choices"][0]["suggestion_index"] is None
    assert options["choices"][1]["label"] == "Bash(git *)"
    assert options["choices"][1]["suggestion_index"] == 0
    assert json.loads(row["suggestions_json"])[0]["id"] == "s-broad"

    _insert_response(db_path, uid, cancelled=True)
    thread.join(timeout=3)


def test_ask_user_question_collects_answers(db_path: Path, tmp_path: Path) -> None:
    dialog = AskUserQuestionDialogSpec(
        title="q",
        questions=(
            AskUserQuestionEntry(
                question="Pick",
                header="H",
                multi_select=False,
                options=(AskUserQuestionOption(label="A"), AskUserQuestionOption(label="B")),
            ),
        ),
    )
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path), tool_name="AskUserQuestion"),
        db_path=db_path,
        poll_interval=0.02,
    )
    thread, box = _run_blocking(lambda: transport.show_ask_user_question_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(db_path, uid, answers={"Pick": "A"})
    thread.join(timeout=3)

    assert box["result"].answers == {"Pick": "A"}


def test_ask_user_question_cancel(db_path: Path, tmp_path: Path) -> None:
    dialog = AskUserQuestionDialogSpec(
        title="q",
        questions=(
            AskUserQuestionEntry(question="Pick", header="H", multi_select=False, options=()),
        ),
    )
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path), tool_name="AskUserQuestion"),
        db_path=db_path,
        poll_interval=0.02,
    )
    thread, box = _run_blocking(lambda: transport.show_ask_user_question_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(db_path, uid, cancelled=True)
    thread.join(timeout=3)

    assert box["result"].answers is None


def test_show_dialog_free_text_returns_correction(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path)), db_path=db_path, poll_interval=0.02
    )
    dialog = DialogSpec(
        title="t", message="m", buttons=PERMISSION_BUTTONS, default_button=DialogButton.ALLOW_ONCE
    )
    thread, box = _run_blocking(lambda: transport.show_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(db_path, uid, action="deny_correct", freetext="run the tests first")
    thread.join(timeout=3)

    result = box["result"]
    assert result.button is None
    assert result.free_text is not None
    assert result.free_text.action == "deny_correct"
    assert result.free_text.text == "run the tests first"


def test_ask_user_question_allow_note_returns_free_text(db_path: Path, tmp_path: Path) -> None:
    dialog = AskUserQuestionDialogSpec(
        title="q",
        questions=(
            AskUserQuestionEntry(
                question="Pick",
                header="H",
                multi_select=False,
                options=(AskUserQuestionOption(label="A"),),
            ),
        ),
    )
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path), tool_name="AskUserQuestion"),
        db_path=db_path,
        poll_interval=0.02,
    )
    thread, box = _run_blocking(lambda: transport.show_ask_user_question_dialog(dialog))
    uid = _wait_for_request(db_path)
    _insert_response(
        db_path, uid, answers={"Pick": "A"}, action="allow_note", freetext="prefer the safe path"
    )
    thread.join(timeout=3)

    result = box["result"]
    assert result.answers == {"Pick": "A"}
    assert result.free_text is not None
    assert result.free_text.action == "allow_note"
    assert result.free_text.text == "prefer the safe path"


def test_correction_renders_deny_reason_for_ask_user_question() -> None:
    from agent_hooks.providers import provider_client
    from agent_hooks.providers.claude_code.payload import build_hook_payload
    from agent_hooks.providers.claude_code.permissions import build_correction_response

    payload = build_hook_payload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Pick", "options": []}]},
            "cwd": ".",
        }
    )
    response = build_correction_response(payload, "do X instead")
    wire = provider_client.render_response_payload(
        response, provider="claude-code", input_payload=payload
    )
    hook_output = wire["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert hook_output["permissionDecisionReason"] == "do X instead"


def test_correction_renders_decision_message_for_permission_request() -> None:
    from agent_hooks.providers import provider_client
    from agent_hooks.providers.claude_code.payload import build_hook_payload
    from agent_hooks.providers.claude_code.permissions import build_correction_response

    payload = build_hook_payload(
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": "git push"},
            "cwd": ".",
        }
    )
    response = build_correction_response(payload, "use --dry-run")
    wire = provider_client.render_response_payload(
        response, provider="claude-code", input_payload=payload
    )
    hook_output = wire["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PermissionRequest"
    assert hook_output["decision"] == {"behavior": "deny", "message": "use --dry-run"}


def test_allow_with_context_renders_for_ask_user_question() -> None:
    from agent_hooks.providers import provider_client
    from agent_hooks.providers.claude_code.payload import build_hook_payload
    from agent_hooks.providers.claude_code.permissions import build_allow_with_context_response

    payload = build_hook_payload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Pick"}]},
            "cwd": ".",
        }
    )
    response = build_allow_with_context_response(payload, {"Pick": "A"}, "also prefer Y")
    wire = provider_client.render_response_payload(
        response, provider="claude-code", input_payload=payload
    )
    hook_output = wire["hookSpecificOutput"]
    assert hook_output["permissionDecision"] == "allow"
    assert hook_output["updatedInput"]["answers"] == {"Pick": "A"}
    assert hook_output["additionalContext"] == "also prefer Y"


def test_heartbeat_advances_while_blocking(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path)), db_path=db_path, poll_interval=0.02
    )
    dialog = DialogSpec(
        title="t", message="m", buttons=PERMISSION_BUTTONS, default_button=DialogButton.ALLOW_ONCE
    )
    thread, box = _run_blocking(lambda: transport.show_dialog(dialog))
    uid = _wait_for_request(db_path)
    first = _heartbeat(db_path, uid)
    time.sleep(0.2)
    second = _heartbeat(db_path, uid)
    _insert_response(db_path, uid, selected_index=1)
    thread.join(timeout=3)

    assert second > first
    assert box["result"].button == DialogButton.ALLOW_ONCE


def test_request_timeout_expires(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path)),
        db_path=db_path,
        poll_interval=0.02,
        request_timeout=0.1,
    )
    dialog = DialogSpec(
        title="t",
        message="m",
        buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
        default_button=DialogButton.ALLOW_ONCE,
    )
    result = transport.show_dialog(dialog)

    assert result.button is None
    connection = connect(db_path)
    try:
        status = connection.execute("SELECT status FROM requests LIMIT 1").fetchone()[0]
    finally:
        connection.close()
    assert status == "expired"


def test_send_notification_inserts_row(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(cwd=str(tmp_path), event_name=HookEventName.STOP), db_path=db_path
    )
    result = transport.send_notification(
        NotificationSpec(title="Done", message="finished", subtitle="s")
    )

    assert result.status == TransportStatus.SUCCEEDED
    connection = connect(db_path)
    try:
        row = connection.execute("SELECT kind, title, message FROM notifications").fetchone()
    finally:
        connection.close()
    assert row["kind"] == "stop"
    assert row["title"] == "Done"
    assert row["message"] == "finished"


def test_send_notification_skips_permission_prompt(db_path: Path, tmp_path: Path) -> None:
    transport = SQLiteTransport(
        payload=_payload(
            cwd=str(tmp_path),
            event_name=HookEventName.NOTIFICATION,
            raw_notification_type="permission_prompt",
        ),
        db_path=db_path,
    )
    result = transport.send_notification(NotificationSpec(title="t", message="m"))

    assert result.status == TransportStatus.SKIPPED
    connection = connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_cleanup_marks_pending_cancelled(db_path: Path, tmp_path: Path) -> None:
    connection = connect(db_path)
    try:
        connection.execute(
            "INSERT INTO requests "
            "(request_uid, kind, status, queue, cwd, provider, owner_pid, created_at_ms, "
            "heartbeat_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "uid-1",
                "permission",
                "pending",
                str(tmp_path),
                str(tmp_path),
                "claude-code",
                1,
                now_ms(),
                now_ms(),
            ),
        )
    finally:
        connection.close()
    cleanup.register_pending(db_path, "uid-1")
    cleanup._mark_all_cancelled()

    connection = connect(db_path)
    try:
        status = connection.execute(
            "SELECT status FROM requests WHERE request_uid = 'uid-1'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "cancelled"


def test_build_transport_applescript_is_default(tmp_path: Path) -> None:
    from app.applescript.transport import AppleScriptTransport
    from app.transports import build_transport

    config = load_runtime_config({})
    transport = build_transport("applescript", config=config, raw_input="")
    assert isinstance(transport, AppleScriptTransport)


def _hook_input_json(tmp_path: Path) -> str:
    """Return a minimal permission-request payload as JSON."""
    return json.dumps(
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": str(tmp_path),
        }
    )


def test_build_transport_swift_ui_falls_back_without_daemon(tmp_path: Path, monkeypatch) -> None:
    from app.applescript.transport import AppleScriptTransport
    from app.transports import build_transport

    db = tmp_path / "queue.db"
    monkeypatch.setenv("AGENT_HOOK_DB_PATH", str(db))
    config = load_runtime_config({})
    raw_input = _hook_input_json(tmp_path)

    # No database file at all: fall back to AppleScript so the hook never hangs.
    assert isinstance(
        build_transport("swift-ui", config=config, raw_input=raw_input), AppleScriptTransport
    )

    # A fresh daemon heartbeat routes through the SQLite transport.
    bootstrap_database(db)
    connection = connect(db)
    try:
        connection.execute(
            "INSERT INTO daemon (id, pid, host, version, heartbeat_at_ms) VALUES (1, ?, ?, ?, ?)",
            (4321, "host", "0.3.0", now_ms()),
        )
    finally:
        connection.close()
    assert isinstance(
        build_transport("swift-ui", config=config, raw_input=raw_input), SQLiteTransport
    )


def test_build_transport_swift_ui_stale_daemon_falls_back(tmp_path: Path, monkeypatch) -> None:
    from app.applescript.transport import AppleScriptTransport
    from app.transports import build_transport

    db = tmp_path / "queue.db"
    monkeypatch.setenv("AGENT_HOOK_DB_PATH", str(db))
    config = load_runtime_config({})
    bootstrap_database(db)
    connection = connect(db)
    try:
        connection.execute(
            "INSERT INTO daemon (id, pid, host, version, heartbeat_at_ms) VALUES (1, ?, ?, ?, ?)",
            (4321, "host", "0.3.0", now_ms() - 60_000),
        )
    finally:
        connection.close()

    assert isinstance(
        build_transport("swift-ui", config=config, raw_input=_hook_input_json(tmp_path)),
        AppleScriptTransport,
    )
