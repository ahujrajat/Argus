# tests/e2e/conftest.py
"""
E2E conftest: skips all e2e tests gracefully when PostgreSQL is not reachable.
"""
from __future__ import annotations
import asyncio
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end (deselect with -m 'not e2e')"
    )


def _check_db_sync() -> bool:
    """Synchronous connectivity check — runs before the async event loop is set up."""
    import socket

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://argus:argus@localhost:5432/argus",
    )
    # Parse host/port from the URL quickly with stdlib
    try:
        # URL form: postgresql+asyncpg://user:pass@host:port/db
        host_part = url.split("@", 1)[1].split("/")[0]
        host, port_str = host_part.rsplit(":", 1)
        port = int(port_str)
    except Exception:
        host, port = "localhost", 5432

    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


# Check DB reachability once at collection time
_DB_AVAILABLE = _check_db_sync()


def _maybe_skip_db():
    if not _DB_AVAILABLE:
        pytest.skip("PostgreSQL not reachable — skipping E2E test")


async def _ensure_schema() -> None:
    """Create all tables if they don't already exist (idempotent)."""
    from core.db.session import engine
    from core.db.tables import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture(scope="module")
async def app_client():
    """Async HTTP client wired directly to the FastAPI app (no real server needed).

    Skips automatically when PostgreSQL is not reachable.
    """
    _maybe_skip_db()
    await _ensure_schema()

    from core.api.app import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
