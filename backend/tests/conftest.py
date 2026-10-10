import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/local-llm-day29-tests.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chats import get_ollama_service
from app.database import Base, get_db, initialize_database
from app.main import app
from app.services.ollama import OllamaResult


class FakeOllama:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    async def chat(self, messages, profile):
        self.calls.append((messages, profile))
        response = self.responses.pop(0) if self.responses else f"answer-{profile.name}"
        if isinstance(response, Exception):
            raise response
        return OllamaResult(
            content=response,
            raw_response={
                "total_duration": 2_000_000_000,
                "load_duration": 100_000_000,
                "prompt_eval_count": 20,
                "prompt_eval_duration": 1_000_000_000,
                "eval_count": 10,
                "eval_duration": 500_000_000,
            },
        )


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_database(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeOllama()

    def override_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ollama_service] = lambda: fake
    with TestClient(app) as client:
        yield client, fake, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(api):
    _, _, session_factory = api
    with session_factory() as session:
        yield session
