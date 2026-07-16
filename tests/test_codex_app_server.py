from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from app.cli import build_argument_parser
from app.codex_app_server import CodexUserInputBridge, CodexUserInputRequest
from app.swift_ui.config import SwiftUiConfig
from app.swift_ui.db import (
    DAEMON_MAX_AGE_MS,
    bootstrap_database,
    connect,
    daemon_supports_codex_user_input,
    now_ms,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a bootstrapped SwiftUI database."""
    return bootstrap_database(tmp_path / "queue.db")


def _request() -> CodexUserInputRequest:
    """Return a representative two-question Codex request."""
    request = CodexUserInputRequest.parse(
        {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "itemId": "item-1",
            "questions": [
                {
                    "id": "framework",
                    "header": "Framework",
                    "question": "Which framework?",
                    "isOther": False,
                    "isSecret": False,
                    "options": [
                        {"label": "SwiftUI", "description": "Native UI"},
                        {"label": "AppKit", "description": "Classic UI"},
                    ],
                },
                {
                    "id": "storage",
                    "header": "Storage",
                    "question": "Which store?",
                    "isOther": True,
                    "isSecret": False,
                    "options": [
                        {"label": "SQLite", "description": "Local database"},
                        {"label": "Files", "description": "Plain JSON"},
                    ],
                },
            ],
            "autoResolutionMs": None,
        }
    )
    assert request is not None
    return request


def _wait_for_request(db_path: Path, timeout: float = 3.0) -> sqlite3.Row:
    """Wait for the bridge to insert a pending request row."""
    connection = connect(db_path)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = connection.execute(
                "SELECT request_uid, kind, provider, options_json FROM requests "
                "WHERE status = 'pending' LIMIT 1"
            ).fetchone()
            if row is not None:
                return row
            time.sleep(0.01)
    finally:
        connection.close()
    raise AssertionError("Codex user-input request was not queued")


class TestCodexUserInputRequest:
    def test_parses_multiple_questions_with_stable_ids(self) -> None:
        request = _request()

        assert [question.question_id for question in request.questions] == [
            "framework",
            "storage",
        ]
        assert request.questions[1].is_other is True
        assert request.questions[0].options[0].description == "Native UI"

    def test_rejects_duplicate_question_ids(self) -> None:
        request = CodexUserInputRequest.parse(
            {
                "questions": [
                    {"id": "same", "options": []},
                    {"id": "same", "options": []},
                ]
            }
        )

        assert request is None


class TestSwiftUiCodexCapability:
    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            pytest.param("0.3.0", False, id="older-ui"),
            pytest.param("0.3.1", True, id="minimum-ui"),
            pytest.param("0.4.0", True, id="newer-ui"),
            pytest.param("0.3.1-dev", True, id="prerelease-metadata"),
            pytest.param("not-a-version", False, id="invalid-version"),
        ],
    )
    def test_requires_compatible_live_ui(
        self,
        db_path: Path,
        version: str,
        expected: bool,
    ) -> None:
        connection = connect(db_path)
        try:
            connection.execute(
                "INSERT INTO daemon (id, pid, host, version, heartbeat_at_ms) "
                "VALUES (1, ?, ?, ?, ?)",
                (123, "localhost", version, 50_000),
            )
        finally:
            connection.close()

        assert daemon_supports_codex_user_input(db_path, current_ms=50_000) is expected

    def test_rejects_stale_compatible_ui(self, db_path: Path) -> None:
        connection = connect(db_path)
        try:
            connection.execute(
                "INSERT INTO daemon (id, pid, host, version, heartbeat_at_ms) "
                "VALUES (1, ?, ?, ?, ?)",
                (123, "localhost", "0.3.1", 50_000),
            )
        finally:
            connection.close()

        assert not daemon_supports_codex_user_input(
            db_path,
            current_ms=50_000 + DAEMON_MAX_AGE_MS + 1,
        )


class TestCodexUserInputBridge:
    def test_round_trips_multiple_answers_in_codex_shape(self, db_path: Path) -> None:
        bridge = CodexUserInputBridge(
            SwiftUiConfig(db_path=db_path, poll_interval_seconds=0.02),
            cwd="/tmp/project",
        )
        box: dict[str, object] = {}

        def run_prompt() -> None:
            box["result"] = bridge.prompt(_request())

        thread = threading.Thread(target=run_prompt)
        thread.start()
        row = _wait_for_request(db_path)

        options = json.loads(row["options_json"])
        assert row["kind"] == "codex_user_input"
        assert row["provider"] == "codex"
        assert [question["id"] for question in options["questions"]] == [
            "framework",
            "storage",
        ]
        assert options["questions"][1]["is_other"] is True

        connection = connect(db_path)
        try:
            connection.execute(
                "INSERT INTO responses "
                "(request_uid, selected_index, answers_json, cancelled, responder, created_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row["request_uid"],
                    None,
                    json.dumps(
                        {
                            "framework": {"answers": ["SwiftUI"]},
                            "storage": {"answers": ["A custom store"]},
                        }
                    ),
                    0,
                    "swift_ui",
                    now_ms(),
                ),
            )
        finally:
            connection.close()
        thread.join(timeout=3)

        assert not thread.is_alive()
        assert box["result"] == {
            "answers": {
                "framework": {"answers": ["SwiftUI"]},
                "storage": {"answers": ["A custom store"]},
            }
        }

    def test_cancel_returns_empty_answer_map(self, db_path: Path) -> None:
        bridge = CodexUserInputBridge(
            SwiftUiConfig(db_path=db_path, poll_interval_seconds=0.02),
            cwd="/tmp/project",
        )
        box: dict[str, object] = {}
        thread = threading.Thread(target=lambda: box.update(result=bridge.prompt(_request())))
        thread.start()
        row = _wait_for_request(db_path)

        connection = connect(db_path)
        try:
            connection.execute(
                "INSERT INTO responses "
                "(request_uid, selected_index, answers_json, cancelled, responder, created_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (row["request_uid"], None, None, 1, "swift_ui", now_ms()),
            )
        finally:
            connection.close()
        thread.join(timeout=3)

        assert box["result"] == {"answers": {}}


class TestCodexAppServerCli:
    def test_accepts_codex_binary_and_passthrough_args(self) -> None:
        args = build_argument_parser().parse_args(
            ["codex-app-server", "--codex-bin", "/opt/codex", "--", "--listen", "stdio://"]
        )

        assert args.command == "codex-app-server"
        assert args.codex_bin == "/opt/codex"
        assert args.codex_args == ["--", "--listen", "stdio://"]
