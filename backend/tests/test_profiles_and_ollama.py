import asyncio

import httpx
import pytest

from app.config import Settings
from app.config.model_profiles import MODEL_PROFILES, apply_service_context, resolve_profile
from app.services.ollama import OllamaError, OllamaService


class FakeClient:
    def __init__(self, outcome, captured):
        self.outcome = outcome
        self.captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, json):
        self.captured.update(url=url, payload=json)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def response(data=None, status=200, content=None):
    request = httpx.Request("POST", "http://ollama/api/chat")
    if content is not None:
        return httpx.Response(status, request=request, content=content)
    return httpx.Response(status, request=request, json=data)


def call_service(monkeypatch, profile, outcome):
    captured = {}
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient(outcome, captured),
    )
    service = OllamaService(Settings(ollama_url="http://ollama"))
    result = asyncio.run(service.chat([{"role": "user", "content": "hi"}], profile))
    return result, captured


def test_baseline_payload_applies_effective_service_context(monkeypatch):
    result, captured = call_service(
        monkeypatch,
        apply_service_context(resolve_profile("baseline"), 4096)[0],
        response({"message": {"content": " ok "}}),
    )
    assert result.content == "ok"
    assert captured["payload"] == {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096},
    }


def test_optimized_payload_defaults_and_overrides(monkeypatch):
    profile = resolve_profile(
        "optimized",
        temperature=0.7,
        max_tokens=1024,
        context_window=2048,
        thinking=True,
    )
    _, captured = call_service(
        monkeypatch, profile, response({"message": {"content": "ok"}})
    )
    payload = captured["payload"]
    assert payload["model"] == "qwen3-dev:8b"
    assert payload["think"] is True
    assert payload["messages"][0] == {
        "role": "system",
        "content": MODEL_PROFILES["optimized"].system_prompt,
    }
    assert payload["options"] == {
        "temperature": 0.7,
        "num_predict": 1024,
        "num_ctx": 2048,
        "top_p": 0.9,
        "repeat_penalty": 1.08,
    }

    _, default_capture = call_service(
        monkeypatch,
        resolve_profile("optimized"),
        response({"message": {"content": "ok"}}),
    )
    assert default_capture["payload"]["options"] == {
        "temperature": 0.2,
        "num_predict": 512,
        "num_ctx": 4096,
        "top_p": 0.9,
        "repeat_penalty": 1.08,
    }
    assert default_capture["payload"]["think"] is False


@pytest.mark.parametrize(
    ("outcome", "error_type"),
    [
        (
            httpx.ReadTimeout(
                "timeout", request=httpx.Request("POST", "http://ollama/api/chat")
            ),
            "timeout",
        ),
        (
            httpx.ConnectError(
                "network", request=httpx.Request("POST", "http://ollama/api/chat")
            ),
            "network_error",
        ),
        (response({"error": "bad"}, status=500), "http_error"),
        (response(content=b"not-json"), "parse_error"),
        (response({"message": {"content": " "}}), "empty_response"),
    ],
)
def test_stable_ollama_errors(monkeypatch, outcome, error_type):
    with pytest.raises(OllamaError) as caught:
        call_service(monkeypatch, resolve_profile("baseline"), outcome)
    assert caught.value.error_type == error_type
