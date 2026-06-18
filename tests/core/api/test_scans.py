from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
async def client():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_openapi_schema_exists(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    # FastAPI adds trailing slash; check either form
    assert any(p.startswith("/api/v1/scans") for p in schema["paths"])


async def test_startup_calls_seed():
    import asyncio
    from core.api.app import create_app

    with patch("core.api.app.seed_pipeline_configs", new_callable=AsyncMock) as mock_seed, \
         patch("core.api.app.get_session") as mock_get_session:

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_get_session.return_value = mock_cm

        app = create_app()

        called = asyncio.Event()

        async def receive():
            if not called.is_set():
                called.set()
                return {"type": "lifespan.startup"}
            return {"type": "lifespan.shutdown"}

        async def send(event):
            pass

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)

    mock_seed.assert_called_once_with(mock_session)
