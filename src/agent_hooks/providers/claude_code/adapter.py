"""Assemble the Claude Code provider adapter."""

from __future__ import annotations

from agent_hooks.enums import HookProvider
from agent_hooks.providers.claude_code.payload import build_hook_payload
from agent_hooks.providers.claude_code.response import render_response_payload
from agent_hooks.providers.interfaces import HookProviderAdapter

PROVIDER_ADAPTER = HookProviderAdapter(
    provider=HookProvider.CLAUDE_CODE,
    build_hook_payload=build_hook_payload,
    render_response_payload=render_response_payload,
)
