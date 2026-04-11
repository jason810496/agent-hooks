"""Define enums used throughout callback processing."""

from __future__ import annotations

from enum import Enum


class HookProvider(str, Enum):
    """Represent the supported hook protocol providers."""

    CLAUDE_CODE = "claude-code"
    CODEX = "codex"


class HookEventName(str, Enum):
    """Represent normalized hook events across supported providers."""

    NOTIFICATION = "Notification"
    PERMISSION_REQUEST = "PermissionRequest"
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"
    STOP_FAILURE = "StopFailure"
    UNKNOWN = "Unknown"


class NotificationType(str, Enum):
    """Represent supported Claude notification types."""

    PERMISSION_PROMPT = "permission_prompt"
    IDLE_PROMPT = "idle_prompt"
    AUTH_SUCCESS = "auth_success"
    ELICITATION_DIALOG = "elicitation_dialog"
    UNKNOWN = "unknown"


class NotificationSound(str, Enum):
    """Represent macOS notification sounds used by the callback."""

    NONE = ""
    PING = "Ping"
    GLASS = "Glass"
    BASSO = "Basso"


class DialogButton(str, Enum):
    """Represent buttons shown in the permission dialog."""

    DENY = "Deny"
    ALLOW_ONCE = "Allow Once"
    ALWAYS_ALLOW = "Always Allow"


class PermissionBehavior(str, Enum):
    """Represent normalized permission decisions."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class HookControlDecision(str, Enum):
    """Represent normalized non-permission control decisions."""

    BLOCK = "block"


class PermissionDestination(str, Enum):
    """Represent Claude permission update destinations."""

    SESSION = "session"


class AppleScriptInvocation(str, Enum):
    """Represent the AppleScript operation being executed."""

    NOTIFICATION = "notification"
    DIALOG = "dialog"


class TransportStatus(str, Enum):
    """Represent the result state for AppleScript execution."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
