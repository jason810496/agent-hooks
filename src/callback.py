#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Handle Claude Code hook callbacks via macOS notifications."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).parent.parent / "logs" / "hooks.log"
RAW_LOG_PATH = Path(__file__).parent.parent / "logs" / "hooks.raw.log"
SUPPRESS_OUTPUT_RESPONSE = {"suppressOutput": True}
SKIP_OSASCRIPT = os.environ.get("CLAUDE_HOOK_DISABLE_OSASCRIPT") == "1"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
LOG_BACKUP_COUNT = 5


@dataclass(frozen=True)
class NotificationSpec:
    title: str
    message: str
    subtitle: str = ""
    sound: str = ""


@dataclass(frozen=True)
class DialogSpec:
    """Interactive macOS dialog with buttons for user decisions."""

    title: str
    message: str
    buttons: tuple[str, ...]
    default_button: str


def compact_text(value: Any, *, limit: int = 220) -> str:
    """Collapse whitespace and trim long strings for notification display."""
    if value is None:
        return ""

    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text

    return f"{text[: limit - 1].rstrip()}…"


def first_non_empty_line(value: Any) -> str:
    """Return the first non-empty line from a string-like value."""
    if value is None:
        return ""

    for line in str(value).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return ""


def humanize(value: Any) -> str:
    """Convert snake_case values into title-case labels."""
    if value is None:
        return ""

    return str(value).replace("_", " ").strip().title()


def read_hook_input() -> tuple[str, dict[str, Any], str | None]:
    """Read and decode hook stdin without writing anything to stdout."""
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        return raw_input, {}, None

    try:
        parsed = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        return raw_input, {}, f"Invalid hook JSON: {exc}"

    if not isinstance(parsed, dict):
        return raw_input, {}, "Hook input was not a JSON object"

    return raw_input, parsed, None


def build_notification(payload: dict[str, Any]) -> NotificationSpec | None:
    """Map hook payloads to a macOS notification."""
    event_name = str(payload.get("hook_event_name", "") or "")

    if event_name == "Notification":
        notification_type = str(payload.get("notification_type", "") or "")
        title = compact_text(payload.get("title") or humanize(notification_type) or "Claude Code")
        message = compact_text(
            payload.get("message") or "Claude Code sent a notification."
        )
        return NotificationSpec(
            title=title,
            message=message,
            sound={
                "permission_prompt": "Ping",
                "idle_prompt": "Ping",
                "auth_success": "Glass",
                "elicitation_dialog": "Ping",
            }.get(notification_type, "Ping"),
        )

    if event_name == "Stop":
        return NotificationSpec(
            title="Claude finished",
            message=compact_text(
                first_non_empty_line(payload.get("last_assistant_message"))
                or "Claude finished responding."
            ),
            sound="Glass",
        )

    if event_name == "StopFailure":
        return NotificationSpec(
            title="Claude error",
            message=compact_text(
                first_non_empty_line(payload.get("error_details"))
                or first_non_empty_line(payload.get("last_assistant_message"))
                or first_non_empty_line(payload.get("error"))
                or "Claude hit an API error."
            ),
            subtitle=compact_text(payload.get("error")),
            sound="Basso",
        )

    return None


def _format_tool_detail(payload: dict[str, Any]) -> str:
    """Extract the most relevant detail from a tool input for dialog display."""
    tool_name = str(payload.get("tool_name") or "Unknown")
    tool_input = payload.get("tool_input")
    ti = tool_input if isinstance(tool_input, dict) else {}

    parts: list[str] = [f"Tool: {tool_name}"]

    if command := ti.get("command"):
        parts.append(f"Command: {compact_text(command, limit=400)}")
    if file_path := ti.get("file_path"):
        parts.append(f"File: {compact_text(file_path, limit=400)}")
    if description := ti.get("description"):
        parts.append(f"Description: {compact_text(description, limit=300)}")
    if url := ti.get("url"):
        parts.append(f"URL: {compact_text(url, limit=400)}")
    if query := ti.get("query"):
        parts.append(f"Query: {compact_text(query, limit=300)}")
    if (prompt := ti.get("prompt")) and "command" not in ti:
        parts.append(f"Prompt: {compact_text(prompt, limit=300)}")
    if pattern := ti.get("pattern"):
        parts.append(f"Pattern: {compact_text(pattern, limit=300)}")

    return "\n".join(parts)


def build_permission_dialog(payload: dict[str, Any]) -> DialogSpec:
    """Build an interactive dialog for a PermissionRequest event."""
    message = _format_tool_detail(payload)

    # Show what "Always Allow" will remember for this session
    suggestions = payload.get("permission_suggestions") or []
    if suggestions:
        rules = (suggestions[0].get("rules") or [{}])
        rule = rules[0] if rules else {}
        tool = rule.get("toolName", "")
        content = rule.get("ruleContent", "")
        if tool and content:
            message += f'\n\n"Always Allow" adds session rule: {tool}({content})'

    return DialogSpec(
        title="Claude Code — Permission Request",
        message=message,
        buttons=("Deny", "Allow Once", "Always Allow"),
        default_button="Allow Once",
    )


