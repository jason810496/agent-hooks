"""Provider registry for hook schema parsing and rendering."""

from __future__ import annotations

from agent_hooks.enums import HookProvider
from agent_hooks.middleware import HookMiddleware
from agent_hooks.models import HookPayload, HookResponse, HookResponseProtocol, JsonObject
from agent_hooks.providers.common import coerce_text
from agent_hooks.providers.registry import get_provider_adapter

DEFAULT_PROVIDER = HookProvider.CLAUDE_CODE
CLAUDE_ONLY_EVENTS = frozenset(
    {
        "Notification",
        "PermissionRequest",
        "PermissionDenied",
        "StopFailure",
        "InstructionsLoaded",
        "SubagentStart",
        "SubagentStop",
        "TaskCreated",
        "TaskCompleted",
        "TeammateIdle",
        "ConfigChange",
        "CwdChanged",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PreCompact",
        "PostCompact",
        "Elicitation",
        "ElicitationResult",
        "SessionEnd",
    }
)


def coerce_provider(value: HookProvider | str | None) -> HookProvider:
    """Normalize a provider value."""
    if isinstance(value, HookProvider):
        return value
    if value is None:
        return DEFAULT_PROVIDER
    return HookProvider(value)


def infer_provider(raw_payload: JsonObject) -> HookProvider:
    """Infer the hook provider from the raw input payload."""
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    if raw_event_name in CLAUDE_ONLY_EVENTS:
        return HookProvider.CLAUDE_CODE

    if raw_event_name in {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"}:
        if "turn_id" in raw_payload:
            return HookProvider.CODEX
        return HookProvider.CLAUDE_CODE

    if raw_event_name == "SessionStart":
        codex_markers = {"session_id", "cwd", "permission_mode", "transcript_path"}
        if any(marker in raw_payload for marker in codex_markers):
            return HookProvider.CODEX
        return HookProvider.CLAUDE_CODE

    return DEFAULT_PROVIDER


def build_hook_payload(provider: HookProvider | str | None, raw_payload: JsonObject) -> HookPayload:
    """Build the normalized payload for one provider."""
    adapter = get_provider_adapter(coerce_provider(provider))
    return adapter.build_hook_payload(raw_payload)


def render_response_payload(
    provider: HookProvider | str | None,
    response: HookResponseProtocol | None,
    *,
    input_payload: HookPayload | None = None,
) -> JsonObject:
    """Render a provider-neutral response into the provider wire format."""
    raw_payload = (response or HookResponse()).as_payload()
    adapter = get_provider_adapter(coerce_provider(provider))
    return adapter.render_response_payload(raw_payload, input_payload=input_payload)


def get_provider_middlewares(provider: HookProvider | str | None) -> tuple[HookMiddleware, ...]:
    """Return the provider middlewares configured for one provider."""
    adapter = get_provider_adapter(coerce_provider(provider))
    return adapter.middlewares
