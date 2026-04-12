"""Define the provider adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_hooks.enums import HookProvider
from agent_hooks.middleware import HookMiddleware
from agent_hooks.models import HookPayload, JsonObject


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


@dataclass(frozen=True)
class HookProviderAdapter:
    """Store the pluggable behavior exposed by one provider module."""

    provider: HookProvider
    build_hook_payload: HookPayloadBuilder
    render_response_payload: HookResponseRenderer
    middlewares: tuple[HookMiddleware, ...] = ()
