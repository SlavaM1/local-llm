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
