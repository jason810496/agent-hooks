"""Shared SQLAlchemy model helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def utc_now_text() -> str:
    """Return the current UTC time encoded as ISO 8601 text.

    :return: A UTC timestamp suitable for text-backed SQLite columns.
    """
    return datetime.now(timezone.utc).isoformat()
