"""Shared helpers for provider-specific hook schema adapters."""

from __future__ import annotations

from enum import Enum
from typing import TypeVar, cast

from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject, JsonValue
from agent_hooks.text import compact_text

EnumT = TypeVar("EnumT", bound=Enum)


def coerce_text(value: JsonValue | object) -> str:
    """Convert a JSON value into a displayable string."""
    if value is None:
        return ""
    return str(value)


def coerce_bool(value: JsonValue | object) -> bool:
    """Convert a JSON value into a boolean."""
    return bool(value) if isinstance(value, bool) else False


def coerce_object(value: JsonValue | object) -> JsonObject:
    """Return a JSON object when the input is object-like."""
    if isinstance(value, dict):
        return cast(JsonObject, dict(value))
    return {}


def coerce_object_list(value: JsonValue | object) -> list[JsonObject]:
    """Return a list containing only JSON objects."""
    if not isinstance(value, list):
        return []

    objects: list[JsonObject] = []
    for item in value:
        if isinstance(item, dict):
            objects.append(cast(JsonObject, item.copy()))
    return objects


def coerce_enum(value: str, enum_type: type[EnumT], default: EnumT) -> EnumT:
    """Convert a string into an enum value with fallback support."""
    try:
        return enum_type(value)
    except ValueError:
        return default


def format_tool_detail(payload: HookPayload) -> str:
    """Return the multi-line tool summary used by permission dialogs."""
    tool_input = payload.tool_input
    tool_name = payload.tool_name or "Unknown"
    parts: list[str] = [f"Tool: {tool_name}"]

    if tool_input.command:
        parts.append(f"Command: {compact_text(tool_input.command, limit=400)}")
    if tool_input.file_path:
        parts.append(f"File: {compact_text(tool_input.file_path, limit=400)}")
    if tool_input.description:
        parts.append(f"Description: {compact_text(tool_input.description, limit=300)}")
    if tool_input.url:
        parts.append(f"URL: {compact_text(tool_input.url, limit=400)}")
    if tool_input.query:
        parts.append(f"Query: {compact_text(tool_input.query, limit=300)}")
    if tool_input.prompt and not tool_input.command:
        parts.append(f"Prompt: {compact_text(tool_input.prompt, limit=300)}")
    if tool_input.pattern:
        parts.append(f"Pattern: {compact_text(tool_input.pattern, limit=300)}")

    return "\n".join(parts)
