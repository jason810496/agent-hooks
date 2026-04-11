"""Serialize dataclasses and enums into JSON-safe values."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import cast

from agent_hooks.models import JsonObject, JsonValue


def serialize_json_value(value: object) -> JsonValue:
    """Convert supported Python objects into JSON-safe values.

    :param value: Value to serialize.
    :type value: object
    :return: JSON-safe value.
    :raises TypeError: If the value cannot be serialized safely.
    """
    if value is None or isinstance(value, str | int | float | bool):
        return cast(JsonValue, value)

    if isinstance(value, Enum):
        return cast(JsonValue, value.value)

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value):
        return cast(
            JsonObject,
            {item.name: serialize_json_value(getattr(value, item.name)) for item in fields(value)},
        )

    if isinstance(value, dict):
        return {str(key): serialize_json_value(item) for key, item in value.items()}

    if isinstance(value, list | tuple):
        return [serialize_json_value(item) for item in value]

    msg = f"Unsupported value for JSON serialization: {type(value).__name__}"
    raise TypeError(msg)
