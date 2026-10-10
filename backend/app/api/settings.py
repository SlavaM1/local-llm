import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import ServiceSettingsRead, ServiceSettingsUpdate
from app.services.security import current_admin
from app.services.settings import get_service_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=ServiceSettingsRead)
def read_settings(
    db: Session = Depends(get_db), _user: User = Depends(current_admin)
) -> ServiceSettingsRead:
    return ServiceSettingsRead.model_validate(get_service_settings(db))


@router.put("", response_model=ServiceSettingsRead)
def update_settings(
    payload: ServiceSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_admin),
) -> ServiceSettingsRead:
    settings = get_service_settings(db)
    settings.requests_per_minute = payload.requests_per_minute
    settings.max_context_tokens = payload.max_context_tokens
    db.commit()
    db.refresh(settings)
    logger.info("Service settings updated by user_id=%s", user.id)
    return ServiceSettingsRead.model_validate(settings)
