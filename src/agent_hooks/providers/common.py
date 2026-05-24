"""Shared helpers for provider-specific hook schema adapters."""

from __future__ import annotations

from enum import Enum
from typing import Final, TypeVar, cast

from agent_hooks.config import (
    DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS,
    DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS,
    DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES,
    load_runtime_config,
)
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject, JsonValue
from agent_hooks.text import compact_text

EnumT = TypeVar("EnumT", bound=Enum)
COMMAND_PREVIEW_MAX_TOTAL_CHARS: Final = DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS
COMMAND_PREVIEW_MAX_TOTAL_LINES: Final = DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES
COMMAND_PREVIEW_MAX_LINE_CHARS: Final = DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS


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


def format_tool_detail(
    payload: HookPayload,
    *,
    command_preview_max_total_chars: int | None = None,
    command_preview_max_total_lines: int | None = None,
    command_preview_max_line_chars: int | None = None,
) -> str:
    """Return the multi-line tool summary used by permission dialogs."""
    tool_input = payload.tool_input
    tool_name = payload.tool_name or "Unknown"
    parts: list[str] = [f"Tool: {tool_name}"]

    if tool_input.command:
        parts.append(
            format_command_detail(
                tool_input.command,
                max_total_chars=command_preview_max_total_chars,
                max_total_lines=command_preview_max_total_lines,
                max_line_chars=command_preview_max_line_chars,
            )
        )
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


def format_command_detail(
    command: str,
    *,
    max_total_chars: int | None = None,
    max_total_lines: int | None = None,
    max_line_chars: int | None = None,
) -> str:
    """Return a permission-dialog command summary with multiline commands preserved."""
    command_text = str(command).strip()
    resolved_max_total_chars, resolved_max_total_lines, resolved_max_line_chars = (
        _resolve_preview_limits(
            max_total_chars=max_total_chars,
            max_total_lines=max_total_lines,
            max_line_chars=max_line_chars,
        )
    )
    if "\n" not in command_text and "\r" not in command_text:
        line_limit = min(resolved_max_total_chars, resolved_max_line_chars)
        return f"Command: {_truncate_preview_line(command_text, line_limit)}"

    preview = format_code_preview(
        command_text,
        max_total_chars=resolved_max_total_chars,
        max_total_lines=resolved_max_total_lines,
        max_line_chars=resolved_max_line_chars,
    )
    return f"Command:\n{preview}"


def format_code_preview(
    value: str,
    *,
    max_total_chars: int | None = None,
    max_total_lines: int | None = None,
    max_line_chars: int | None = None,
) -> str:
    """Return a bounded multiline preview while preserving line breaks."""
    resolved_max_total_chars, resolved_max_total_lines, resolved_max_line_chars = (
        _resolve_preview_limits(
            max_total_chars=max_total_chars,
            max_total_lines=max_total_lines,
            max_line_chars=max_line_chars,
        )
    )
    lines = str(value).strip().splitlines()
    if not lines:
        return ""

    preview_lines: list[str] = []
    used_chars = 0
    for line in lines:
        if len(preview_lines) >= resolved_max_total_lines:
            break

        remaining_total_chars = resolved_max_total_chars - used_chars
        if remaining_total_chars <= 0:
            break

        line_limit = min(resolved_max_line_chars, remaining_total_chars)
        rendered_line = _truncate_preview_line(line, line_limit)
        preview_lines.append(rendered_line)
        used_chars += len(rendered_line) + 1

        if line_limit == remaining_total_chars and len(line) > line_limit:
            break

    omitted_lines = len(lines) - len(preview_lines)
    if omitted_lines > 0:
        preview_lines.append(f"… +{omitted_lines} lines")

    return "\n".join(preview_lines)


def _truncate_preview_line(line: str, limit: int) -> str:
    """Return one command preview line constrained to a positive width."""
    if len(line) <= limit:
        return line

    return f"{line[: limit - 1].rstrip()}…"


def _resolve_preview_limits(
    *,
    max_total_chars: int | None,
    max_total_lines: int | None,
    max_line_chars: int | None,
) -> tuple[int, int, int]:
    """Return configured command preview limits, honoring explicit overrides."""
    config = load_runtime_config()
    return (
        _resolve_preview_limit(
            max_total_chars,
            configured_value=config.command_preview_max_total_chars,
            default=COMMAND_PREVIEW_MAX_TOTAL_CHARS,
        ),
        _resolve_preview_limit(
            max_total_lines,
            configured_value=config.command_preview_max_total_lines,
            default=COMMAND_PREVIEW_MAX_TOTAL_LINES,
        ),
        _resolve_preview_limit(
            max_line_chars,
            configured_value=config.command_preview_max_line_chars,
            default=COMMAND_PREVIEW_MAX_LINE_CHARS,
        ),
    )


def _resolve_preview_limit(
    explicit_value: int | None,
    *,
    configured_value: int,
    default: int,
) -> int:
    """Return a positive preview limit from an explicit value, config, or default."""
    if explicit_value is not None:
        return _positive_limit_or_default(explicit_value, default)
    return _positive_limit_or_default(configured_value, default)


def _positive_limit_or_default(value: int, default: int) -> int:
    """Return ``value`` when positive, otherwise ``default``."""
    if value > 0:
        return value
    return default
