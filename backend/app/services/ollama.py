import logging
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from app.config import Settings
from app.config.model_profiles import MODEL_PROFILES, ResolvedProfile

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    def __init__(self, message: str, error_type: str) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class OllamaResult:
    content: str
    raw_response: dict[str, Any]


class OllamaService:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ollama_url.rstrip("/")
        self.timeout = settings.ollama_timeout_seconds

    async def chat(
        self, messages: list[dict[str, str]], profile: ResolvedProfile
    ) -> OllamaResult:
        request_messages = messages
        payload: dict[str, Any] = {
            "model": profile.model,
            "messages": request_messages,
            "stream": False,
            "think": profile.thinking,
        }
        if profile.name == "optimized":
            request_messages = [
                {"role": "system", "content": profile.system_prompt or ""},
                *messages,
            ]
            payload["messages"] = request_messages
            payload["options"] = {
                "temperature": profile.temperature,
                "num_predict": profile.max_tokens,
                "num_ctx": profile.context_window,
                "top_p": profile.top_p,
                "repeat_penalty": profile.repeat_penalty,
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError as exc:
                    logger.exception("Could not parse Ollama JSON response")
                    raise OllamaError(
                        "Локальная модель вернула некорректный ответ.", "parse_error"
                    ) from exc
        except OllamaError:
            raise
        except httpx.TimeoutException as exc:
            logger.exception("Ollama request timed out after %s seconds", self.timeout)
            raise OllamaError(
                "Локальная модель не ответила вовремя.", "timeout"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Ollama returned HTTP %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise OllamaError("Локальная модель вернула ошибку.", "http_error") from exc
        except httpx.RequestError as exc:
            logger.exception("Could not communicate with Ollama")
            raise OllamaError(
                "Не удалось подключиться к локальной модели.", "network_error"
            ) from exc

        if not isinstance(data, dict):
            raise OllamaError(
                "Локальная модель вернула некорректный ответ.", "parse_error"
            )
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            logger.error("Unexpected Ollama response: %r", data)
            raise OllamaError(
                "Локальная модель вернула пустой ответ.", "empty_response"
            )
        return OllamaResult(content=content.strip(), raw_response=data)

    async def is_available(
        self, models: Iterable[str] | None = None, *, require_all: bool = True
    ) -> bool:
        expected = set(models or (profile.model for profile in MODEL_PROFILES.values()))
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                available = {
                    item.get("name")
                    for item in data.get("models", [])
                    if isinstance(item, dict)
                }
                return expected <= available if require_all else bool(expected & available)
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
