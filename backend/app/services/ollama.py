import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    pass


class OllamaService:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout_seconds

    async def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            logger.exception("Ollama request timed out after %s seconds", self.timeout)
            raise OllamaError("Локальная модель не ответила вовремя.") from exc
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "Ollama returned HTTP %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise OllamaError("Локальная модель вернула ошибку.") from exc
        except (httpx.RequestError, ValueError) as exc:
            logger.exception("Could not communicate with Ollama")
            raise OllamaError("Не удалось подключиться к локальной модели.") from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            logger.error("Unexpected Ollama response: %r", data)
            raise OllamaError("Локальная модель вернула пустой ответ.")
        return content.strip()

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                return any(model.get("name") == self.model for model in models)
        except (httpx.HTTPError, ValueError):
            return False
