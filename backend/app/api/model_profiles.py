from fastapi import APIRouter, Depends

from app.config.model_profiles import profile_metadata
from app.models import User
from app.services.security import current_user

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/model-profiles")
def list_model_profiles(_user: User = Depends(current_user)) -> dict:
    return profile_metadata()
