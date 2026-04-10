"""Session ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utc_now_text

if TYPE_CHECKING:
    from .hook_event import HookEvent
    from .request import Request


class Session(Base):
    """Persist provider session metadata."""

    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("provider_session_id", name="uq_session_provider_session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_session_id: Mapped[str] = mapped_column(Text, nullable=False)
    cwd: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    permission_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_text)
    updated_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=utc_now_text,
        onupdate=utc_now_text,
    )
    last_seen_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=utc_now_text,
        onupdate=utc_now_text,
    )

    hook_events: Mapped[list[HookEvent]] = relationship(back_populates="session")
    requests: Mapped[list[Request]] = relationship(back_populates="session")
