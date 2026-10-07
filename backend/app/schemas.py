from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatCreate(BaseModel):
    pass


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def attach_utc_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class MessageCreate(BaseModel):
    content: str = Field(max_length=20_000)
    provider: Literal["ollama", "deepseek"] = "ollama"
    rag_enabled: bool = False

    @field_validator("content")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Сообщение не может быть пустым.")
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    request_id: str | None = None
    provider: Literal["ollama", "deepseek"] | None = None
    model: str | None = None
    rag_enabled: bool | None = None
    status: str | None = None
    metrics: dict[str, object] | None = None
    sources: list[object] = Field(default_factory=list)
    quotes: list[object] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def attach_utc_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class MessageExchange(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead
    chat: ChatRead


class HealthRead(BaseModel):
    status: str
    backend: Literal["ok", "unavailable"]
    ollama: str
    rag: str
    deepseek_configured: bool
    model: str
