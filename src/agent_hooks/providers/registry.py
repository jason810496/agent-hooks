"""Register pluggable hook provider adapters."""

from __future__ import annotations

from agent_hooks.enums import HookProvider
from agent_hooks.models import JsonObject
from agent_hooks.providers.interfaces import HookProviderAdapter

from . import claude_code, codex

PROVIDER_ADAPTERS = {
    HookProvider.CLAUDE_CODE: claude_code.PROVIDER_ADAPTER,
    HookProvider.CODEX: codex.PROVIDER_ADAPTER,
}
PROVIDER_DETECTION_ORDER = (
    HookProvider.CODEX,
    HookProvider.CLAUDE_CODE,
)


def get_provider_adapter(provider: HookProvider) -> HookProviderAdapter:
    """Return the registered adapter for one provider."""
    return PROVIDER_ADAPTERS[provider]


def infer_provider_from_payload(
    raw_payload: JsonObject,
    *,
    default_provider: HookProvider,
) -> HookProvider:
    """Infer the provider that owns one raw payload."""
    for provider in PROVIDER_DETECTION_ORDER:
        adapter = get_provider_adapter(provider)
        if adapter.matches_payload(raw_payload):
            return provider
    return default_provider
