from app.services.ollama import OllamaError


def create_chat(client):
    response = client.post("/api/chats", json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_profiles_and_request_validation(api):
    client, _, _ = api
    profiles = client.get("/api/model-profiles")
    assert profiles.status_code == 200
    assert [item["id"] for item in profiles.json()["profiles"]] == [
        "baseline",
        "optimized",
    ]
    chat_id = create_chat(client)
    assert client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "x", "profile": "unknown"},
    ).status_code == 422
    assert client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "x", "profile": "baseline", "settings": {}},
    ).status_code == 422
    assert client.post(
        f"/api/chats/{chat_id}/messages",
        json={
            "content": "x",
            "profile": "optimized",
            "settings": {"temperature": 1.1},
        },
    ).status_code == 422
    assert client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "x", "model": "other"},
    ).status_code == 422


def test_metrics_persist_and_are_listed(api):
    client, fake, _ = api
    chat_id = create_chat(client)
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        json={
            "content": "hello",
            "profile": "optimized",
            "settings": {"temperature": 0.4, "max_tokens": 256},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user_message"]["metrics"] is None
    metrics = body["assistant_message"]["metrics"]
    assert metrics["profile"] == "optimized"
    assert metrics["temperature"] == 0.4
    assert metrics["max_tokens"] == 256
    assert metrics["ollama_total_duration_ms"] == 2000
    assert metrics["input_tokens"] == 20
    assert metrics["output_tokens"] == 10
    listed = client.get(f"/api/chats/{chat_id}/messages").json()
    assert listed[1]["metrics"]["id"] == metrics["id"]
    assert fake.calls[0][1].temperature == 0.4


def test_compare_is_sequential_fair_and_excluded_from_future_context(api):
    client, fake, _ = api
    fake.responses = ["ordinary", "baseline", "optimized", "after"]
    chat_id = create_chat(client)
    assert client.post(
        f"/api/chats/{chat_id}/messages", json={"content": "first"}
    ).status_code == 201
    response = client.post(
        f"/api/chats/{chat_id}/compare",
        json={"content": "experiment", "optimized_settings": {"max_tokens": 256}},
    )
    assert response.status_code == 201
    body = response.json()
    comparison_id = body["user_message"]["comparison_id"]
    assert comparison_id
    assert body["baseline_message"]["comparison_id"] == comparison_id
    assert body["optimized_message"]["comparison_id"] == comparison_id
    baseline_messages = fake.calls[1][0]
    optimized_messages = fake.calls[2][0]
    assert [fake.calls[1][1].name, fake.calls[2][1].name] == [
        "baseline",
        "optimized",
    ]
    assert baseline_messages == optimized_messages
    assert all(message["content"] != "baseline" for message in optimized_messages)

    assert client.post(
        f"/api/chats/{chat_id}/messages", json={"content": "after"}
    ).status_code == 201
    future_messages = fake.calls[3][0]
    assert [message["content"] for message in future_messages] == [
        "first",
        "ordinary",
        "after",
    ]
    assert len(client.get(f"/api/chats/{chat_id}/messages").json()) == 7


def test_failed_attempt_persists_metric_and_returns_503(api):
    client, fake, session_factory = api
    fake.responses = [OllamaError("timeout", "timeout")]
    chat_id = create_chat(client)
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": "hello"})
    assert response.status_code == 503
    with session_factory() as session:
        from app.models import MessageMetric

        metric = session.query(MessageMetric).one()
        assert metric.success is False
        assert metric.error_type == "timeout"
        assert metric.message_id is None
