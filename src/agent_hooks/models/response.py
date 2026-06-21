"""Expose response-side models for application authors."""

from __future__ import annotations

from agent_hooks.models.schemas.display import (
    AppleScriptResult,
    DialogResult,
    DialogSpec,
    DisplaySpec,
    NotificationSpec,
)
from agent_hooks.models.schemas.json_types import JsonObject, JsonScalar, JsonValue
from agent_hooks.models.schemas.log_records import ApplicationLogRecord, ResponseAuditLogRecord
from agent_hooks.models.schemas.permissions import PermissionDecision, PermissionUpdate
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import (
    AppleScriptDialogResponse,
    HookResponse,
    HookResponseProtocol,
    HookSpecificOutput,
)

__all__ = [
    "AppleScriptDialogResponse",
    "AppleScriptResult",
    "ApplicationLogRecord",
    "DialogResult",
    "DialogSpec",
    "DisplaySpec",
    "HookProcessingResult",
    "HookResponse",
    "HookResponseProtocol",
    "HookSpecificOutput",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "NotificationSpec",
    "PermissionDecision",
    "PermissionUpdate",
    "ResponseAuditLogRecord",
]
