"""Parse stdin into normalized hook models."""

from __future__ import annotations

import json
import sys
from enum import Enum
from json import JSONDecodeError
from typing import IO, TypeVar, cast

from agent_hooks.enums import HookEventName, NotificationType
from agent_hooks.models import (
    HookInput,
    HookPayload,
    JsonObject,
    JsonValue,
    PermissionRule,
    PermissionSuggestion,
    ToolInput,
)

EnumT = TypeVar("EnumT", bound=Enum)


def read_hook_input(stdin: IO[str] | None = None) -> HookInput:
    """Read and decode hook stdin.

    :param stdin: Optional text stream override.
    :type stdin: IO[str] | None
    :return: Parsed hook input result.
    """
    stream = stdin if stdin is not None else sys.stdin
    raw_input = stream.read()
    if not raw_input.strip():
        return HookInput(raw_input=raw_input, payload=HookPayload())

    try:
        parsed = json.loads(raw_input)
    except JSONDecodeError as exc:
        return HookInput(
            raw_input=raw_input,
            payload=HookPayload(),
            parse_error=f"Invalid hook JSON: {exc}",
        )

    if not isinstance(parsed, dict):
        return HookInput(
            raw_input=raw_input,
            payload=HookPayload(),
            parse_error="Hook input was not a JSON object",
        )

    payload = build_hook_payload(cast(JsonObject, parsed))
    return HookInput(raw_input=raw_input, payload=payload)


def build_hook_payload(raw_payload: JsonObject) -> HookPayload:
    """Normalize a raw JSON payload into the domain model.

    :param raw_payload: Raw JSON object from stdin.
    :type raw_payload: JsonObject
    :return: Normalized hook payload.
    """
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    raw_notification_type = coerce_text(raw_payload.get("notification_type"))
    tool_input_raw = coerce_object(raw_payload.get("tool_input"))

    return HookPayload(
        raw=dict(raw_payload),
        event_name=coerce_enum(raw_event_name, HookEventName, HookEventName.UNKNOWN),
        raw_event_name=raw_event_name,
        notification_type=coerce_enum(
            raw_notification_type,
            NotificationType,
            NotificationType.UNKNOWN,
        ),
        raw_notification_type=raw_notification_type,
        title=coerce_text(raw_payload.get("title")),
        message=coerce_text(raw_payload.get("message")),
        last_assistant_message=coerce_text(raw_payload.get("last_assistant_message")),
        error_details=coerce_text(raw_payload.get("error_details")),
        error=coerce_text(raw_payload.get("error")),
        session_id=coerce_text(raw_payload.get("session_id")),
        cwd=coerce_text(raw_payload.get("cwd")),
        tool_name=coerce_text(raw_payload.get("tool_name")),
        tool_input=ToolInput(
            raw=tool_input_raw,
            command=coerce_text(tool_input_raw.get("command")),
            file_path=coerce_text(tool_input_raw.get("file_path")),
            description=coerce_text(tool_input_raw.get("description")),
            url=coerce_text(tool_input_raw.get("url")),
            query=coerce_text(tool_input_raw.get("query")),
            prompt=coerce_text(tool_input_raw.get("prompt")),
            pattern=coerce_text(tool_input_raw.get("pattern")),
        ),
        permission_suggestions=tuple(build_permission_suggestions(raw_payload)),
    )


def build_permission_suggestions(raw_payload: JsonObject) -> list[PermissionSuggestion]:
    """Normalize permission suggestions from the raw payload.

    :param raw_payload: Raw JSON object from stdin.
    :type raw_payload: JsonObject
    :return: Normalized permission suggestions.
    """
    suggestions: list[PermissionSuggestion] = []
    for suggestion_raw in coerce_object_list(raw_payload.get("permission_suggestions")):
        rules = tuple(build_permission_rules(suggestion_raw))
        suggestions.append(PermissionSuggestion(raw=dict(suggestion_raw), rules=rules))
    return suggestions


def build_permission_rules(suggestion_raw: JsonObject) -> list[PermissionRule]:
    """Normalize permission rules from one suggestion payload.

    :param suggestion_raw: Raw suggestion object.
    :type suggestion_raw: JsonObject
    :return: Normalized permission rules.
    """
    rules: list[PermissionRule] = []
    for rule_raw in coerce_object_list(suggestion_raw.get("rules")):
        rules.append(
            PermissionRule(
                tool_name=coerce_text(rule_raw.get("toolName")),
                rule_content=coerce_text(rule_raw.get("ruleContent")),
                raw=dict(rule_raw),
            )
        )
    return rules


def coerce_text(value: JsonValue | object) -> str:
    """Convert a JSON value into a displayable string.

    :param value: Value to normalize.
    :type value: JsonValue | object
    :return: String representation, or an empty string.
    """
    if value is None:
        return ""
    return str(value)


def coerce_object(value: JsonValue | object) -> JsonObject:
    """Return a JSON object when the input is object-like.

    :param value: Raw JSON value.
    :type value: JsonValue | object
    :return: Dictionary value, or an empty dictionary.
    """
    if isinstance(value, dict):
        return cast(JsonObject, dict(value))
    return {}


def coerce_object_list(value: JsonValue | object) -> list[JsonObject]:
    """Return a list containing only JSON objects.

    :param value: Raw JSON value.
    :type value: JsonValue | object
    :return: List of dictionary values.
    """
    if not isinstance(value, list):
        return []

    objects: list[JsonObject] = []
    for item in value:
        if isinstance(item, dict):
            objects.append(cast(JsonObject, item.copy()))
    return objects


def coerce_enum(value: str, enum_type: type[EnumT], default: EnumT) -> EnumT:
    """Convert a string into an enum value with fallback support.

    :param value: Raw enum string.
    :type value: str
    :param enum_type: Enum class to coerce into.
    :type enum_type: type[EnumT]
    :param default: Fallback enum member.
    :type default: EnumT
    :return: Parsed enum member, or the fallback value.
    """
    try:
        return enum_type(value)
    except ValueError:
        return default
