"""Expose typed data models for callback processing layers."""

from __future__ import annotations

from agent_hooks.models.request import (
    HookInput,
    HookPayload,
    InputAuditLogRecord,
    JsonObject,
    JsonScalar,
    JsonValue,
    ToolInput,
)
from agent_hooks.models.response import (
    AppleScriptDialogResponse,
    AppleScriptResult,
    ApplicationLogRecord,
    DialogResult,
    DialogSpec,
    DisplaySpec,
    HookProcessingResult,
    HookResponse,
    HookResponseProtocol,
    HookSpecificOutput,
    NotificationSpec,
    PermissionDecision,
    PermissionUpdate,
    ResponseAuditLogRecord,
)

__all__ = [
    "AppleScriptDialogResponse",
    "AppleScriptResult",
    "ApplicationLogRecord",
    "DialogResult",
    "DialogSpec",
    "DisplaySpec",
    "HookInput",
    "HookPayload",
    "HookProcessingResult",
    "HookResponse",
    "HookResponseProtocol",
    "HookSpecificOutput",
    "InputAuditLogRecord",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "NotificationSpec",
    "PermissionDecision",
    "PermissionUpdate",
    "ResponseAuditLogRecord",
    "ToolInput",
]
