"""Queue a deterministic Codex multi-question card for manual SwiftUI testing."""

from __future__ import annotations

import json
import sys

from app.codex_app_server import CodexUserInputBridge, CodexUserInputRequest
from app.swift_ui.cleanup import install_handlers
from app.swift_ui.config import load_swift_ui_config
from app.swift_ui.db import daemon_is_alive, daemon_supports_codex_user_input


def main() -> int:
    """Show a two-question card and print the Codex-shaped response.

    :return: Zero after an answer or cancellation, one when the Swift app is not running.
    """
    config = load_swift_ui_config()
    if not daemon_is_alive(config.db_path):
        print(
            "Agent Hooks UI is not running (no fresh daemon heartbeat).",
            file=sys.stderr,
        )
        return 1
    if not daemon_supports_codex_user_input(config.db_path):
        print(
            "Agent Hooks UI is running, but it is too old for Codex questions. "
            "Install and relaunch version 0.3.1 or newer.",
            file=sys.stderr,
        )
        return 1

    request = CodexUserInputRequest.parse(
        {
            "threadId": "manual-thread",
            "turnId": "manual-turn",
            "itemId": "manual-request-user-input",
            "questions": [
                {
                    "id": "framework",
                    "header": "Framework",
                    "question": "Which macOS UI framework should this test use?",
                    "isOther": False,
                    "isSecret": False,
                    "options": [
                        {"label": "SwiftUI", "description": "Modern declarative UI"},
                        {"label": "AppKit", "description": "Traditional macOS UI"},
                    ],
                },
                {
                    "id": "storage",
                    "header": "Storage",
                    "question": "How should answers be stored?",
                    "isOther": True,
                    "isSecret": False,
                    "options": [
                        {"label": "SQLite", "description": "Use the shared queue database"},
                        {"label": "JSON", "description": "Use a standalone file"},
                    ],
                },
            ],
            "autoResolutionMs": None,
        }
    )
    if request is None:
        print("The built-in manual request is invalid.", file=sys.stderr)
        return 1

    install_handlers()
    result = CodexUserInputBridge(config).prompt(request)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
