"""Provide text normalization helpers for display strings."""

from __future__ import annotations

from typing import Any


def compact_text(value: Any, *, limit: int = 220) -> str:
    """Collapse whitespace and trim long strings for UI display.

    :param value: Raw value to compact.
    :type value: Any
    :param limit: Maximum output length.
    :type limit: int
    :return: Compact display string.
    """
    if value is None:
        return ""

    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text

    return f"{text[: limit - 1].rstrip()}…"


def first_non_empty_line(value: Any) -> str:
    """Return the first non-empty line from a string-like value.

    :param value: Raw value to inspect.
    :type value: Any
    :return: First non-empty line, or an empty string.
    """
    if value is None:
        return ""

    for line in str(value).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return ""


def humanize(value: Any) -> str:
    """Convert snake_case values into title-cased labels.

    :param value: Raw value to humanize.
    :type value: Any
    :return: Human-readable label.
    """
    if value is None:
        return ""

    return str(value).replace("_", " ").strip().title()
