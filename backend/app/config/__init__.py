from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Local LLM API"
    database_url: str = "sqlite:////app/data/chats.db"
    ollama_url: str = "http://ollama:11434"
    ollama_timeout_seconds: float = 600.0
    cors_origins: str = "http://localhost:3000"
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin1"
    session_cookie_name: str = "local_llm_session"
    session_lifetime_hours: int = 24
    session_cookie_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
