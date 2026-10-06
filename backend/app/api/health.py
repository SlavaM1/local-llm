from fastapi import APIRouter, Response, status

from app.config import get_settings
from app.schemas import HealthRead
from app.services.ollama import OllamaService

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthRead)
async def health(response: Response) -> HealthRead:
    settings = get_settings()
    ollama_available = await OllamaService(settings).is_available()
    if not ollama_available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthRead(
        status="ok" if ollama_available else "degraded",
        ollama="available" if ollama_available else "unavailable",
        model=settings.ollama_model,
    )
