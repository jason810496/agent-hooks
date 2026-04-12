"""Persist session-scoped approval rules for hook providers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_hooks.enums import HookProvider
from agent_hooks.models import HookPayload

CODEX_SUPPORT_NATIVE_ASK_AND_ALLOW_TOOL_USE = False


@dataclass(frozen=True)
class SessionRuleRecord:
    """Store one session-scoped permission rule."""

    provider: HookProvider
    session_id: str
    tool_name: str
    command: str
    created_at: str

    def as_payload(self) -> dict[str, str]:
        """Serialize the rule to JSON-friendly data."""
        return {
            "provider": self.provider.value,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "command": self.command,
            "created_at": self.created_at,
        }


def session_rules_file_path(base_directory: Path, provider: HookProvider, session_id: str) -> Path:
    """Return the file path used to store one session's rules."""
    return base_directory / provider.value / f"{session_id}.json"


def load_session_rules(
    base_directory: Path,
    provider: HookProvider,
    session_id: str,
) -> tuple[SessionRuleRecord, ...]:
    """Load stored rules for one session."""
    path = session_rules_file_path(base_directory, provider, session_id)
    if not path.exists():
        return ()

    try:
        raw_rules = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    records: list[SessionRuleRecord] = []
    for raw_rule in raw_rules if isinstance(raw_rules, list) else []:
        if not isinstance(raw_rule, dict):
            continue
        records.append(
            SessionRuleRecord(
                provider=provider,
                session_id=session_id,
                tool_name=str(raw_rule.get("tool_name", "")),
                command=str(raw_rule.get("command", "")),
                created_at=str(raw_rule.get("created_at", "")),
            )
        )
    return tuple(records)


def prune_stale_session_rules(base_directory: Path, retention_days: int) -> None:
    """Remove stale session-rule files older than the configured retention window."""
    if retention_days <= 0 or not base_directory.exists():
        return

    cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 24 * 60 * 60)
    for path in base_directory.rglob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue
    for directory in list(base_directory.iterdir()):
        if directory.is_dir():
            try:
                next(directory.iterdir())
            except StopIteration:
                try:
                    directory.rmdir()
                except OSError:
                    continue
            except OSError:
                continue


def store_session_rule(
    base_directory: Path,
    provider: HookProvider,
    session_id: str,
    tool_name: str,
    command: str,
) -> SessionRuleRecord:
    """Persist one session rule to disk."""
    record = SessionRuleRecord(
        provider=provider,
        session_id=session_id,
        tool_name=tool_name,
        command=command,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    path = session_rules_file_path(base_directory, provider, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = list(load_session_rules(base_directory, provider, session_id))
    existing.append(record)
    path.write_text(
        json.dumps([item.as_payload() for item in existing], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


def matches_session_rule(payload: HookPayload, rules: tuple[SessionRuleRecord, ...]) -> bool:
    """Check whether a Codex payload matches an existing session rule."""
    command = payload.tool_input.command
    if payload.tool_name != "Bash" or not command:
        return False
    return any(rule.tool_name == payload.tool_name and rule.command == command for rule in rules)
