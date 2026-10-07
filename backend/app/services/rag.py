import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class RAGServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 503) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class RAGResult:
    answer: str
    provider: str
    model: str
    rag_enabled: bool
    status: str
    metrics: dict[str, Any]
    sources: list[Any]
    quotes: list[Any]


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.rag_service_url.rstrip("/")
        self.timeout = settings.rag_timeout_seconds
        self.health_timeout = settings.health_timeout_seconds

    async def chat(
        self,
        *,
        request_id: str,
        provider: str,
        model: str,
        rag_enabled: bool,
        messages: list[dict[str, str]],
        question: str,
    ) -> RAGResult:
        payload = {
            "request_id": request_id,
            "question": question,
            "messages": messages,
            "provider": provider,
            "model": model,
            "rag_enabled": rag_enabled,
            "strategy": "structural",
            "retrieval_mode": "enhanced",
            "candidate_top_k": 15,
            "final_top_k": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/integration/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise RAGServiceError("RAG-сервис не ответил вовремя.", 504) from exc
        except httpx.RequestError as exc:
            raise RAGServiceError("RAG-сервис недоступен.", 503) from exc

        if response.is_error:
            detail = _upstream_error(response)
            logger.warning(
                "RAG request failed request_id=%s upstream_status=%s",
                request_id,
                response.status_code,
            )
            if response.status_code == 504:
                raise RAGServiceError("Модель или RAG-сервис не ответили вовремя.", 504)
            if response.status_code in {401, 403} or "auth" in detail.lower():
                raise RAGServiceError("Облачная модель отклонила авторизацию.", 502)
            if response.status_code == 422:
                raise RAGServiceError("RAG-сервис не смог обработать запрос.", 422)
            raise RAGServiceError("RAG-сервис не смог сформировать ответ.", 503)

        try:
            data = response.json()
        except ValueError as exc:
            raise RAGServiceError("RAG-сервис вернул некорректный ответ.", 502) from exc
        if not isinstance(data, dict):
            raise RAGServiceError("RAG-сервис вернул некорректный ответ.", 502)

        answer = data.get("answer")
        status = data.get("status")
        metrics = data.get("metrics")
        sources = data.get("sources")
        quotes = data.get("quotes")
        returned_model = data.get("model")
        if (
            data.get("request_id") != request_id
            or data.get("provider") != provider
            or data.get("rag_enabled") is not rag_enabled
            or not isinstance(answer, str)
            or not answer.strip()
            or not isinstance(status, str)
            or not isinstance(metrics, dict)
            or not isinstance(sources, list)
            or not isinstance(quotes, list)
            or not isinstance(returned_model, str)
        ):
            raise RAGServiceError("RAG-сервис вернул некорректный ответ.", 502)
        return RAGResult(
            answer=answer.strip(),
            provider=provider,
            model=returned_model,
            rag_enabled=rag_enabled,
            status=status,
            metrics=metrics,
            sources=sources,
            quotes=quotes,
        )

    async def health(self) -> tuple[bool, bool]:
        try:
            async with httpx.AsyncClient(timeout=self.health_timeout) as client:
                response = await client.get(f"{self.base_url}/health")
            if not response.is_success:
                return False, False
            data = response.json()
            if not isinstance(data, dict):
                return False, False
            return (
                data.get("local_retrieval_ready") is True,
                data.get("deepseek_configured") is True,
            )
        except (httpx.HTTPError, ValueError):
            return False, False


def _upstream_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    for key in ("error", "detail"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    return ""
