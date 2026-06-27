"""SQLite-backed DisplayTransport that defers hook decisions to the Swift app.

This transport is selected (opt-in) instead of AppleScript when ``--ui swift-ui`` is
passed and the Swift daemon is running. Each blocking display call writes one
``requests`` row and then polls the ``responses`` table until the Swift app answers,
the request expires, or the process is interrupted. It implements the same
``DisplayTransport`` protocol as ``AppleScriptTransport`` so the handler logic,
permission decisions, and presentation are reused unchanged.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_hooks.enums import (
    AppleScriptInvocation,
    DialogButton,
    HookEventName,
    TransportStatus,
)
from agent_hooks.models.schemas.display import (
    AppleScriptResult,
    AskUserQuestionDialogResult,
    AskUserQuestionDialogSpec,
    DialogResult,
    DialogSpec,
    FreeText,
    NotificationSpec,
    PermissionChoiceDialogResult,
    PermissionChoiceDialogSpec,
)
from agent_hooks.models.schemas.hooks import HookPayload
from app.swift_ui.cleanup import register_pending, resolve_pending
from app.swift_ui.db import connect, now_ms
from app.swift_ui.queue import resolve_queue

DEFAULT_POLL_INTERVAL_SECONDS = 0.2
MIN_POLL_INTERVAL_SECONDS = 0.05
RESPONDER_SWIFT = "swift_ui"
PERMISSION_PROMPT_NOTIFICATION = "permission_prompt"


@dataclass(frozen=True)
class _Outcome:
    """Internal result of one request/response round trip."""

    selected_index: int | None
    answers: dict[str, str] | None
    cancelled: bool
    expired: bool
    free_text: FreeText | None = None


class SQLiteTransport:
    """Write hook requests to SQLite and block until the Swift app responds."""

    def __init__(
        self,
        *,
        payload: HookPayload,
        db_path: str | Path,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        request_timeout: float = 0.0,
    ) -> None:
        """Initialize the transport for one hook invocation.

        :param payload: Normalized payload for the event being handled.
        :type payload: HookPayload
        :param db_path: Path to the shared SQLite database.
        :type db_path: str | Path
        :param poll_interval: Seconds between response polls.
        :type poll_interval: float
        :param request_timeout: Seconds to block before expiring the request; ``0``
            (or negative) blocks indefinitely.
        :type request_timeout: float
        """
        self._payload = payload
        self._db_path = Path(db_path)
        self._poll_interval = max(MIN_POLL_INTERVAL_SECONDS, poll_interval)
        self._request_timeout = max(0.0, request_timeout)
        self._pid = os.getpid()
        self._host = socket.gethostname()
        self._queue = resolve_queue(payload.cwd)

    def send_notification(self, notification: NotificationSpec) -> AppleScriptResult:
        """Append a notification to the buffer, skipping permission-prompt duplicates.

        :param notification: Notification specification.
        :type notification: NotificationSpec
        :return: Transport result.
        """
        invocation = AppleScriptInvocation.NOTIFICATION
        if self._payload.raw_notification_type == PERMISSION_PROMPT_NOTIFICATION:
            # The blocking permission card already represents this event.
            return AppleScriptResult(
                status=TransportStatus.SKIPPED,
                invocation=invocation,
                skipped_reason="permission-prompt-deduped",
            )
        try:
            connection = connect(self._db_path)
            try:
                connection.execute(
                    "INSERT INTO notifications "
                    "(queue, session_id, kind, title, subtitle, message, created_at_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        self._queue,
                        self._payload.session_id,
                        self._notification_kind(),
                        notification.title,
                        notification.subtitle,
                        notification.message,
                        now_ms(),
                    ),
                )
            finally:
                connection.close()
        except sqlite3.Error as exc:
            return AppleScriptResult(
                status=TransportStatus.FAILED,
                invocation=invocation,
                stderr=f"{type(exc).__name__}: {exc}",
            )
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED, invocation=invocation, returncode=0
        )

    def show_dialog(self, dialog: DialogSpec) -> DialogResult:
        """Queue a basic permission dialog and map the chosen button.

        :param dialog: Dialog specification.
        :type dialog: DialogSpec
        :return: Dialog result with button selection.
        """
        invocation = AppleScriptInvocation.DIALOG
        options = {
            "default_button": dialog.default_button.value,
            "buttons": [button.value for button in dialog.buttons],
        }
        outcome = self._await_response(
            kind="permission",
            title=dialog.title,
            summary=dialog.message,
            options=options,
        )
        if outcome.free_text is not None:
            return DialogResult(
                button=None, transport=self._result(invocation), free_text=outcome.free_text
            )
        if outcome.cancelled or outcome.expired:
            return DialogResult(button=None, transport=self._result(invocation))
        button = self._resolve_button(dialog.buttons, outcome.selected_index)
        return DialogResult(button=button, transport=self._result(invocation))

    def show_permission_choice_dialog(
        self, dialog: PermissionChoiceDialogSpec
    ) -> PermissionChoiceDialogResult:
        """Queue the permission picker and map the chosen scope.

        :param dialog: Permission picker specification.
        :type dialog: PermissionChoiceDialogSpec
        :return: Selected choice and transport metadata.
        """
        invocation = AppleScriptInvocation.PERMISSION_CHOICE
        if not dialog.choices:
            return PermissionChoiceDialogResult(
                choice=None,
                transport=self._result(
                    invocation, status=TransportStatus.SKIPPED, skipped_reason="no-choices"
                ),
            )
        options = {
            "default_index": dialog.default_index,
            "choices": [
                {
                    "label": choice.label,
                    "button": choice.button.value,
                    "suggestion_index": choice.suggestion_index,
                }
                for choice in dialog.choices
            ],
        }
        outcome = self._await_response(
            kind="permission_choice",
            title=dialog.title,
            summary=dialog.message,
            options=options,
        )
        if outcome.free_text is not None:
            return PermissionChoiceDialogResult(
                choice=None, transport=self._result(invocation), free_text=outcome.free_text
            )
        if outcome.cancelled or outcome.expired:
            return PermissionChoiceDialogResult(choice=None, transport=self._result(invocation))
        choice = self._resolve_choice(dialog, outcome.selected_index)
        return PermissionChoiceDialogResult(choice=choice, transport=self._result(invocation))

    def show_ask_user_question_dialog(
        self, dialog: AskUserQuestionDialogSpec
    ) -> AskUserQuestionDialogResult:
        """Queue the AskUserQuestion picker and return the collected answers.

        :param dialog: AskUserQuestion dialog specification.
        :type dialog: AskUserQuestionDialogSpec
        :return: Collected answers and transport metadata.
        """
        invocation = AppleScriptInvocation.ASK_USER_QUESTION
        options = {
            "questions": [
                {
                    "question": entry.question,
                    "header": entry.header,
                    "multi_select": entry.multi_select,
                    "options": [
                        {"label": option.label, "description": option.description}
                        for option in entry.options
                    ],
                }
                for entry in dialog.questions
            ],
        }
        outcome = self._await_response(
            kind="ask_user_question",
            title=dialog.title,
            summary="",
            options=options,
        )
        if outcome.free_text is not None:
            return AskUserQuestionDialogResult(
                answers=outcome.answers,
                transport=self._result(invocation),
                free_text=outcome.free_text,
            )
        if outcome.cancelled or outcome.expired or outcome.answers is None:
            return AskUserQuestionDialogResult(answers=None, transport=self._result(invocation))
        return AskUserQuestionDialogResult(
            answers=outcome.answers, transport=self._result(invocation)
        )

    def _await_response(
        self,
        *,
        kind: str,
        title: str,
        summary: str,
        options: Mapping[str, object],
    ) -> _Outcome:
        """Insert a request row and block until a response arrives or it expires.

        :param kind: Request kind discriminator stored on the row.
        :type kind: str
        :param title: Card title.
        :type title: str
        :param summary: Formatted detail shown on the card.
        :type summary: str
        :param options: Renderable options serialized to ``options_json``.
        :type options: dict[str, object]
        :return: The parsed outcome of the round trip.
        """
        request_uid = os.urandom(16).hex()
        connection = connect(self._db_path)
        try:
            self._insert_request(connection, request_uid, kind, title, summary, options)
            register_pending(self._db_path, request_uid)
            initial_ppid = os.getppid()
            deadline = (
                time.monotonic() + self._request_timeout if self._request_timeout > 0 else None
            )
            while True:
                row = connection.execute(
                    "SELECT selected_index, answers_json, cancelled, action, freetext "
                    "FROM responses WHERE request_uid = ? ORDER BY id LIMIT 1",
                    (request_uid,),
                ).fetchone()
                if row is not None:
                    self._set_status(connection, request_uid, "answered")
                    resolve_pending(request_uid)
                    return self._parse_response_row(row)
                if os.getppid() != initial_ppid:
                    # The spawning session went away (reparented to launchd / a subreaper)
                    # without sending a catchable signal. Stop waiting and clear the card.
                    self._set_status(connection, request_uid, "cancelled")
                    resolve_pending(request_uid)
                    return _Outcome(None, None, cancelled=True, expired=False)
                connection.execute(
                    "UPDATE requests SET heartbeat_at_ms = ? WHERE request_uid = ?",
                    (now_ms(), request_uid),
                )
                if deadline is not None and time.monotonic() >= deadline:
                    self._set_status(connection, request_uid, "expired")
                    resolve_pending(request_uid)
                    return _Outcome(None, None, cancelled=False, expired=True)
                time.sleep(self._poll_interval)
        finally:
            connection.close()

    @staticmethod
    def _parse_response_row(row: sqlite3.Row) -> _Outcome:
        """Map one ``responses`` row to an internal outcome.

        :param row: Response row with ``selected_index``, ``answers_json``, ``cancelled``,
            ``action``, and ``freetext``.
        :type row: sqlite3.Row
        :return: Parsed outcome.
        """
        if row["cancelled"]:
            return _Outcome(None, None, cancelled=True, expired=False)
        answers_json = row["answers_json"]
        answers = json.loads(answers_json) if answers_json else None
        free_text: FreeText | None = None
        action = row["action"]
        if action:
            free_text = FreeText(action=action, text=row["freetext"] or "")
        return _Outcome(
            row["selected_index"], answers, cancelled=False, expired=False, free_text=free_text
        )

    def _insert_request(
        self,
        connection: sqlite3.Connection,
        request_uid: str,
        kind: str,
        title: str,
        summary: str,
        options: Mapping[str, object],
    ) -> None:
        """Insert one pending request row stamped with this process's identity."""
        created = now_ms()
        expires_at = (
            created + int(self._request_timeout * 1000) if self._request_timeout > 0 else None
        )
        suggestions = self._payload.raw.get("permission_suggestions") or []
        connection.execute(
            "INSERT INTO requests ("
            " request_uid, kind, status, queue, cwd, session_id, provider, tool_name,"
            " tool_use_id, title, summary, tool_input_json, options_json, suggestions_json,"
            " transcript_path, owner_pid, owner_host, created_at_ms, heartbeat_at_ms, expires_at_ms"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_uid,
                kind,
                "pending",
                self._queue,
                self._payload.cwd,
                self._payload.session_id,
                self._payload.provider.value,
                self._payload.tool_name,
                self._payload.tool_use_id,
                title,
                summary,
                json.dumps(self._payload.tool_input.raw),
                json.dumps(options),
                json.dumps(suggestions),
                self._payload.transcript_path,
                self._pid,
                self._host,
                created,
                created,
                expires_at,
            ),
        )

    @staticmethod
    def _set_status(connection: sqlite3.Connection, request_uid: str, status: str) -> None:
        """Update the lifecycle status of one request row."""
        connection.execute(
            "UPDATE requests SET status = ? WHERE request_uid = ?",
            (status, request_uid),
        )

    @staticmethod
    def _resolve_button(
        buttons: tuple[DialogButton, ...], index: int | None
    ) -> DialogButton | None:
        """Map a selected option index back to a dialog button."""
        if index is None or not 0 <= index < len(buttons):
            return None
        return buttons[index]

    @staticmethod
    def _resolve_choice(dialog: PermissionChoiceDialogSpec, index: int | None):
        """Map a selected option index back to a permission choice."""
        if index is None or not 0 <= index < len(dialog.choices):
            return None
        return dialog.choices[index]

    def _notification_kind(self) -> str:
        """Return the notification buffer kind for the current event."""
        event = self._payload.event_name
        if event == HookEventName.STOP:
            return "stop"
        if event == HookEventName.STOP_FAILURE:
            return "stop_failure"
        return "notification"

    @staticmethod
    def _result(
        invocation: AppleScriptInvocation,
        *,
        status: TransportStatus = TransportStatus.SUCCEEDED,
        stderr: str = "",
        skipped_reason: str = "",
    ) -> AppleScriptResult:
        """Build a transport result mirroring the AppleScript transport's shape."""
        return AppleScriptResult(
            status=status,
            invocation=invocation,
            returncode=0,
            stdout="",
            stderr=stderr,
            skipped_reason=skipped_reason,
        )


__all__ = ["SQLiteTransport"]
