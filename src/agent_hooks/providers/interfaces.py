"""Define the provider adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_hooks.enums import DialogButton, HookProvider
from agent_hooks.middleware import HookMiddleware
from agent_hooks.models.schemas.display import DialogSpec, NotificationSpec
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.models.schemas.responses import AppleScriptDialogResponse


class HookPayloadMatcher(Protocol):
    """Define the provider detection callable used by one provider."""

    def __call__(self, raw_payload: JsonObject) -> bool:
        """Return whether one provider owns the raw payload."""
        ...


class HookPayloadBuilder(Protocol):
    """Define the payload builder callable used by one provider."""

    def __call__(self, raw_payload: JsonObject) -> HookPayload:
        """Build a normalized hook payload from one raw provider payload."""
        ...


class HookResponseRenderer(Protocol):
    """Define the response renderer callable used by one provider."""

    def __call__(
        self,
        raw_payload: JsonObject,
        *,
        input_payload: HookPayload | None = None,
    ) -> JsonObject:
        """Render a provider-neutral response into the provider wire format."""
        ...


class HookNotificationBuilder(Protocol):
    """Define the notification builder used by one provider."""

    def __call__(self, payload: HookPayload) -> NotificationSpec | None:
        """Build a provider-specific notification request when supported."""
        ...


class HookPermissionDialogBuilder(Protocol):
    """Define the permission dialog builder used by one provider."""

    def __call__(self, payload: HookPayload) -> DialogSpec:
        """Build a provider-specific permission dialog."""
        ...


class HookPermissionResponseBuilder(Protocol):
    """Define the permission response builder used by one provider."""

    def __call__(self, button: DialogButton, payload: HookPayload) -> AppleScriptDialogResponse:
        """Build the provider response for one permission dialog decision."""
        ...


@dataclass(frozen=True)
class HookProviderAdapter:
    """Store the pluggable behavior exposed by one provider module."""

    provider: HookProvider
    matches_payload: HookPayloadMatcher
    build_hook_payload: HookPayloadBuilder
    render_response_payload: HookResponseRenderer
    build_notification: HookNotificationBuilder
    build_permission_dialog: HookPermissionDialogBuilder
    build_permission_response: HookPermissionResponseBuilder
    middlewares: tuple[HookMiddleware, ...] = ()
