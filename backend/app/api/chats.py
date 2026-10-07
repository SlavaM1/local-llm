import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Chat, Message, MessageMetadata, utc_now
from app.schemas import ChatCreate, ChatRead, MessageCreate, MessageExchange, MessageRead
from app.services.ollama import OllamaError, OllamaService
from app.services.rag import RAGService, RAGServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chats"])
chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def find_chat_or_404(chat_id: int, db: Session) -> Chat:
    chat = db.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
    return chat


def make_title(content: str, max_length: int = 44) -> str:
    one_line = " ".join(content.split())
    if len(one_line) <= max_length:
        return one_line
    return f"{one_line[: max_length - 3].rstrip()}..."


@router.get("", response_model=list[ChatRead])
def list_chats(db: Session = Depends(get_db)) -> list[Chat]:
    return list(db.scalars(select(Chat).order_by(Chat.updated_at.desc(), Chat.id.desc())))


@router.post("", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_chat(_payload: ChatCreate, db: Session = Depends(get_db)) -> Chat:
    chat = Chat()
    try:
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not create chat")
        raise HTTPException(status_code=500, detail="Не удалось создать диалог.") from exc


@router.get("/{chat_id}", response_model=ChatRead)
def get_chat(chat_id: int, db: Session = Depends(get_db)) -> Chat:
    return find_chat_or_404(chat_id, db)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: int, db: Session = Depends(get_db)) -> Response:
    async with chat_locks[chat_id]:
        chat = find_chat_or_404(chat_id, db)
        try:
            db.delete(chat)
            db.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Could not delete chat %s", chat_id)
            raise HTTPException(status_code=500, detail="Не удалось удалить диалог.") from exc


@router.get("/{chat_id}/messages", response_model=list[MessageRead])
def list_messages(chat_id: int, db: Session = Depends(get_db)) -> list[Message]:
    find_chat_or_404(chat_id, db)
    statement = (
        select(Message)
        .options(selectinload(Message.generation_metadata))
        .where(Message.chat_id == chat_id)
        .order_by(Message.id)
    )
    return list(db.scalars(statement))


