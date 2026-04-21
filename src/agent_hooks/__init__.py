"""Core package for the agent hook framework."""

from __future__ import annotations

from agent_hooks.cli_app.cli import main
from agent_hooks.enums import HookProvider
from agent_hooks.models.events import (
    HookEvent,
    NotificationEvent,
    PermissionRequestEvent,
    PostToolUseEvent,
    SessionStartEvent,
    StopEvent,
    StopFailureEvent,
    UserPromptSubmitEvent,
)
from agent_hooks.models.response import (
    AppleScriptDialogResponse,
    HookResponse,
    HookResponseProtocol,
)
from agent_hooks.processor import build_permission_response
from agent_hooks.router import AgentHook, CallbackRequest
from agent_hooks.runner import run_callback

__all__ = [
    "AgentHook",
    "AppleScriptDialogResponse",
    "CallbackRequest",
    "HookEvent",
    "HookProvider",
    "HookResponse",
    "HookResponseProtocol",
    "NotificationEvent",
    "PermissionRequestEvent",
    "PostToolUseEvent",
    "SessionStartEvent",
    "StopEvent",
    "StopFailureEvent",
    "UserPromptSubmitEvent",
    "build_permission_response",
    "main",
    "run_callback",
]
