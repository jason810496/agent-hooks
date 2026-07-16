"""Proxy Codex app-server traffic and route user-input requests to SwiftUI.

Codex exposes ``request_user_input`` as a server-initiated JSON-RPC request. Hook
callbacks cannot answer it, so the native UI integration runs as a transparent
stdio proxy in front of ``codex app-server`` and handles only that request type.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, TextIO, TypedDict

from agent_hooks.models.schemas.json_types import JsonObject, JsonValue
from app.swift_ui.cleanup import install_handlers, register_pending, resolve_pending
from app.swift_ui.config import SwiftUiConfig, load_swift_ui_config
from app.swift_ui.db import connect, daemon_supports_codex_user_input, now_ms
from app.swift_ui.queue import resolve_queue

REQUEST_USER_INPUT_METHOD: Final = "item/tool/requestUserInput"
CODEX_USER_INPUT_KIND: Final = "codex_user_input"


class CodexUserInputAnswer(TypedDict):
    """Represent one Codex answer value on the JSON-RPC wire."""

    answers: list[str]


class CodexUserInputResult(TypedDict):
    """Represent the result returned for a Codex user-input request."""

    answers: dict[str, CodexUserInputAnswer]


class CodexUserInputJsonRpcResponse(TypedDict):
    """Represent a JSON-RPC response to a Codex user-input request."""

    id: str | int
    result: CodexUserInputResult


@dataclass(frozen=True, slots=True)
class CodexUserInputOption:
    """Store one normalized Codex question option."""

    label: str
    description: str


@dataclass(frozen=True, slots=True)
class CodexUserInputQuestion:
    """Store one normalized Codex question."""

    question_id: str
    header: str
    question: str
    is_other: bool
    is_secret: bool
    options: tuple[CodexUserInputOption, ...]


@dataclass(frozen=True, slots=True)
class CodexUserInputRequest:
    """Store a validated Codex ``request_user_input`` request."""

    thread_id: str
    turn_id: str
    item_id: str
    questions: tuple[CodexUserInputQuestion, ...]
    auto_resolution_ms: int | None

    @classmethod
    def parse(cls, params: JsonObject) -> CodexUserInputRequest | None:
        """Parse a JSON-RPC params object into a normalized request.

        :param params: Untrusted ``item/tool/requestUserInput`` parameters.
        :return: Parsed request, or ``None`` when required fields are invalid.
        """
        raw_questions = params.get("questions")
        if not isinstance(raw_questions, list):
            return None

        questions: list[CodexUserInputQuestion] = []
        question_ids: set[str] = set()
        for raw_question in raw_questions:
            question = _parse_question(raw_question)
            if question is None or question.question_id in question_ids:
                return None
            questions.append(question)
            question_ids.add(question.question_id)
        if not questions:
            return None

        auto_resolution = params.get("autoResolutionMs")
        auto_resolution_ms = (
            auto_resolution
            if isinstance(auto_resolution, int)
            and not isinstance(auto_resolution, bool)
            and auto_resolution > 0
            else None
        )
        return cls(
            thread_id=_text(params.get("threadId")),
            turn_id=_text(params.get("turnId")),
            item_id=_text(params.get("itemId")),
            questions=tuple(questions),
            auto_resolution_ms=auto_resolution_ms,
        )


class CodexUserInputBridge:
    """Round-trip one Codex question request through the SwiftUI SQLite queue."""

    def __init__(self, config: SwiftUiConfig, *, cwd: str | Path | None = None) -> None:
        """Initialize the bridge.

        :param config: SwiftUI database, polling, and timeout settings.
        :param cwd: Workspace used to group the question card in SwiftUI.
        """
        self._config = config
        self._cwd = str(Path.cwd() if cwd is None else cwd)

    def prompt(self, request: CodexUserInputRequest) -> CodexUserInputResult:
        """Queue a request, wait for SwiftUI, and return Codex-shaped answers.

        :param request: Validated Codex question request.
        :return: Answers keyed by stable Codex question id. Cancellation and expiry
            return an empty answer map so the app-server request is always resolved.
        """
        request_uid = secrets.token_hex(16)
        connection = connect(self._config.db_path)
        try:
            self._insert_request(connection, request_uid, request)
            register_pending(self._config.db_path, request_uid)
            return self._await_response(connection, request_uid, request)
        finally:
            resolve_pending(request_uid)
            connection.close()

    def _insert_request(
        self,
        connection: sqlite3.Connection,
        request_uid: str,
        request: CodexUserInputRequest,
    ) -> None:
        """Insert a Codex question request into the shared queue."""
        created = now_ms()
        timeout_seconds = self._effective_timeout(request)
        expires_at = created + int(timeout_seconds * 1000) if timeout_seconds > 0 else None
        options = {
            "answer_format": "codex",
            "questions": [
                {
                    "id": question.question_id,
                    "question": question.question,
                    "header": question.header,
                    "multi_select": False,
                    "is_other": question.is_other or not question.options,
                    "is_secret": question.is_secret,
                    "options": [
                        {"label": option.label, "description": option.description}
                        for option in question.options
                    ],
                }
                for question in request.questions
            ],
        }
        tool_input = {
            "threadId": request.thread_id,
            "turnId": request.turn_id,
            "itemId": request.item_id,
        }
        connection.execute(
            "INSERT INTO requests ("
            " request_uid, kind, status, queue, cwd, session_id, provider, tool_name,"
            " tool_use_id, title, summary, tool_input_json, options_json, suggestions_json,"
            " transcript_path, owner_pid, owner_host, created_at_ms, heartbeat_at_ms, expires_at_ms"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_uid,
                CODEX_USER_INPUT_KIND,
                "pending",
                resolve_queue(self._cwd),
                self._cwd,
                request.thread_id,
                "codex",
                "request_user_input",
                request.item_id,
                "Codex — Question",
                "",
                json.dumps(tool_input),
                json.dumps(options),
                "[]",
                "",
                os.getpid(),
                socket.gethostname(),
                created,
                created,
                expires_at,
            ),
        )

    def _await_response(
        self,
        connection: sqlite3.Connection,
        request_uid: str,
        request: CodexUserInputRequest,
    ) -> CodexUserInputResult:
        """Poll until SwiftUI answers or the configured deadline passes."""
        timeout_seconds = self._effective_timeout(request)
        deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
        while True:
            row = connection.execute(
                "SELECT answers_json, cancelled FROM responses "
                "WHERE request_uid = ? ORDER BY id LIMIT 1",
                (request_uid,),
            ).fetchone()
            if row is not None:
                self._set_status(connection, request_uid, "answered")
                if row["cancelled"]:
                    return {"answers": {}}
                return _parse_answers(row["answers_json"], request.questions)

            connection.execute(
                "UPDATE requests SET heartbeat_at_ms = ? WHERE request_uid = ?",
                (now_ms(), request_uid),
            )
            if deadline is not None and time.monotonic() >= deadline:
                self._set_status(connection, request_uid, "expired")
                return {"answers": {}}
            time.sleep(self._config.poll_interval_seconds)

    def _effective_timeout(self, request: CodexUserInputRequest) -> float:
        """Return the earliest configured or Codex auto-resolution timeout."""
        candidates = [
            timeout
            for timeout in (
                self._config.request_timeout_seconds,
                (request.auto_resolution_ms or 0) / 1000,
            )
            if timeout > 0
        ]
        return min(candidates) if candidates else 0.0

    @staticmethod
    def _set_status(connection: sqlite3.Connection, request_uid: str, status: str) -> None:
        """Update the request lifecycle status."""
        connection.execute(
            "UPDATE requests SET status = ? WHERE request_uid = ?",
            (status, request_uid),
        )


class CodexAppServerProxy:
    """Run a Codex app-server child and intercept its user-input requests."""

    def __init__(
        self,
        *,
        codex_binary: str = "codex",
        codex_args: tuple[str, ...] = (),
        swift_config: SwiftUiConfig | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        """Initialize the transparent stdio proxy.

        :param codex_binary: Codex executable name or path.
        :param codex_args: Additional arguments passed after ``codex app-server``.
        :param swift_config: Optional SwiftUI config override.
        :param cwd: Working directory used for the child and queue grouping.
        """
        self._codex_binary = codex_binary
        self._codex_args = codex_args
        self._config = swift_config or load_swift_ui_config()
        self._cwd = Path.cwd() if cwd is None else Path(cwd)
        self._write_lock = threading.Lock()

    def run(
        self,
        *,
        stdin: TextIO = sys.stdin,
        stdout: TextIO = sys.stdout,
        stderr: TextIO = sys.stderr,
    ) -> int:
        """Proxy JSON-RPC until the Codex app-server child exits.

        :param stdin: JSON-RPC input supplied by the app-server client.
        :param stdout: JSON-RPC output returned to the client.
        :param stderr: Diagnostic output stream.
        :return: Child process exit code, or ``127`` when Codex is unavailable.
        """
        try:
            process = subprocess.Popen(
                [self._codex_binary, "app-server", *self._codex_args],
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            stderr.write(f"agent-hooks: Codex executable not found: {self._codex_binary}\n")
            stderr.flush()
            return 127

        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            return 1

        client_pump = threading.Thread(
            target=self._pump_client_input,
            args=(stdin, process.stdin),
            daemon=True,
        )
        error_pump = threading.Thread(
            target=self._pump_stream,
            args=(process.stderr, stderr),
            daemon=True,
        )
        client_pump.start()
        error_pump.start()

        bridge = CodexUserInputBridge(self._config, cwd=self._cwd)
        for line in process.stdout:
            message = _decode_object(line)
            intercepted = _user_input_request(message)
            if intercepted is not None and daemon_supports_codex_user_input(self._config.db_path):
                request_id, request = intercepted
                result = bridge.prompt(request)
                response = CodexUserInputJsonRpcResponse(id=request_id, result=result)
                self._write_json(process.stdin, response)
                continue
            stdout.write(line)
            stdout.flush()
        return process.wait()

    def _pump_client_input(self, source: TextIO, destination: IO[str]) -> None:
        """Forward client requests into the child without racing proxy responses."""
        for line in source:
            with self._write_lock:
                try:
                    destination.write(line)
                    destination.flush()
                except BrokenPipeError:
                    return

    @staticmethod
    def _pump_stream(source: IO[str], destination: TextIO) -> None:
        """Forward a diagnostic stream line by line."""
        for line in source:
            destination.write(line)
            destination.flush()

    def _write_json(
        self,
        destination: IO[str],
        payload: CodexUserInputJsonRpcResponse,
    ) -> None:
        """Write one compact JSON-RPC message into the child."""
        serialized = json.dumps(payload, separators=(",", ":"))
        with self._write_lock:
            destination.write(serialized + "\n")
            destination.flush()


def run_codex_app_server(
    *,
    codex_binary: str = "codex",
    codex_args: tuple[str, ...] = (),
) -> int:
    """Run the SwiftUI-aware Codex app-server proxy.

    :param codex_binary: Codex executable name or path.
    :param codex_args: Additional ``codex app-server`` arguments.
    :return: Proxy exit code.
    """
    install_handlers()
    return CodexAppServerProxy(
        codex_binary=codex_binary,
        codex_args=codex_args,
    ).run()


def _parse_question(value: JsonValue) -> CodexUserInputQuestion | None:
    """Normalize one untrusted Codex question value."""
    if not isinstance(value, dict):
        return None
    question_id = _text(value.get("id"))
    if not question_id:
        return None
    raw_options = value.get("options")
    if raw_options is not None and not isinstance(raw_options, list):
        return None
    options: list[CodexUserInputOption] = []
    for raw_option in raw_options or []:
        if not isinstance(raw_option, dict):
            return None
        label = _text(raw_option.get("label"))
        if not label:
            return None
        options.append(
            CodexUserInputOption(
                label=label,
                description=_text(raw_option.get("description")),
            )
        )
    return CodexUserInputQuestion(
        question_id=question_id,
        header=_text(value.get("header")),
        question=_text(value.get("question")),
        is_other=value.get("isOther") is True,
        is_secret=value.get("isSecret") is True,
        options=tuple(options),
    )


def _parse_answers(
    answers_json: object,
    questions: tuple[CodexUserInputQuestion, ...],
) -> CodexUserInputResult:
    """Validate SwiftUI answer JSON against the Codex response schema."""
    if not isinstance(answers_json, str):
        return {"answers": {}}
    try:
        raw_answers = json.loads(answers_json)
    except json.JSONDecodeError:
        return {"answers": {}}
    if not isinstance(raw_answers, dict):
        return {"answers": {}}

    answers: dict[str, CodexUserInputAnswer] = {}
    for question in questions:
        raw_answer = raw_answers.get(question.question_id)
        if not isinstance(raw_answer, dict):
            continue
        values = raw_answer.get("answers")
        if isinstance(values, list):
            answer_values = [value for value in values if isinstance(value, str)]
            if len(answer_values) == len(values):
                answers[question.question_id] = {"answers": answer_values}
    return {"answers": answers}


def _decode_object(line: str) -> JsonObject | None:
    """Decode one JSON line when it contains an object."""
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _user_input_request(
    message: JsonObject | None,
) -> tuple[str | int, CodexUserInputRequest] | None:
    """Return a normalized request when a message is interceptable."""
    if message is None or message.get("method") != REQUEST_USER_INPUT_METHOD:
        return None
    request_id = message.get("id")
    if isinstance(request_id, bool) or not isinstance(request_id, str | int):
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    request = CodexUserInputRequest.parse(params)
    return (request_id, request) if request is not None else None


def _text(value: JsonValue | object) -> str:
    """Return a string JSON value or an empty string."""
    return value if isinstance(value, str) else ""


__all__ = [
    "CODEX_USER_INPUT_KIND",
    "REQUEST_USER_INPUT_METHOD",
    "CodexAppServerProxy",
    "CodexUserInputBridge",
    "CodexUserInputRequest",
    "run_codex_app_server",
]
