"""Shared helpers for provider-specific hook schema adapters."""

from __future__ import annotations

from enum import Enum
from typing import TypeVar, cast

from agent_hooks.models import JsonObject, JsonValue

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
