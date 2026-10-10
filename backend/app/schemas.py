from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config.model_profiles import ProfileName, ResolvedProfile, resolve_profile


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


class OptimizedSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Literal[256, 512, 1024] | None = None
    context_window: Literal[2048, 4096] | None = None
    thinking: bool | None = None

    def resolve(self) -> ResolvedProfile:
        return resolve_profile("optimized", **self.model_dump())


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=20_000)
    profile: ProfileName = "baseline"
    settings: OptimizedSettings | None = None

    @field_validator("content")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Сообщение не может быть пустым.")
        return value

    @model_validator(mode="after")
    def settings_are_optimized_only(self) -> "MessageCreate":
        if self.profile == "baseline" and self.settings is not None:
            raise ValueError("Baseline profile does not accept custom settings.")
        return self

    def resolved_profile(self) -> ResolvedProfile:
        if self.profile == "baseline":
            return resolve_profile("baseline")
        return (self.settings or OptimizedSettings()).resolve()


class CompareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=20_000)
    optimized_settings: OptimizedSettings | None = None

    @field_validator("content")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Сообщение не может быть пустым.")
        return value


class MessageMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int | None
    chat_id: int
    profile: ProfileName
    model: str
    settings_json: dict
    metrics_json: dict
    temperature: float | None
    max_tokens: int | None
    context_window: int | None
    thinking: bool | None
    request_started_at: datetime
    total_latency_ms: float
    ollama_total_duration_ms: float | None
    load_duration_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    prompt_eval_duration_ms: float | None
    generation_duration_ms: float | None
    prompt_tokens_per_second: float | None
    generation_tokens_per_second: float | None
    history_messages_count: int
    history_chars: int
    system_prompt_chars: int
    user_prompt_chars: int
    prompt_chars: int
    success: bool
    error_type: str | None
    created_at: datetime

    @field_validator("request_started_at", "created_at")
    @classmethod
    def attach_utc_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: Literal["user", "assistant"]
    content: str
    comparison_id: str | None
    metrics: MessageMetricRead | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def attach_utc_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class MessageExchange(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead
    chat: ChatRead


class ComparisonExchange(BaseModel):
    chat: ChatRead
    user_message: MessageRead
    baseline_message: MessageRead
    optimized_message: MessageRead


class HealthRead(BaseModel):
    status: str
    ollama: str
    model: str
    models: dict[ProfileName, str]
