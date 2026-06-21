"""Parse stdin into normalized hook models."""

from __future__ import annotations

import json
import sys
from json import JSONDecodeError
from typing import IO, cast

from agent_hooks.enums import HookProvider
from agent_hooks.models.schemas.hooks import HookInput, HookPayload
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.providers import provider_client


def read_hook_input(
    stdin: IO[str] | None = None,
    *,
    provider: HookProvider | str | None = None,
) -> HookInput:
    """Read and decode hook stdin."""
    stream = stdin if stdin is not None else sys.stdin
    raw_input = stream.read()
    resolved_provider = provider_client.coerce_provider(provider) if provider is not None else None
    if not raw_input.strip():
        return HookInput(
            raw_input=raw_input,
            payload=HookPayload(provider=provider_client.coerce_provider(resolved_provider)),
        )

    try:
        parsed = json.loads(raw_input)
    except JSONDecodeError as exc:
        return HookInput(
            raw_input=raw_input,
            payload=HookPayload(provider=provider_client.coerce_provider(resolved_provider)),
            parse_error=f"Invalid hook JSON: {exc}",
        )

    if not isinstance(parsed, dict):
        return HookInput(
            raw_input=raw_input,
            payload=HookPayload(provider=provider_client.coerce_provider(resolved_provider)),
            parse_error="Hook input was not a JSON object",
        )

    parsed_payload = cast(JsonObject, parsed)
    effective_provider = resolved_provider or provider_client.infer_provider(parsed_payload)
    payload = build_hook_payload(parsed_payload, provider=effective_provider)
    return HookInput(raw_input=raw_input, payload=payload)


def build_hook_payload(
    raw_payload: JsonObject,
    *,
    provider: HookProvider | str | None = None,
) -> HookPayload:
    """Normalize a raw JSON payload into the shared domain model."""
    return provider_client.build_hook_payload(raw_payload, provider=provider)
