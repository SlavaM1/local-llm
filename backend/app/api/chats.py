import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Chat, Message, utc_now
from app.schemas import ChatCreate, ChatRead, MessageCreate, MessageExchange, MessageRead
from app.services.ollama import OllamaError, OllamaService

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
) -> MessageExchange:
    async with chat_locks[chat_id]:
        return await process_message(chat_id, payload, db)


async def process_message(
    chat_id: int,
    payload: MessageCreate,
    db: Session,
) -> MessageExchange:
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
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not persist user message for chat %s", chat_id)
        raise HTTPException(status_code=500, detail="Не удалось сохранить сообщение.") from exc

    history = list(
        db.scalars(select(Message).where(Message.chat_id == chat_id).order_by(Message.id))
    )
    ollama_messages = [
        {"role": message.role, "content": message.content} for message in history
    ]

    service = OllamaService(get_settings())
    try:
        answer = await service.chat(ollama_messages)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    assistant_message = Message(chat_id=chat_id, role="assistant", content=answer)
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
