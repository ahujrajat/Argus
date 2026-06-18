# core/auth/keys.py
from __future__ import annotations
import hashlib
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import ApiKeyRow

_bearer = HTTPBearer(auto_error=False)

_ARGUS_MASTER_KEY = os.environ.get("ARGUS_MASTER_KEY", "")


def generate_key() -> tuple[str, str]:
    """Return (raw_key, hashed_key). Store only the hash."""
    raw = "argus_" + secrets.token_urlsafe(32)
    hashed = _hash(raw)
    return raw, hashed


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyRow:
    """FastAPI dependency — validates Bearer token against ApiKeyRow table."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw = credentials.credentials

    # Allow master key bypass (for bootstrapping)
    if _ARGUS_MASTER_KEY and raw == _ARGUS_MASTER_KEY:
        return ApiKeyRow(id="master", name="master", key_hash="master", created_by="env")

    hashed = _hash(raw)
    result = await db.execute(
        select(ApiKeyRow).where(ApiKeyRow.key_hash == hashed, ApiKeyRow.revoked == False)  # noqa: E712
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if row.expires_at and row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return row


def optional_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str | None:
    """Return the raw token if present, None otherwise. Does not hit the DB."""
    return credentials.credentials if credentials else None
