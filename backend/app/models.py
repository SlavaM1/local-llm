from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
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
    metrics: Mapped[list["MessageMetric"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", passive_deletes=True
    )
    user: Mapped["User | None"] = relationship(back_populates="chats")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    chats: Mapped[list[Chat]] = relationship(back_populates="user")
    sessions: Mapped[list["SessionToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    user: Mapped[User] = relationship(back_populates="sessions")


class ServiceSettings(Base):
    __tablename__ = "service_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=20)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
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
    comparison_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    chat: Mapped[Chat] = relationship(back_populates="messages")
    metrics: Mapped["MessageMetric | None"] = relationship(
        back_populates="message", uselist=False
    )


class MessageMetric(Base):
    __tablename__ = "message_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, unique=True, index=True
    )
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), index=True
    )
    authenticated_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    profile: Mapped[str] = mapped_column(String(16), index=True)
    model: Mapped[str] = mapped_column(String(120))
    settings_json: Mapped[dict] = mapped_column(JSON)
    metrics_json: Mapped[dict] = mapped_column(JSON)

    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_max_context: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_context: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_context: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thinking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_latency_ms: Mapped[float] = mapped_column(Float)
    ollama_total_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_eval_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    history_messages_count: Mapped[int] = mapped_column(Integer)
    history_messages_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history_messages_sent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history_messages_dropped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history_chars: Mapped[int] = mapped_column(Integer)
    system_prompt_chars: Mapped[int] = mapped_column(Integer)
    user_prompt_chars: Mapped[int] = mapped_column(Integer)
    prompt_chars: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, index=True)
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    message: Mapped[Message | None] = relationship(back_populates="metrics")
    chat: Mapped[Chat] = relationship(back_populates="metrics")
