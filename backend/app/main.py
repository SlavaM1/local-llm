import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.chats import router as chats_router
from app.api.health import router as health_router
from app.config import get_settings
from app.database import Base, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
app.include_router(chats_router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled database error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Ошибка локальной базы данных."})


@app.on_event("startup")
def create_database_tables() -> None:
    Base.metadata.create_all(bind=engine)
