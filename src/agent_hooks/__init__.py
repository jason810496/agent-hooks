"""Core package for the agent hook framework."""

from __future__ import annotations

from agent_hooks.cli_app.cli import main
from agent_hooks.models import AppleScriptDialogResponse, HookResponse, HookResponseProtocol
from agent_hooks.processor import build_permission_response
from agent_hooks.router import (
    AgentHook,
    CallbackRequest,
    NotificationEvent,
    PermissionRequestEvent,
    StopEvent,
    StopFailureEvent,
)
from agent_hooks.runner import run_callback

__all__ = [
    "AgentHook",
    "AppleScriptDialogResponse",
    "CallbackRequest",
    "HookResponse",
    "HookResponseProtocol",
    "NotificationEvent",
    "PermissionRequestEvent",
    "StopEvent",
    "StopFailureEvent",
    "build_permission_response",
    "main",
    "run_callback",
]
