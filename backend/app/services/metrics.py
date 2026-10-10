from datetime import datetime
from time import perf_counter
from typing import Any

from app.config.model_profiles import ResolvedProfile
from app.models import MessageMetric

PROVIDER_FIELDS = (
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
)


def _number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _milliseconds(value: int | float | None) -> float | None:
    return value / 1_000_000 if value is not None else None


def _tokens_per_second(
    count: int | float | None, duration_ns: int | float | None
) -> float | None:
    if count is None or duration_ns is None or count <= 0 or duration_ns <= 0:
        return None
    return count / (duration_ns / 1_000_000_000)


def prompt_statistics(
    messages: list[dict[str, str]], profile: ResolvedProfile
) -> dict[str, int]:
    latest_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index]["role"] == "user"),
        None,
    )
    if latest_user_index is None:
        history = messages
        user_prompt_chars = 0
    else:
        history = messages[:latest_user_index]
        user_prompt_chars = len(messages[latest_user_index]["content"])
    history_chars = sum(len(message["content"]) for message in history)
    system_prompt_chars = len(profile.system_prompt or "")
    return {
        "history_messages_count": len(history),
        "history_chars": history_chars,
        "system_prompt_chars": system_prompt_chars,
        "user_prompt_chars": user_prompt_chars,
        "prompt_chars": history_chars + system_prompt_chars + user_prompt_chars,
    }


def build_metric(
    *,
    chat_id: int,
    profile: ResolvedProfile,
    messages: list[dict[str, str]],
    request_started_at: datetime,
    request_started_counter: float,
    raw_response: dict[str, Any] | None,
    success: bool,
    error_type: str | None = None,
) -> MessageMetric:
    raw = raw_response or {}
    provider = {
        field: raw[field]
        for field in PROVIDER_FIELDS
        if field in raw and _number(raw[field]) is not None
    }
    total_duration = _number(raw.get("total_duration"))
    load_duration = _number(raw.get("load_duration"))
    input_tokens = _number(raw.get("prompt_eval_count"))
    output_tokens = _number(raw.get("eval_count"))
    prompt_duration = _number(raw.get("prompt_eval_duration"))
    generation_duration = _number(raw.get("eval_duration"))
    total_tokens = (
        int(input_tokens + output_tokens)
        if input_tokens is not None and output_tokens is not None
        else None
    )
    prompt = prompt_statistics(messages, profile)
    return MessageMetric(
        chat_id=chat_id,
        profile=profile.name,
        model=profile.model,
        settings_json=profile.settings_dict(),
        metrics_json=provider,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        context_window=profile.context_window,
        thinking=profile.thinking,
        request_started_at=request_started_at,
        total_latency_ms=(perf_counter() - request_started_counter) * 1000,
        ollama_total_duration_ms=_milliseconds(total_duration),
        load_duration_ms=_milliseconds(load_duration),
        input_tokens=int(input_tokens) if input_tokens is not None else None,
        output_tokens=int(output_tokens) if output_tokens is not None else None,
        total_tokens=total_tokens,
        prompt_eval_duration_ms=_milliseconds(prompt_duration),
        generation_duration_ms=_milliseconds(generation_duration),
        prompt_tokens_per_second=_tokens_per_second(input_tokens, prompt_duration),
        generation_tokens_per_second=_tokens_per_second(output_tokens, generation_duration),
        success=success,
        error_type=error_type,
        **prompt,
    )
