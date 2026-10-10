from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import create_engine, inspect, text

from app.config.model_profiles import apply_service_context, resolve_profile
from app.database import initialize_database
from app.services.history import budget_history, budget_optimized_history
from app.services.metrics import build_metric


def test_metric_normalization_and_missing_values():
    metric = build_metric(
        chat_id=1,
        profile=resolve_profile("optimized"),
        messages=[
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "new"},
        ],
        request_started_at=datetime.now(timezone.utc),
        request_started_counter=perf_counter(),
        raw_response={
            "total_duration": 2_500_000,
            "prompt_eval_count": 10,
            "prompt_eval_duration": 2_000_000_000,
            "eval_count": 4,
            "eval_duration": 500_000_000,
        },
        success=True,
        context_budget=budget_history(
            [
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "answer"},
                {"role": "user", "content": "new"},
            ],
            resolve_profile("optimized"),
        ),
        authenticated_user_id=1,
        service_rate_limit=20,
        service_max_context=4096,
        profile_context=4096,
    )
    assert metric.ollama_total_duration_ms == 2.5
    assert metric.load_duration_ms is None
    assert metric.total_tokens == 14
    assert metric.prompt_tokens_per_second == 5
    assert metric.generation_tokens_per_second == 8
    assert metric.history_messages_count == 2
    assert metric.history_chars == 9
    assert metric.user_prompt_chars == 3
    assert metric.request_started_at.tzinfo == timezone.utc
    assert "load_duration" not in metric.metrics_json


def test_optimized_budget_keeps_latest_complete_turns_and_latest_user():
    profile = resolve_profile("optimized", max_tokens=1024, context_window=2048)
    messages = [
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "c" * 400},
        {"role": "assistant", "content": "d" * 400},
        {"role": "user", "content": "latest"},
    ]
    trimmed = budget_optimized_history(messages, profile)
    assert trimmed == messages[-3:]
    baseline, _ = apply_service_context(resolve_profile("baseline"), 4096)
    assert budget_optimized_history(messages, baseline) == messages


def test_old_sqlite_database_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE chats (id INTEGER PRIMARY KEY, title VARCHAR(80), "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE messages (id INTEGER PRIMARY KEY, chat_id INTEGER, "
                "role VARCHAR(16), content TEXT, created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO messages (id, chat_id, role, content) "
                "VALUES (1, 1, 'user', 'preserved')"
            )
        )
    initialize_database(engine)
    inspector = inspect(engine)
    assert "comparison_id" in {
        column["name"] for column in inspector.get_columns("messages")
    }
    assert "message_metrics" in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT content FROM messages WHERE id = 1")) == "preserved"
