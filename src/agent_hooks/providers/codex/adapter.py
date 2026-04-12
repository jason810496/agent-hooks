"""Assemble the Codex provider adapter."""

from __future__ import annotations

from agent_hooks.enums import HookProvider
from agent_hooks.providers.codex.middleware import codex_execpolicy_middleware
from agent_hooks.providers.codex.payload import build_hook_payload
from agent_hooks.providers.codex.response import render_response_payload
from agent_hooks.providers.interfaces import HookProviderAdapter

PROVIDER_ADAPTER = HookProviderAdapter(
    provider=HookProvider.CODEX,
    build_hook_payload=build_hook_payload,
    render_response_payload=render_response_payload,
    middlewares=(codex_execpolicy_middleware,),
)
