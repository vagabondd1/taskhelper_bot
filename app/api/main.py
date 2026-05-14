from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session_factory
from app.db.models import (
    Attempt,
    Message,
    MessageRole,
    Session as DbSession,
    SessionStatus,
    User,
)
from app.db.uow import UnitOfWork


app = FastAPI(title="TaskHelper API", version="1.0")


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


# ---------- Схемы ----------

class UserOut(BaseModel):
    id: int
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    created_at: datetime
    active_session_id: Optional[int] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    telegram_user_id: int = Field(..., gt=0)
    username: Optional[str] = None
    first_name: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: MessageRole
    message_text: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessagesPage(BaseModel):
    count: int
    list: list[MessageOut]


class SessionOut(BaseModel):
    id: int
    user_id: int
    current_task_text: Optional[str] = None
    current_mode: str
    status: str
    current_step_index: int
    total_steps: Optional[int] = None
    plan_steps: Optional[list[str]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Endpoints ----------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/users/{telegram_id}", response_model=UserOut)
async def get_user(telegram_id: int, db: AsyncSession = Depends(get_db)) -> UserOut:
    uow = UnitOfWork(db)
    user = await uow.users.get_by_telegram_id(telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    active = await uow.sessions.get_active_by_user_id(user.id)
    out = UserOut.model_validate(user)
    out.active_session_id = active.id if active else None
    return out


@app.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> UserOut:
    uow = UnitOfWork(db)
    # Берём тот же advisory lock, что и бот — иначе одновременный апсёрт
    # от пользователя из Telegram даст двух юзеров с одинаковым tg_id.
    await uow.lock_user(payload.telegram_user_id)

    existing = await uow.users.get_by_telegram_id(payload.telegram_user_id)
    if existing is not None:
        await uow.rollback()
        raise HTTPException(status_code=409, detail="user already exists")

    user = await uow.users.create(
        telegram_user_id=payload.telegram_user_id,
        username=payload.username,
        first_name=payload.first_name,
    )
    await uow.commit()
    return UserOut.model_validate(user)


@app.delete("/users/{telegram_id}", status_code=204)
async def delete_user(telegram_id: int, db: AsyncSession = Depends(get_db)) -> None:
    uow = UnitOfWork(db)
    await uow.lock_user(telegram_id)

    user = await uow.users.get_by_telegram_id(telegram_id)
    if user is None:
        await uow.rollback()
        raise HTTPException(status_code=404, detail="user not found")

    # FK без ON DELETE CASCADE — чистим вручную от детей к корню.
    await db.execute(delete(Attempt).where(Attempt.user_id == user.id))
    await db.execute(delete(Message).where(Message.user_id == user.id))
    await db.execute(delete(DbSession).where(DbSession.user_id == user.id))
    await db.delete(user)
    await uow.commit()


@app.get("/users/{telegram_id}/messages", response_model=MessagesPage)
async def get_user_messages(
    telegram_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> MessagesPage:
    uow = UnitOfWork(db)
    user = await uow.users.get_by_telegram_id(telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    result = await db.execute(
        select(Message)
        .where(Message.user_id == user.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [MessageOut.model_validate(m) for m in result.scalars().all()]
    return MessagesPage(count=len(items), list=items)


@app.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)) -> SessionOut:
    uow = UnitOfWork(db)
    s = await uow.sessions.get_by_id(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionOut.model_validate(s)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)) -> None:
    uow = UnitOfWork(db)
    s = await uow.sessions.get_by_id(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Lock по владельцу — чтобы не пересечься с обработчиком апдейта бота.
    owner = await db.execute(select(User).where(User.id == s.user_id))
    owner_row = owner.scalar_one_or_none()
    if owner_row is not None:
        await uow.lock_user(owner_row.telegram_user_id)

    # Перечитываем после lock — за время ожидания статус мог измениться.
    s = await uow.sessions.get_by_id(session_id)
    if s is not None and s.status != SessionStatus.completed:
        s.status = SessionStatus.completed
    await uow.commit()
