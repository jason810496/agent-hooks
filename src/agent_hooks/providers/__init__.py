"""Provider registry helpers for payload parsing and response rendering."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookProvider
from agent_hooks.middleware import HookMiddleware
from agent_hooks.models import (
    AppleScriptDialogResponse,
    DialogSpec,
    HookPayload,
    HookResponse,
    HookResponseProtocol,
    JsonObject,
    NotificationSpec,
)
from agent_hooks.providers.registry import get_provider_adapter, infer_provider_from_payload

DEFAULT_PROVIDER = HookProvider.CLAUDE_CODE


def coerce_provider(value: HookProvider | str | None) -> HookProvider:
    """Normalize a provider value."""
    if isinstance(value, HookProvider):
        return value
    if value is None:
        return DEFAULT_PROVIDER
    return HookProvider(value)


def infer_provider(raw_payload: JsonObject) -> HookProvider:
    """Infer the hook provider from the raw input payload."""
    return infer_provider_from_payload(raw_payload, default_provider=DEFAULT_PROVIDER)


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


def build_notification(payload: HookPayload) -> NotificationSpec | None:
    """Build the provider-specific notification display, when supported."""
    adapter = get_provider_adapter(payload.provider)
    return adapter.build_notification(payload)


def build_permission_dialog(payload: HookPayload) -> DialogSpec:
    """Build the provider-specific permission dialog."""
    adapter = get_provider_adapter(payload.provider)
    return adapter.build_permission_dialog(payload)


def build_permission_response(
    button: DialogButton,
    payload: HookPayload,
) -> AppleScriptDialogResponse:
    """Build the provider response for one permission dialog selection."""
    adapter = get_provider_adapter(payload.provider)
    return adapter.build_permission_response(button, payload)


def get_provider_middlewares(provider: HookProvider | str | None) -> tuple[HookMiddleware, ...]:
    """Return the provider middlewares configured for one provider."""
    adapter = get_provider_adapter(coerce_provider(provider))
    return adapter.middlewares
