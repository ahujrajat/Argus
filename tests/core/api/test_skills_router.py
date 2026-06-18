# tests/core/api/test_skills_router.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from core.skills.base import Skill


def _make_skill(name: str, activation: str = "active") -> Skill:
    return Skill(
        name=name,
        description=f"Test skill {name}",
        languages=["python"],
        frameworks=[],
        activation=activation,
        body="- Some guidance",
    )


@pytest.fixture
async def client():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def client_with_db():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_skills_returns_builtin_skills(client):
    resp = await client.get("/api/v1/skills/")
    assert resp.status_code == 200
    skills = resp.json()
    assert isinstance(skills, list)
    names = {s["name"] for s in skills}
    assert "python-secure-coding" in names
    assert "secrets-detection" in names
    assert "iac-hardening" in names


@pytest.mark.asyncio
async def test_activate_skill(client_with_db):
    client, session = client_with_db
    with patch("core.api.routers.skills._loader") as mock_loader:
        skill = _make_skill("test-skill", activation="inactive")
        mock_loader.load_by_name.return_value = skill
        mock_loader.save_generated = MagicMock()

        resp = await client.post("/api/v1/skills/test-skill/activate")

    assert resp.status_code == 200
    assert resp.json()["activation"] == "active"
    mock_loader.save_generated.assert_called_once()
    session.add.assert_called_once()  # audit entry written


@pytest.mark.asyncio
async def test_disable_skill(client_with_db):
    client, session = client_with_db
    with patch("core.api.routers.skills._loader") as mock_loader:
        skill = _make_skill("test-skill", activation="active")
        mock_loader.load_by_name.return_value = skill
        mock_loader.save_generated = MagicMock()

        resp = await client.post("/api/v1/skills/test-skill/disable")

    assert resp.status_code == 200
    assert resp.json()["activation"] == "inactive"
    session.add.assert_called_once()  # audit entry written


@pytest.mark.asyncio
async def test_activate_unknown_skill_returns_404(client_with_db):
    client, session = client_with_db
    with patch("core.api.routers.skills._loader") as mock_loader:
        mock_loader.load_by_name.return_value = None
        resp = await client.post("/api/v1/skills/nonexistent/activate")

    assert resp.status_code == 404
    assert "nonexistent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_skills_with_language_filter(client):
    resp = await client.get("/api/v1/skills/?language=python")
    assert resp.status_code == 200
    skills = resp.json()
    for s in skills:
        assert "python" in [l.lower() for l in s["languages"]] or s["languages"] == []


@pytest.mark.asyncio
async def test_audit_log_endpoint(client_with_db):
    client, session = client_with_db
    from core.db.tables import AuditLogEntryRow
    from uuid import uuid4
    from datetime import datetime, timezone

    row = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action="skill.activate",
        target="skill:python-secure-coding",
        before={"activation": "inactive"},
        after={"activation": "active"},
        timestamp=datetime.now(timezone.utc),
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=mock_result)

    resp = await client.get("/api/v1/audit/")

    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["action"] == "skill.activate"
    assert entries[0]["target"] == "skill:python-secure-coding"
