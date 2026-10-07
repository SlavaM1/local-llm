import asyncio

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas import HealthRead
from app.services.ollama import OllamaService
from app.services.rag import RAGService

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthRead)
async def health(response: Response, db: Session = Depends(get_db)) -> HealthRead:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database_available = True
    except SQLAlchemyError:
        database_available = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    ollama_result, rag_result = await asyncio.gather(
        OllamaService(settings).is_available(),
        RAGService(settings).health(),
        return_exceptions=True,
    )
    ollama_available = ollama_result is True
    rag_available, deepseek_configured = (
        rag_result if isinstance(rag_result, tuple) else (False, False)
    )
    return HealthRead(
        status=(
            "ok"
            if database_available and ollama_available and rag_available and deepseek_configured
            else "degraded"
        ),
        backend="ok" if database_available else "unavailable",
        ollama="available" if ollama_available else "unavailable",
        rag="available" if rag_available else "unavailable",
        deepseek_configured=deepseek_configured,
        model=settings.ollama_model,
    )
