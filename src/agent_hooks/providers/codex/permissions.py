"""Build Codex permission dialogs and responses."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookEventName, PermissionBehavior
from agent_hooks.models import (
    AppleScriptDialogResponse,
    HookPayload,
    HookSpecificOutput,
    PermissionDecision,
)


def build_permission_response(
    button: DialogButton,
    payload: HookPayload,
) -> AppleScriptDialogResponse:
    """Build the Codex pre-tool-use response for one dialog decision."""
    hook_specific_output = None
    if button == DialogButton.DENY:
        hook_specific_output = HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=PermissionDecision(behavior=PermissionBehavior.DENY),
            permission_decision_reason="Permission denied by local user.",
        )

    return AppleScriptDialogResponse(
        button=button,
        payload=payload,
        hook_specific_output=hook_specific_output,
    )
