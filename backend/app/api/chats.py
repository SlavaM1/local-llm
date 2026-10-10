import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.config.model_profiles import ResolvedProfile, apply_service_context, resolve_profile
from app.database import get_db
from app.models import Chat, Message, MessageMetric, User, utc_now
from app.schemas import (
    ChatCreate,
    ChatRead,
    CompareCreate,
    ComparisonExchange,
    MessageCreate,
    MessageExchange,
    MessageRead,
    OptimizedSettings,
)
from app.services.history import ContextBudget, budget_history
from app.services.metrics import build_metric
from app.services.ollama import OllamaError, OllamaResult, OllamaService
from app.services.rate_limit import generation_limiter
from app.services.security import current_user
from app.services.settings import get_service_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chats"])
chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def get_ollama_service() -> OllamaService:
    return OllamaService(get_settings())


def find_chat_or_404(chat_id: int, user_id: int, db: Session) -> Chat:
    chat = db.scalar(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
    if chat is None:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
    return chat


def make_title(content: str, max_length: int = 44) -> str:
    one_line = " ".join(content.split())
    if len(one_line) <= max_length:
        return one_line
    return f"{one_line[: max_length - 3].rstrip()}..."


def ordinary_history(chat_id: int, db: Session) -> list[dict[str, str]]:
    statement = (
        select(Message)
        .where(Message.chat_id == chat_id, Message.comparison_id.is_(None))
        .order_by(Message.id)
    )
    return [
        {"role": message.role, "content": message.content}
        for message in db.scalars(statement)
    ]


def prepare_messages(
    messages: list[dict[str, str]], profile: ResolvedProfile
) -> ContextBudget:
    return budget_history(messages, profile)


async def generate(
    service: OllamaService,
    chat_id: int,
    profile: ResolvedProfile,
    context_budget: ContextBudget,
    authenticated_user_id: int,
    service_rate_limit: int,
    service_max_context: int,
    profile_context: int,
) -> tuple[OllamaResult | None, MessageMetric, OllamaError | None]:
    started_at = datetime.now(timezone.utc)
    started_counter = perf_counter()
    try:
        result = await service.chat(context_budget.messages, profile)
    except OllamaError as exc:
        metric = build_metric(
            chat_id=chat_id,
            profile=profile,
            messages=context_budget.messages,
            request_started_at=started_at,
            request_started_counter=started_counter,
            raw_response=None,
            success=False,
            error_type=exc.error_type,
            context_budget=context_budget,
            authenticated_user_id=authenticated_user_id,
            service_rate_limit=service_rate_limit,
            service_max_context=service_max_context,
            profile_context=profile_context,
        )
        return None, metric, exc
    metric = build_metric(
        chat_id=chat_id,
        profile=profile,
        messages=context_budget.messages,
        request_started_at=started_at,
        request_started_counter=started_counter,
        raw_response=result.raw_response,
        success=True,
        context_budget=context_budget,
        authenticated_user_id=authenticated_user_id,
        service_rate_limit=service_rate_limit,
        service_max_context=service_max_context,
        profile_context=profile_context,
    )
    return result, metric, None


def persist_failed_metric(db: Session, metric: MessageMetric) -> None:
    try:
        db.add(metric)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not persist failed Ollama attempt")
        raise HTTPException(status_code=500, detail="Не удалось сохранить метрики.") from exc


def raise_unavailable(error: OllamaError) -> None:
    raise HTTPException(status_code=503, detail=str(error)) from error


def enforce_generation_limit(user: User, requests_per_minute: int, *, cost: int = 1) -> None:
    retry_after = generation_limiter.check(
        f"user:{user.id}", requests_per_minute, cost=cost
    )
    if retry_after is not None:
        logger.info("Generation rate limit rejected for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


@router.get("", response_model=list[ChatRead])
def list_chats(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Chat]:
    return list(
        db.scalars(
            select(Chat).where(Chat.user_id == user.id).order_by(Chat.updated_at.desc(), Chat.id.desc())
        )
    )


@router.post("", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_chat(
    _payload: ChatCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Chat:
    chat = Chat(user_id=user.id)
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
def get_chat(chat_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Chat:
    return find_chat_or_404(chat_id, user.id, db)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Response:
    async with chat_locks[chat_id]:
        chat = find_chat_or_404(chat_id, user.id, db)
        try:
            db.delete(chat)
            db.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Could not delete chat %s", chat_id)
            raise HTTPException(status_code=500, detail="Не удалось удалить диалог.") from exc


@router.get("/{chat_id}/messages", response_model=list[MessageRead])
def list_messages(
    chat_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[Message]:
    find_chat_or_404(chat_id, user.id, db)
    statement = select(Message).where(Message.chat_id == chat_id).order_by(Message.id)
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
    service: OllamaService = Depends(get_ollama_service),
    user: User = Depends(current_user),
) -> MessageExchange:
    request_started = perf_counter()
    service_settings = get_service_settings(db)
    enforce_generation_limit(user, service_settings.requests_per_minute)
    async with chat_locks[chat_id]:
        exchange = await process_message(chat_id, payload, db, service, user, service_settings)
    logger.info(
        "[chat=%s] response ready in %.3fs", chat_id, perf_counter() - request_started
    )
    return exchange


async def process_message(
    chat_id: int,
    payload: MessageCreate,
    db: Session,
    service: OllamaService,
    user: User,
    service_settings,
) -> MessageExchange:
    chat = find_chat_or_404(chat_id, user.id, db)
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
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not persist user message for chat %s", chat_id)
        raise HTTPException(status_code=500, detail="Не удалось сохранить сообщение.") from exc

    resolved_profile = payload.resolved_profile()
    profile, profile_context = apply_service_context(
        resolved_profile, service_settings.max_context_tokens
    )
    context_budget = prepare_messages(ordinary_history(chat_id, db), profile)
    db.commit()  # End the implicit read transaction before model generation.
    result, metric, error = await generate(
        service,
        chat_id,
        profile,
        context_budget,
        user.id,
        service_settings.requests_per_minute,
        service_settings.max_context_tokens,
        profile_context,
    )
    if error is not None:
        persist_failed_metric(db, metric)
        raise_unavailable(error)
    assert result is not None

    assistant_message = Message(chat_id=chat_id, role="assistant", content=result.content)
    assistant_message.metrics = metric
    chat.updated_at = utc_now()
    try:
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        db.refresh(chat)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not persist assistant response for chat %s", chat_id)
        raise HTTPException(status_code=500, detail="Не удалось сохранить ответ модели.") from exc

    return MessageExchange(
        user_message=MessageRead.model_validate(user_message),
        assistant_message=MessageRead.model_validate(assistant_message),
        chat=ChatRead.model_validate(chat),
    )


@router.post(
    "/{chat_id}/compare",
    response_model=ComparisonExchange,
    status_code=status.HTTP_201_CREATED,
)
async def compare_profiles(
    chat_id: int,
    payload: CompareCreate,
    db: Session = Depends(get_db),
    service: OllamaService = Depends(get_ollama_service),
    user: User = Depends(current_user),
) -> ComparisonExchange:
    service_settings = get_service_settings(db)
    enforce_generation_limit(user, service_settings.requests_per_minute, cost=2)
    async with chat_locks[chat_id]:
        return await process_comparison(chat_id, payload, db, service, user, service_settings)


async def process_comparison(
    chat_id: int,
    payload: CompareCreate,
    db: Session,
    service: OllamaService,
    user: User,
    service_settings,
) -> ComparisonExchange:
    chat = find_chat_or_404(chat_id, user.id, db)
    history_snapshot = ordinary_history(chat_id, db)
    had_user_messages = db.scalar(
        select(Message.id)
        .where(Message.chat_id == chat_id, Message.role == "user")
        .limit(1)
    )
    comparison_id = str(uuid4())
    user_message = Message(
        chat_id=chat_id,
        role="user",
        content=payload.content,
        comparison_id=comparison_id,
    )
    if had_user_messages is None:
        chat.title = make_title(payload.content)
    chat.updated_at = utc_now()
    try:
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not persist comparison message for chat %s", chat_id)
        raise HTTPException(status_code=500, detail="Не удалось сохранить сообщение.") from exc

    common_messages = [
        *history_snapshot,
        {"role": "user", "content": payload.content},
    ]
    baseline_profile, baseline_profile_context = apply_service_context(
        resolve_profile("baseline"), service_settings.max_context_tokens
    )
    optimized_profile, optimized_profile_context = apply_service_context(
        (payload.optimized_settings or OptimizedSettings()).resolve(),
        service_settings.max_context_tokens,
    )
    baseline_context_budget = prepare_messages(common_messages, baseline_profile)
    optimized_context_budget = prepare_messages(common_messages, optimized_profile)

    baseline_result, baseline_metric, baseline_error = await generate(
        service,
        chat_id,
        baseline_profile,
        baseline_context_budget,
        user.id,
        service_settings.requests_per_minute,
        service_settings.max_context_tokens,
        baseline_profile_context,
    )
    if baseline_error is not None:
        persist_failed_metric(db, baseline_metric)
        raise_unavailable(baseline_error)
    assert baseline_result is not None

    optimized_result, optimized_metric, optimized_error = await generate(
        service,
        chat_id,
        optimized_profile,
        optimized_context_budget,
        user.id,
        service_settings.requests_per_minute,
        service_settings.max_context_tokens,
        optimized_profile_context,
    )
    if optimized_error is not None:
        baseline_message = Message(
            chat_id=chat_id,
            role="assistant",
            content=baseline_result.content,
            comparison_id=comparison_id,
            metrics=baseline_metric,
        )
        try:
            db.add_all([baseline_message, optimized_metric])
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Could not persist comparison failure")
            raise HTTPException(status_code=500, detail="Не удалось сохранить метрики.") from exc
        raise_unavailable(optimized_error)
    assert optimized_result is not None

    baseline_message = Message(
        chat_id=chat_id,
        role="assistant",
        content=baseline_result.content,
        comparison_id=comparison_id,
        metrics=baseline_metric,
    )
    optimized_message = Message(
        chat_id=chat_id,
        role="assistant",
        content=optimized_result.content,
        comparison_id=comparison_id,
        metrics=optimized_metric,
    )
    chat.updated_at = utc_now()
    try:
        db.add_all([baseline_message, optimized_message])
        db.commit()
        db.refresh(baseline_message)
        db.refresh(optimized_message)
        db.refresh(chat)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not persist comparison responses")
        raise HTTPException(status_code=500, detail="Не удалось сохранить ответы моделей.") from exc

    return ComparisonExchange(
        chat=ChatRead.model_validate(chat),
        user_message=MessageRead.model_validate(user_message),
        baseline_message=MessageRead.model_validate(baseline_message),
        optimized_message=MessageRead.model_validate(optimized_message),
    )
