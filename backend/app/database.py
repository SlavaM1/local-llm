from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

if settings.database_url.startswith("sqlite:////"):
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database(target_engine: Engine = engine) -> None:
    # Import registers all model tables before create_all is evaluated.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=target_engine)
    if target_engine.dialect.name != "sqlite":
        return

    inspector = inspect(target_engine)
    if "messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("messages")}
    chat_columns = {column["name"] for column in inspector.get_columns("chats")}
    metric_columns = (
        {column["name"] for column in inspector.get_columns("message_metrics")}
        if "message_metrics" in inspector.get_table_names()
        else set()
    )
    with target_engine.begin() as connection:
        if "comparison_id" not in columns:
            connection.execute(
                text("ALTER TABLE messages ADD COLUMN comparison_id VARCHAR(36)")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_messages_comparison_id "
                "ON messages (comparison_id)"
            )
        )
        if "user_id" not in chat_columns:
            connection.execute(text("ALTER TABLE chats ADD COLUMN user_id INTEGER"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_chats_user_id ON chats (user_id)"))
        metric_migrations = {
            "authenticated_user_id": "INTEGER",
            "service_rate_limit": "INTEGER",
            "service_max_context": "INTEGER",
            "profile_context": "INTEGER",
            "effective_context": "INTEGER",
            "history_messages_available": "INTEGER",
            "history_messages_sent": "INTEGER",
            "history_messages_dropped": "INTEGER",
        }
        for name, sql_type in metric_migrations.items():
            if name not in metric_columns:
                connection.execute(text(f"ALTER TABLE message_metrics ADD COLUMN {name} {sql_type}"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_message_metrics_authenticated_user_id "
                "ON message_metrics (authenticated_user_id)"
            )
        )

    # The initial account is seeded once; existing local Day 29 chats become its data.
    from app.models import Chat, ServiceSettings, User
    from app.services.security import hash_password
    from app.services.settings import DEFAULT_MAX_CONTEXT_TOKENS, DEFAULT_REQUESTS_PER_MINUTE

    factory = sessionmaker(bind=target_engine, expire_on_commit=False)
    with factory() as db:
        admin = db.query(User).filter(User.username == settings.initial_admin_username).one_or_none()
        if admin is None:
            admin = User(
                username=settings.initial_admin_username,
                password_hash=hash_password(settings.initial_admin_password),
                is_admin=True,
            )
            db.add(admin)
            db.flush()
        if db.get(ServiceSettings, 1) is None:
            db.add(
                ServiceSettings(
                    id=1,
                    requests_per_minute=DEFAULT_REQUESTS_PER_MINUTE,
                    max_context_tokens=DEFAULT_MAX_CONTEXT_TOKENS,
                )
            )
        db.query(Chat).filter(Chat.user_id.is_(None)).update({Chat.user_id: admin.id})
        db.commit()
