import bcrypt

from app.models import ServiceSettings, User


def create_chat(client):
    response = client.post("/api/chats", json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_seeded_admin_is_hashed_and_login_session_protects_endpoints(api):
    client, _, session_factory = api
    with session_factory() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        assert admin.password_hash != "admin1"
        assert bcrypt.checkpw(b"admin1", admin.password_hash.encode())

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/chats").status_code == 401
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    ).status_code == 401
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin1"})
    assert login.status_code == 200
    assert login.json() == {"username": "admin"}
    assert "httponly" in login.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json() == {"username": "admin"}
    assert client.get("/api/chats").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/chats").status_code == 401


def test_settings_validation_persistence_and_context_propagation(api):
    client, fake, session_factory = api
    assert client.put("/api/settings", json={"requests_per_minute": 0, "max_context_tokens": 4096}).status_code == 422
    assert client.put("/api/settings", json={"requests_per_minute": 20, "max_context_tokens": 9999}).status_code == 422
    updated = client.put(
        "/api/settings", json={"requests_per_minute": 10, "max_context_tokens": 2048}
    )
    assert updated.status_code == 200
    assert updated.json() == {"requests_per_minute": 10, "max_context_tokens": 2048}
    with session_factory() as db:
        assert db.get(ServiceSettings, 1).max_context_tokens == 2048

    chat_id = create_chat(client)
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "context", "profile": "optimized", "settings": {"context_window": 4096}},
    )
    assert response.status_code == 201
    assert fake.calls[-1][1].context_window == 2048
    metrics = response.json()["assistant_message"]["metrics"]
    assert metrics["profile_context"] == 4096
    assert metrics["service_max_context"] == 2048
    assert metrics["effective_context"] == 2048


def test_generation_rate_limit_returns_retry_after(api):
    client, _, _ = api
    assert client.put(
        "/api/settings", json={"requests_per_minute": 3, "max_context_tokens": 4096}
    ).status_code == 200
    chat_id = create_chat(client)
    for number in range(3):
        assert client.post(
            f"/api/chats/{chat_id}/messages", json={"content": f"message {number}"}
        ).status_code == 201
    rejected = client.post(f"/api/chats/{chat_id}/messages", json={"content": "too many"})
    assert rejected.status_code == 429
    assert rejected.json()["detail"] == "Rate limit exceeded"
    assert int(rejected.headers["retry-after"]) >= 1
