"""Build display models from normalized payloads."""

from __future__ import annotations

from agent_hooks.models import DialogSpec, HookPayload, NotificationSpec
from agent_hooks.providers import (
    build_notification as build_provider_notification,
)
from agent_hooks.providers import (
    build_permission_dialog as build_provider_permission_dialog,
)


def build_notification(payload: HookPayload) -> NotificationSpec | None:
    """Map a normalized payload to a notification, when supported."""
    return build_provider_notification(payload)


def build_permission_dialog(payload: HookPayload) -> DialogSpec:
    """Build the permission dialog for a normalized hook payload."""
    return build_provider_permission_dialog(payload)
