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
    ollama: str
    model: str