def run_osascript(notification: NotificationSpec) -> dict[str, Any]:
    """Send a macOS notification using osascript."""
    if SKIP_OSASCRIPT:
        return {"skipped": True}

    script = """
on run argv
    set theMessage to item 1 of argv
    set theTitle to item 2 of argv
    set theSubtitle to item 3 of argv
    set theSoundName to item 4 of argv

    if theSubtitle is "" and theSoundName is "" then
        display notification theMessage with title theTitle
    else if theSubtitle is "" then
        display notification theMessage with title theTitle sound name theSoundName
    else if theSoundName is "" then
        display notification theMessage with title theTitle subtitle theSubtitle
    else
        display notification theMessage with title theTitle subtitle theSubtitle sound name theSoundName
    end if
end run
""".strip()

    completed = subprocess.run(
        [
            "osascript",
            "-e",
            script,
            notification.message,
            notification.title,
            notification.subtitle,
            notification.sound,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_permission_dialog(dialog: DialogSpec) -> tuple[str, dict[str, Any]]:
    """Show a macOS permission dialog and return (button_clicked, osascript_result)."""
    if SKIP_OSASCRIPT:
        return "", {"skipped": True}

    script = """
on run argv
    set theMessage to item 1 of argv
    set theTitle to item 2 of argv
    set theDefault to item 3 of argv
    set buttonList to {}
    repeat with i from 4 to (count of argv)
        set end of buttonList to item i of argv
    end repeat
    display dialog theMessage with title theTitle buttons buttonList default button theDefault with icon caution
end run
""".strip()

    completed = subprocess.run(
        [
            "osascript",
            "-e",
            script,
            dialog.message,
            dialog.title,
            dialog.default_button,
            *dialog.buttons,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    result = {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }

    button = ""
    if completed.returncode == 0 and "button returned:" in completed.stdout:
        button = completed.stdout.split("button returned:", 1)[1].strip()

    return button, result


def build_permission_response(button: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a PermissionRequest hook response from the user's dialog choice."""
    if button == "Deny":
        return {
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny"},
            },
        }

    decision: dict[str, Any] = {"behavior": "allow"}

    if button == "Always Allow":
        suggestions = payload.get("permission_suggestions") or []
        if suggestions:
            # Use Claude Code's suggestions but scope to current session
            decision["updatedPermissions"] = [
                dict(s, destination="session") for s in suggestions
            ]

    return {
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": decision,
        },
    }


def _make_file_logger(
    name: str,
    path: Path,
    *,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> logging.Logger:
    """Return a rotating-file logger. Same name ⇒ same singleton logger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def append_log(entry: dict[str, Any]) -> None:
    """Write a single JSON log entry (rotated automatically)."""
    try:
        logger = _make_file_logger("hooks", LOG_PATH)
        logger.info(json.dumps(entry, ensure_ascii=True, sort_keys=True))
    except OSError:
        pass


def append_raw_input_log(*, timestamp: str, payload: dict[str, Any], raw_input: str) -> None:
    """Append the exact hook stdin payload in human-readable form (rotated automatically)."""
    try:
        hook_event_name = payload.get("hook_event_name") or "unknown"
        session_id = payload.get("session_id") or "unknown"
        cwd = payload.get("cwd") or ""

        header = (
            f"--- timestamp={timestamp} hook_event_name={hook_event_name} "
            f"session_id={session_id}"
        )
        if cwd:
            header += f" cwd={cwd}"
        header += " ---"

        logger = _make_file_logger("hooks.raw", RAW_LOG_PATH)
        if raw_input:
            logger.info("%s\n%s", header, raw_input.rstrip("\n"))
        else:
            logger.info(header)
    except OSError:
        pass


def emit_hook_response(response: dict[str, Any] | None = None) -> None:
    """Emit the structured hook response expected by Claude Code."""
    json.dump(response or SUPPRESS_OUTPUT_RESPONSE, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


def main() -> int:
    raw_input, payload, parse_error = read_hook_input()
    event_name = str(payload.get("hook_event_name", "") or "")
    timestamp = datetime.now(timezone.utc).isoformat()

    osascript_result: dict[str, Any] | None = None
    execution_error: str | None = parse_error
    hook_response: dict[str, Any] = SUPPRESS_OUTPUT_RESPONSE
    display_info: dict[str, Any] | None = None

    if event_name == "PermissionRequest" and payload and not parse_error:
        dialog = build_permission_dialog(payload)
        display_info = asdict(dialog)
        try:
            button, osascript_result = run_permission_dialog(dialog)
            if button:
                hook_response = build_permission_response(button, payload)
        except Exception as exc:  # noqa: BLE001
            execution_error = f"{type(exc).__name__}: {exc}"
    else:
        notification = build_notification(payload) if payload else None
        if notification is not None:
            display_info = asdict(notification)
            try:
                osascript_result = run_osascript(notification)
                if osascript_result.get("returncode") not in (None, 0):
                    execution_error = osascript_result.get("stderr") or "osascript exited non-zero"
            except Exception as exc:  # noqa: BLE001
                execution_error = f"{type(exc).__name__}: {exc}"

    append_raw_input_log(timestamp=timestamp, payload=payload, raw_input=raw_input)
    append_log(
        {
            "timestamp": timestamp,
            "log_path": str(LOG_PATH),
            "raw_log_path": str(RAW_LOG_PATH),
            "raw_input": raw_input,
            "hook_event_name": payload.get("hook_event_name"),
            "payload": payload,
            "display": display_info,
            "osascript": osascript_result,
            "hook_response": hook_response,
            "error": execution_error,
        }
    )
    emit_hook_response(hook_response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
