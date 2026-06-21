"""Codex-specific middleware."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Mapping
from pathlib import Path

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.middleware import HookMiddlewareContext, NextMiddleware
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import HookResponse

CODEX_EXECPOLICY_MODEL_ENV_VAR = "AGENT_HOOK_CODEX_EXECPOLICY_MODEL"
CODEX_EXECPOLICY_RULES_ENV_VAR = "AGENT_HOOK_CODEX_EXECPOLICY_RULES"

DEFAULT_CODEX_EXECPOLICY_MODEL = "5.4-mini"
DEFAULT_CODEX_EXECPOLICY_RULES = Path("~/.codex/rules/default.rules")


def codex_execpolicy_middleware(
    context: HookMiddlewareContext,
    call_next: NextMiddleware,
) -> HookProcessingResult:
    """Auto-allow Codex Bash commands already approved by Codex execpolicy."""
    if should_auto_allow_codex_permission_request(context.payload):
        return HookProcessingResult(
            display=None,
            transport_result=None,
            response=HookResponse(),
        )
    return call_next(context)


def should_auto_allow_codex_permission_request(
    payload: HookPayload,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return whether Codex policy allows the requested command."""
    if payload.provider != HookProvider.CODEX:
        return False
    if payload.event_name != HookEventName.PERMISSION_REQUEST:
        return False
    if payload.tool_name != "Bash":
        return False

    command = payload.tool_input.command.strip()
    if not command:
        return False

    try:
        command_tokens = shlex.split(command)
    except ValueError:
        return False

    if not command_tokens:
        return False

    return (
        run_codex_execpolicy_check(
            command_tokens,
            cwd=payload.cwd or None,
            env=env,
        )
        == "allow"
    )


def run_codex_execpolicy_check(
    command_tokens: list[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the top-level Codex execpolicy decision for one command."""
    environment = dict(os.environ) if env is None else dict(env)
    rules_path = Path(
        environment.get(
            CODEX_EXECPOLICY_RULES_ENV_VAR,
            str(DEFAULT_CODEX_EXECPOLICY_RULES),
        )
    ).expanduser()
    if not rules_path.is_file():
        return ""

    command = [
        "codex",
        "execpolicy",
        "check",
        "-c",
        f'model="{environment.get(CODEX_EXECPOLICY_MODEL_ENV_VAR, DEFAULT_CODEX_EXECPOLICY_MODEL)}"',
        "--rules",
        str(rules_path),
        "--",
        *command_tokens,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd or None,
        )
    except OSError:
        return ""

    if completed.returncode != 0:
        return ""

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ""

    if not isinstance(payload, dict):
        return ""

    decision = payload.get("decision")
    return decision if isinstance(decision, str) else ""