@router.post(
    "/{chat_id}/messages",
    response_model=MessageExchange,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    chat_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> MessageExchange:
    request_started = perf_counter()
    request_id = str(uuid4())
    logger.info(
        "generation_start request_id=%s chat_id=%s provider=%s rag_enabled=%s",
        request_id,
        chat_id,
        payload.provider,
        payload.rag_enabled,
    )
    async with chat_locks[chat_id]:
        exchange = await process_message(chat_id, payload, db, request_started, request_id)
    logger.info(
        "generation_complete request_id=%s chat_id=%s status=%s duration_ms=%.2f",
        request_id,
        chat_id,
        exchange.assistant_message.status,
        (perf_counter() - request_started) * 1000,
    )
    return exchange


async def process_message(
    chat_id: int,
    payload: MessageCreate,
    db: Session,
    request_started: float,
    request_id: str,
) -> MessageExchange:
    request_started_at = datetime.now(timezone.utc).isoformat()
    chat = find_chat_or_404(chat_id, db)
    had_user_messages = db.scalar(
        select(Message.id)
        .where(Message.chat_id == chat_id, Message.role == "user")
        .limit(1)
    )
    user_message = Message(chat_id=chat_id, role="user", content=payload.content)
    if had_user_messages is None:
        chat.title = make_title(payload.content)
    chat.updated_at = utc_now()

    try:
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
        logger.info(
            "user_message_persisted request_id=%s chat_id=%s duration_ms=%.2f",
            request_id,
            chat_id,
            (perf_counter() - request_started) * 1000,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "Could not persist user message request_id=%s chat_id=%s", request_id, chat_id
        )
        raise HTTPException(status_code=500, detail="Не удалось сохранить сообщение.") from exc

    history = list(
        db.scalars(select(Message).where(Message.chat_id == chat_id).order_by(Message.id))
    )
    all_messages = [
        {"role": message.role, "content": message.content} for message in history
    ]
    prior_messages = [
        {"role": message.role, "content": message.content}
        for message in history
        if message.id != user_message.id
    ]
    total_chars = sum(len(message["content"]) for message in all_messages)
    logger.info(
        "history_loaded request_id=%s chat_id=%s messages=%s chars=%s duration_ms=%.2f",
        request_id,
        chat_id,
        len(all_messages),
        total_chars,
        (perf_counter() - request_started) * 1000,
    )

    # End the implicit read transaction before waiting for model generation.
    db.commit()

    settings = get_settings()
    model = settings.ollama_model if payload.provider == "ollama" else "deepseek-flash"
    try:
        if payload.provider == "ollama" and not payload.rag_enabled:
            service = OllamaService(settings)
            logger.info(
                "generation_route request_id=%s route=direct_ollama model=%s",
                request_id,
                model,
            )
            result = await service.chat(all_messages)
            metrics = {
                "request_started_at": request_started_at,
                "success": True,
                "http_status": 200,
                "error_type": None,
                "provider": payload.provider,
                "model": result.model,
                "request_id": request_id,
                "rag_enabled": False,
                "retrieval_mode": None,
                "strategy": None,
                "history_messages_count": len(prior_messages),
                "history_chars": sum(len(message["content"]) for message in prior_messages),
                "rag_context_chars": 0,
                "rag_context_chunks": 0,
                "retrieved_chunks_count": 0,
                "source_count": 0,
                "quote_count": 0,
                "retrieval_total_ms": None,
                "query_rewrite_ms": None,
                "embedding_ms": None,
                "faiss_search_ms": None,
                "filter_ms": None,
                "rerank_ms": None,
                "context_build_ms": None,
                "candidate_top_k": None,
                "candidate_count": 0,
                "filtered_count": 0,
                "final_top_k": None,
                "final_chunk_count": 0,
                "best_similarity": None,
                "similarity_threshold": None,
                "rerank_enabled": False,
                **result.metrics,
                "tokens_per_second": result.metrics.get("generation_tokens_per_second"),
            }
            answer = result.answer
            model = result.model
            result_status = "answered"
            sources: list[object] = []
            quotes: list[object] = []
        else:
            logger.info(
                "generation_route request_id=%s route=rag_service provider=%s model=%s rag_enabled=%s",
                request_id,
                payload.provider,
                model,
                payload.rag_enabled,
            )
            result = await RAGService(settings).chat(
                request_id=request_id,
                provider=payload.provider,
                model=model,
                rag_enabled=payload.rag_enabled,
                messages=prior_messages,
                question=payload.content,
            )
            answer = result.answer
            model = result.model
            result_status = result.status
            metrics = result.metrics
            sources = result.sources
            quotes = result.quotes
    except OllamaError as exc:
        logger.warning(
            "generation_error request_id=%s chat_id=%s status=ollama_error", request_id, chat_id
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RAGServiceError as exc:
        logger.warning(
            "generation_error request_id=%s chat_id=%s status=rag_error http_status=%s",
            request_id,
            chat_id,
            exc.status_code,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    upstream_latency_ms = metrics.get("total_latency_ms")
    metrics["upstream_total_latency_ms"] = upstream_latency_ms
    metrics["total_latency_ms"] = round((perf_counter() - request_started) * 1000, 2)
    assistant_message = Message(chat_id=chat_id, role="assistant", content=answer)
    logger.info(
        "generation_metrics request_id=%s provider=%s model=%s rag_enabled=%s "
        "llm_latency_ms=%s input_tokens=%s output_tokens=%s",
        request_id,
        payload.provider,
        model,
        payload.rag_enabled,
        metrics.get("llm_latency_ms"),
        metrics.get("input_tokens"),
        metrics.get("output_tokens"),
    )
    assistant_message.generation_metadata = MessageMetadata(
        request_id=request_id,
        provider=payload.provider,
        model=model,
        rag_enabled=payload.rag_enabled,
        status=result_status,
        metrics_json=json.dumps(metrics, ensure_ascii=False),
        sources_json=json.dumps(sources, ensure_ascii=False),
        quotes_json=json.dumps(quotes, ensure_ascii=False),
    )
    chat.updated_at = utc_now()
    try:
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        db.refresh(chat)
        logger.info(
            "assistant_message_persisted request_id=%s chat_id=%s duration_ms=%.2f",
            request_id,
            chat_id,
            (perf_counter() - request_started) * 1000,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "Could not persist assistant response request_id=%s chat_id=%s",
            request_id,
            chat_id,
        )
        raise HTTPException(status_code=500, detail="Не удалось сохранить ответ модели.") from exc

    return MessageExchange(
        user_message=MessageRead.model_validate(user_message),
        assistant_message=MessageRead.model_validate(assistant_message),
        chat=ChatRead.model_validate(chat),
    )
