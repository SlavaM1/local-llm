from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.chats as chats_api
import app.api.health as health_api
from app.services.ollama import OllamaResult
from app.services.rag import RAGResult, RAGServiceError


DIRECT_METRICS = {
    "success": True,
    "http_status": 200,
    "total_latency_ms": 12.5,
    "llm_latency_ms": 12.5,
    "total_prompt_chars": 5,
    "input_tokens": 20,
    "output_tokens": 10,
    "total_tokens": 30,
    "prompt_tokens_per_second": 40.0,
    "generation_tokens_per_second": 25.0,
    "token_usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
}


class FakeOllama:
    calls: list[list[dict[str, str]]] = []

    def __init__(self, _settings: object) -> None:
        self.model = "qwen3:8b"

    async def chat(self, messages: list[dict[str, str]]) -> OllamaResult:
        self.calls.append(messages)
        return OllamaResult("local answer", "qwen3:8b", DIRECT_METRICS)

    async def is_available(self) -> bool:
        return True


class FakeRAG:
    calls: list[dict[str, Any]] = []

    def __init__(self, _settings: object) -> None:
        pass

    async def chat(self, **payload: Any) -> RAGResult:
        self.calls.append(payload)
        return RAGResult(
            answer="integrated answer",
            provider=payload["provider"],
            model=payload["model"],
            rag_enabled=payload["rag_enabled"],
            status="answered",
            metrics={
                "total_latency_ms": 21.0,
                "input_tokens": 11,
                "output_tokens": 7,
                "generation_tokens_per_second": 14.0,
            },
            sources=[{"file": "guide.md", "chunk_id": "chunk-1", "final_rank": 1}],
            quotes=[{"quote": "safe quote", "chunk_id": "chunk-1"}],
        )

    async def health(self) -> tuple[bool, bool]:
        return True, True


def create_chat(client: TestClient) -> int:
    response = client.post("/api/chats", json={})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    ("provider", "rag_enabled", "expected_route", "expected_model"),
    [
        ("ollama", False, "direct", "qwen3:8b"),
        ("ollama", True, "rag", "qwen3:8b"),
        ("deepseek", False, "rag", "deepseek-flash"),
        ("deepseek", True, "rag", "deepseek-flash"),
    ],
)
def test_provider_and_rag_routing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    rag_enabled: bool,
    expected_route: str,
    expected_model: str,
) -> None:
    FakeOllama.calls = []
    FakeRAG.calls = []
    monkeypatch.setattr(chats_api, "OllamaService", FakeOllama)
    monkeypatch.setattr(chats_api, "RAGService", FakeRAG)
    chat_id = create_chat(client)

    response = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "hello", "provider": provider, "rag_enabled": rag_enabled},
    )

    assert response.status_code == 201
    assistant = response.json()["assistant_message"]
    assert assistant["provider"] == provider
    assert assistant["model"] == expected_model
    assert assistant["rag_enabled"] is rag_enabled
    assert bool(FakeOllama.calls) is (expected_route == "direct")
    assert bool(FakeRAG.calls) is (expected_route == "rag")
    if FakeRAG.calls:
        assert FakeRAG.calls[0]["model"] == expected_model


def test_defaults_use_direct_ollama_when_rag_and_deepseek_are_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UnavailableRAG:
        def __init__(self, _settings: object) -> None:
            raise AssertionError("RAG must not be constructed for default local mode")

    FakeOllama.calls = []
    monkeypatch.setattr(chats_api, "OllamaService", FakeOllama)
    monkeypatch.setattr(chats_api, "RAGService", UnavailableRAG)
    chat_id = create_chat(client)

    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": "local"})

    assert response.status_code == 201
    assert response.json()["assistant_message"]["provider"] == "ollama"
    assert FakeOllama.calls[-1] == [{"role": "user", "content": "local"}]


def test_history_is_ordered_and_current_question_is_forwarded_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeOllama.calls = []
    FakeRAG.calls = []
    monkeypatch.setattr(chats_api, "OllamaService", FakeOllama)
    monkeypatch.setattr(chats_api, "RAGService", FakeRAG)
    chat_id = create_chat(client)
    first = client.post(f"/api/chats/{chat_id}/messages", json={"content": "first"})
    assert first.status_code == 201

    second = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "current", "provider": "deepseek", "rag_enabled": True},
    )

    assert second.status_code == 201
    call = FakeRAG.calls[-1]
    assert call["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "local answer"},
    ]
    assert call["question"] == "current"
    assert sum(message["content"] == "current" for message in call["messages"]) == 0


def test_metrics_and_evidence_persist_and_reload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeRAG.calls = []
    monkeypatch.setattr(chats_api, "RAGService", FakeRAG)
    chat_id = create_chat(client)
    sent = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "document question", "provider": "ollama", "rag_enabled": True},
    )
    assistant = sent.json()["assistant_message"]

    history = client.get(f"/api/chats/{chat_id}/messages")

    assert history.status_code == 200
    reloaded = history.json()[-1]
    assert reloaded["request_id"] == assistant["request_id"]
    assert reloaded["metrics"]["input_tokens"] == 11
    assert reloaded["metrics"]["total_latency_ms"] >= 0
    assert reloaded["sources"][0]["chunk_id"] == "chunk-1"
    assert reloaded["quotes"][0]["quote"] == "safe quote"


@pytest.mark.parametrize(
    ("detail", "status_code"),
    [
        ("RAG-сервис недоступен.", 503),
        ("RAG-сервис не ответил вовремя.", 504),
        ("Облачная модель отклонила авторизацию.", 502),
        ("RAG-сервис не смог обработать запрос.", 422),
        ("RAG-сервис вернул некорректный ответ.", 502),
    ],
)
def test_rag_errors_are_finite_and_readable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    detail: str,
    status_code: int,
) -> None:
    class FailingRAG:
        def __init__(self, _settings: object) -> None:
            pass

        async def chat(self, **_payload: Any) -> RAGResult:
            raise RAGServiceError(detail, status_code)

    monkeypatch.setattr(chats_api, "RAGService", FailingRAG)
    chat_id = create_chat(client)

    response = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "question", "provider": "deepseek", "rag_enabled": True},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    history = client.get(f"/api/chats/{chat_id}/messages").json()
    assert [message["role"] for message in history] == ["user"]


def test_health_stays_ok_when_optional_services_are_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OfflineOllama(FakeOllama):
        async def is_available(self) -> bool:
            return False

    class OfflineRAG(FakeRAG):
        async def health(self) -> tuple[bool, bool]:
            return False, False

    monkeypatch.setattr(health_api, "OllamaService", OfflineOllama)
    monkeypatch.setattr(health_api, "RAGService", OfflineRAG)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "backend": "ok",
        "ollama": "unavailable",
        "rag": "unavailable",
        "deepseek_configured": False,
        "model": "qwen3:8b",
    }
