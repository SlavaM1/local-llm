import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), default="Новый диалог")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="valid_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    chat: Mapped[Chat] = relationship(back_populates="messages")
    generation_metadata: Mapped["MessageMetadata | None"] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    @property
    def request_id(self) -> str | None:
        return self.generation_metadata.request_id if self.generation_metadata else None

    @property
    def provider(self) -> str | None:
        return self.generation_metadata.provider if self.generation_metadata else None

    @property
    def model(self) -> str | None:
        return self.generation_metadata.model if self.generation_metadata else None

    @property
    def rag_enabled(self) -> bool | None:
        return self.generation_metadata.rag_enabled if self.generation_metadata else None

    @property
    def status(self) -> str | None:
        return self.generation_metadata.status if self.generation_metadata else None

    @property
    def metrics(self) -> dict[str, Any] | None:
        return _safe_json(self.generation_metadata.metrics_json, dict) if self.generation_metadata else None

    @property
    def sources(self) -> list[Any]:
        return _safe_json(self.generation_metadata.sources_json, list) if self.generation_metadata else []

    @property
    def quotes(self) -> list[Any]:
        return _safe_json(self.generation_metadata.quotes_json, list) if self.generation_metadata else []


class MessageMetadata(Base):
    __tablename__ = "message_metadata"

    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    request_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(200))
    rag_enabled: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(40))
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    quotes_json: Mapped[str] = mapped_column(Text, default="[]")
    message: Mapped[Message] = relationship(back_populates="generation_metadata")


def _safe_json(value: str, expected_type: type[dict] | type[list]) -> Any:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        parsed = None
    return parsed if isinstance(parsed, expected_type) else ({} if expected_type is dict else [])
