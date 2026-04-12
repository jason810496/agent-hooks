"""Register pluggable hook provider adapters."""

from __future__ import annotations

from agent_hooks.enums import HookProvider
from agent_hooks.providers.interfaces import HookProviderAdapter

from . import claude_code, codex

PROVIDER_ADAPTERS = {
    HookProvider.CLAUDE_CODE: claude_code.PROVIDER_ADAPTER,
    HookProvider.CODEX: codex.PROVIDER_ADAPTER,
}


def get_provider_adapter(provider: HookProvider) -> HookProviderAdapter:
    """Return the registered adapter for one provider."""
    return PROVIDER_ADAPTERS[provider]
