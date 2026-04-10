"""Request ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_now_text

if TYPE_CHECKING:
    from .hook_event import HookEvent
    from .session import Session


class Request(Base):
    """Persist actionable work derived from hook events."""

    __tablename__ = "request"
    __table_args__ = (UniqueConstraint("hook_event_id", name="uq_request_hook_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hook_event_id: Mapped[int] = mapped_column(ForeignKey("hook_event.id"), nullable=False)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_choice: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hook_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_text)
    updated_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=utc_now_text,
        onupdate=utc_now_text,
    )

    hook_event: Mapped[HookEvent] = relationship(back_populates="request")
    session: Mapped[Session] = relationship(back_populates="requests")
