"""Hook event ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_now_text

if TYPE_CHECKING:
    from .request import Request
    from .session import Session


class HookEvent(Base):
    """Persist a single inbound hook callback."""

    __tablename__ = "hook_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"), nullable=False)
    hook_event_name: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    display_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_text)

    session: Mapped[Session] = relationship(back_populates="hook_events")
    request: Mapped[Request | None] = relationship(back_populates="hook_event", uselist=False)
