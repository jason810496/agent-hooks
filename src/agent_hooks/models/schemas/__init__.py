"""Expose implementation schema models used by Agent Hooks internals."""

from __future__ import annotations

from agent_hooks.models.schemas.display import (
    AppleScriptResult,
    AskUserQuestionDialogResult,
    AskUserQuestionDialogSpec,
    AskUserQuestionEntry,
    AskUserQuestionOption,
    DialogResult,
    DialogSpec,
    DisplaySpec,
    NotificationSpec,
    PermissionChoice,
    PermissionChoiceDialogResult,
    PermissionChoiceDialogSpec,
)
from agent_hooks.models.schemas.hooks import HookInput, HookPayload, ToolInput
from agent_hooks.models.schemas.json_types import JsonObject, JsonScalar, JsonValue
from agent_hooks.models.schemas.log_records import (
    ApplicationLogRecord,
    InputAuditLogRecord,
    ResponseAuditLogRecord,
)
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
    "AskUserQuestionDialogResult",
    "AskUserQuestionDialogSpec",
    "AskUserQuestionEntry",
    "AskUserQuestionOption",
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
    "PermissionChoice",
    "PermissionChoiceDialogResult",
    "PermissionChoiceDialogSpec",
    "PermissionDecision",
    "PermissionUpdate",
    "ResponseAuditLogRecord",
    "ToolInput",
]
