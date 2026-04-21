"""Provider registry facade for payload parsing and response rendering."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookProvider
from agent_hooks.middleware import HookMiddleware
from agent_hooks.models.schemas.display import DialogSpec, NotificationSpec
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.models.schemas.responses import (
    AppleScriptDialogResponse,
    HookResponse,
    HookResponseProtocol,
)
from agent_hooks.providers.registry import get_provider_adapter, infer_provider_from_payload

DEFAULT_PROVIDER = HookProvider.CLAUDE_CODE


class HookProviderClient:
    """Coordinate all registered hook provider adapters."""

    default_provider: HookProvider = DEFAULT_PROVIDER

    def coerce_provider(self, value: HookProvider | str | None) -> HookProvider:
        """Normalize a provider value.

        :param value: Provider enum, provider string, or ``None``.
        :type value: HookProvider | str | None
        :return: Resolved provider enum.
        :raises ValueError: If a provider string is not supported.
        """
        if isinstance(value, HookProvider):
            return value
        if value is None:
            return self.default_provider
        return HookProvider(value)

    def infer_provider(self, raw_payload: JsonObject) -> HookProvider:
        """Infer the hook provider from the raw input payload.

        :param raw_payload: Raw decoded hook JSON payload.
        :type raw_payload: JsonObject
        :return: Inferred provider enum.
        """
        return infer_provider_from_payload(raw_payload, default_provider=self.default_provider)

    def build_hook_payload(
        self,
        raw_payload: JsonObject,
        *,
        provider: HookProvider | str | None = None,
    ) -> HookPayload:
        """Build the normalized payload for one provider.

        :param raw_payload: Raw decoded hook JSON payload.
        :type raw_payload: JsonObject
        :param provider: Provider override.
        :type provider: HookProvider | str | None
        :return: Normalized hook payload.
        """
        adapter = get_provider_adapter(self.coerce_provider(provider))
        return adapter.build_hook_payload(raw_payload)

    def render_response_payload(
        self,
        response: HookResponseProtocol | None,
        *,
        provider: HookProvider | str | None = None,
        input_payload: HookPayload | None = None,
    ) -> JsonObject:
        """Render a provider-neutral response into the provider wire format.

        :param response: Provider-neutral response model.
        :type response: HookResponseProtocol | None
        :param provider: Provider override.
        :type provider: HookProvider | str | None
        :param input_payload: Parsed input payload used to infer event-specific rendering.
        :type input_payload: HookPayload | None
        :return: Provider wire payload.
        """
        raw_payload = (response or HookResponse()).as_payload()
        adapter = get_provider_adapter(self.coerce_provider(provider))
        return adapter.render_response_payload(raw_payload, input_payload=input_payload)

    def build_notification(self, payload: HookPayload) -> NotificationSpec | None:
        """Build the provider-specific notification display, when supported.

        :param payload: Normalized hook payload.
        :type payload: HookPayload
        :return: Notification request, or ``None`` when the event is not displayable.
        """
        adapter = get_provider_adapter(payload.provider)
        return adapter.build_notification(payload)

    def build_permission_dialog(self, payload: HookPayload) -> DialogSpec:
        """Build the provider-specific permission dialog.

        :param payload: Normalized hook payload.
        :type payload: HookPayload
        :return: Permission dialog request.
        """
        adapter = get_provider_adapter(payload.provider)
        return adapter.build_permission_dialog(payload)

    def build_permission_response(
        self,
        button: DialogButton,
        payload: HookPayload,
    ) -> AppleScriptDialogResponse:
        """Build the provider response for one permission dialog selection.

        :param button: Selected dialog button.
        :type button: DialogButton
        :param payload: Normalized hook payload.
        :type payload: HookPayload
        :return: Provider-neutral dialog response.
        """
        adapter = get_provider_adapter(payload.provider)
        return adapter.build_permission_response(button, payload)

    def get_middlewares(self, provider: HookProvider | str | None) -> tuple[HookMiddleware, ...]:
        """Return the provider middlewares configured for one provider.

        :param provider: Provider override.
        :type provider: HookProvider | str | None
        :return: Middleware chain for the provider.
        """
        adapter = get_provider_adapter(self.coerce_provider(provider))
        return adapter.middlewares


provider_client = HookProviderClient()


def coerce_provider(value: HookProvider | str | None) -> HookProvider:
    """Normalize a provider value."""
    return provider_client.coerce_provider(value)


def infer_provider(raw_payload: JsonObject) -> HookProvider:
    """Infer the hook provider from the raw input payload."""
    return provider_client.infer_provider(raw_payload)


def build_hook_payload(provider: HookProvider | str | None, raw_payload: JsonObject) -> HookPayload:
    """Build the normalized payload for one provider."""
    return provider_client.build_hook_payload(raw_payload, provider=provider)


def render_response_payload(
    provider: HookProvider | str | None,
    response: HookResponseProtocol | None,
    *,
    input_payload: HookPayload | None = None,
) -> JsonObject:
    """Render a provider-neutral response into the provider wire format."""
    return provider_client.render_response_payload(
        response,
        provider=provider,
        input_payload=input_payload,
    )


def build_notification(payload: HookPayload) -> NotificationSpec | None:
    """Build the provider-specific notification display, when supported."""
    return provider_client.build_notification(payload)


def build_permission_dialog(payload: HookPayload) -> DialogSpec:
    """Build the provider-specific permission dialog."""
    return provider_client.build_permission_dialog(payload)


def build_permission_response(
    button: DialogButton,
    payload: HookPayload,
) -> AppleScriptDialogResponse:
    """Build the provider response for one permission dialog selection."""
    return provider_client.build_permission_response(button, payload)


def get_provider_middlewares(provider: HookProvider | str | None) -> tuple[HookMiddleware, ...]:
    """Return the provider middlewares configured for one provider."""
    return provider_client.get_middlewares(provider)


__all__ = [
    "DEFAULT_PROVIDER",
    "HookProviderClient",
    "build_hook_payload",
    "build_notification",
    "build_permission_dialog",
    "build_permission_response",
    "coerce_provider",
    "get_provider_middlewares",
    "infer_provider",
    "provider_client",
    "render_response_payload",
]
