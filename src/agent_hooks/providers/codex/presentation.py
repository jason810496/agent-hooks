"""Build Codex display models."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookEventName, NotificationSound
from agent_hooks.models.schemas.display import DialogSpec, NotificationSpec
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.providers.common import format_tool_detail
from agent_hooks.text import compact_text, first_non_empty_line

PROVIDER_DISPLAY_NAME = "Codex"


def build_notification(payload: HookPayload) -> NotificationSpec | None:
    """Build the supported Codex notification display."""
    if payload.event_name == HookEventName.STOP:
        return NotificationSpec(
            title="Codex finished",
            message=compact_text(
                first_non_empty_line(payload.last_assistant_message) or "Codex finished responding."
            ),
            sound=NotificationSound.GLASS,
        )
    return None


def build_permission_dialog(payload: HookPayload) -> DialogSpec:
    """Build the Codex pre-tool-use permission dialog."""
    return DialogSpec(
        title=f"{PROVIDER_DISPLAY_NAME} — Permission Request",
        message=format_tool_detail(payload),
        buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
        default_button=DialogButton.ALLOW_ONCE,
    )
