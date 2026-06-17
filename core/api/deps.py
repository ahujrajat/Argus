# core/api/deps.py
from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.session import get_session as _get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session() as session:
        yield session
