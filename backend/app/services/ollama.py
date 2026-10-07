import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    pass


@dataclass(frozen=True)
class OllamaResult:
    answer: str
    model: str
    metrics: dict[str, Any]


class OllamaService:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout_seconds
        self.health_timeout = settings.health_timeout_seconds

    async def chat(self, messages: list[dict[str, str]]) -> OllamaResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
        }

        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("response is not an object")
        except httpx.TimeoutException as exc:
            logger.exception("Ollama request timed out after %s seconds", self.timeout)
            raise OllamaError("Локальная модель не ответила вовремя.") from exc
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Ollama returned HTTP %s",
                exc.response.status_code,
            )
            raise OllamaError("Локальная модель вернула ошибку.") from exc
        except (httpx.RequestError, ValueError) as exc:
            logger.exception("Could not communicate with Ollama")
            raise OllamaError("Не удалось подключиться к локальной модели.") from exc

        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            logger.error("Ollama returned a response without message content")
            raise OllamaError("Локальная модель вернула пустой ответ.")
        prompt_tokens = _optional_int(data.get("prompt_eval_count"))
        output_tokens = _optional_int(data.get("eval_count"))
        total_tokens = (
            prompt_tokens + output_tokens
            if prompt_tokens is not None and output_tokens is not None
            else None
        )
        prompt_duration_ms = _nanoseconds_to_milliseconds(data.get("prompt_eval_duration"))
        generation_duration_ms = _nanoseconds_to_milliseconds(data.get("eval_duration"))
        prompt_rate = _tokens_per_second(prompt_tokens, prompt_duration_ms)
        generation_rate = _tokens_per_second(output_tokens, generation_duration_ms)
        call_metrics = {
            "prompt_eval_count": prompt_tokens,
            "eval_count": output_tokens,
            "total_duration_ms": _nanoseconds_to_milliseconds(data.get("total_duration")),
            "load_duration_ms": _nanoseconds_to_milliseconds(data.get("load_duration")),
            "prompt_eval_duration_ms": prompt_duration_ms,
            "eval_duration_ms": generation_duration_ms,
            "done": data.get("done") if isinstance(data.get("done"), bool) else None,
            "done_reason": data.get("done_reason") if isinstance(data.get("done_reason"), str) else None,
        }
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return OllamaResult(
            answer=content.strip(),
            model=data.get("model") if isinstance(data.get("model"), str) else self.model,
            metrics={
                "success": True,
                "http_status": 200,
                "total_latency_ms": latency_ms,
                "llm_latency_ms": latency_ms,
                "total_prompt_chars": sum(len(message["content"]) for message in messages),
                "input_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "prompt_tokens_per_second": prompt_rate,
                "generation_tokens_per_second": generation_rate,
                "token_usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                "token_rates": {
                    "prompt_tokens_per_second": prompt_rate,
                    "generation_tokens_per_second": generation_rate,
                },
                "provider_specific": {"calls": [call_metrics]},
            },
        )

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.health_timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                return any(model.get("name") == self.model for model in models)
        except (httpx.HTTPError, ValueError):
            return False


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nanoseconds_to_milliseconds(value: object) -> float | None:
    return round(value / 1_000_000, 2) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _tokens_per_second(tokens: int | None, duration_ms: float | None) -> float | None:
    if tokens is None or duration_ms is None or duration_ms <= 0:
        return None
    return round(tokens / (duration_ms / 1000), 2)
