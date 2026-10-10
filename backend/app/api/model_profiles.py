from fastapi import APIRouter

from app.config.model_profiles import profile_metadata

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/model-profiles")
def list_model_profiles() -> dict:
    return profile_metadata()
