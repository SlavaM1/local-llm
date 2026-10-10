from sqlalchemy.orm import Session

from app.models import ServiceSettings


DEFAULT_REQUESTS_PER_MINUTE = 20
DEFAULT_MAX_CONTEXT_TOKENS = 4096


def get_service_settings(db: Session) -> ServiceSettings:
    settings = db.get(ServiceSettings, 1)
    if settings is None:
        settings = ServiceSettings(
            id=1,
            requests_per_minute=DEFAULT_REQUESTS_PER_MINUTE,
            max_context_tokens=DEFAULT_MAX_CONTEXT_TOKENS,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
