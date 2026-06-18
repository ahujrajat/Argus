from __future__ import annotations
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from core.api.app import create_app
from core.api.deps import get_db


FIX_ID = str(uuid.uuid4())
FINDING_ID = str(uuid.uuid4())
SCAN_ID = str(uuid.uuid4())
AUTH_ID = str(uuid.uuid4())


def _make_fix_row(fix_id: str = FIX_ID, status: str = "proposed") -> MagicMock:
    row = MagicMock()
    row.id = fix_id
    row.finding_id = FINDING_ID
    row.diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-vulnerable()\n"
        "+safe()\n"
    )
    row.test = None
    row.explanation = "Replaces vulnerable call with safe equivalent"
    row.status = status
    row.validation_result = None
    return row


def _make_finding_row() -> MagicMock:
    row = MagicMock()
    row.id = FINDING_ID
    row.scan_id = SCAN_ID
    row.rule_id = "sqli-001"
    row.location = {"file": "src/app.py", "line_start": 1, "line_end": 1}
    return row


def _make_scan_row() -> MagicMock:
    row = MagicMock()
    row.id = SCAN_ID
    row.target_ref = "github.com/acme/myrepo@main"
    return row


def _make_auth_row() -> MagicMock:
    from datetime import datetime, timezone, timedelta
    row = MagicMock()
    row.id = AUTH_ID
    row.target = "github.com/acme/myrepo@main"
    row.owner_confirmed = True
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    return row


@pytest.fixture
def app():
    return create_app()


# ── local apply (create_pr=False) ─────────────────────────────────────────────

async def test_apply_local_sets_status_applied(app):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    call_count = [0]

    session = AsyncMock()

    def _execute_side_effect(stmt, *args, **kwargs):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = fix_row
        else:
            result.scalar_one_or_none.return_value = finding_row
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.add = MagicMock()
    session.flush = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        with patch("core.api.routers.fixes.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/v1/fixes/{FIX_ID}/apply",
                    json={"create_pr": False},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert fix_row.status == "applied"


async def test_apply_local_returns_404_when_fix_missing(app):
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/fixes/{FIX_ID}/apply",
                json={"create_pr": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


async def test_apply_local_writes_audit_log_entry(app):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    added_rows = []
    call_count = [0]

    session = AsyncMock()

    def _execute_side_effect(stmt, *args, **kwargs):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = fix_row
        else:
            result.scalar_one_or_none.return_value = finding_row
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.add = MagicMock(side_effect=added_rows.append)
    session.flush = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        with patch("core.api.routers.fixes.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.post(
                    f"/api/v1/fixes/{FIX_ID}/apply",
                    json={"create_pr": False},
                )
    finally:
        app.dependency_overrides.clear()

    from core.db.tables import AuditLogEntryRow
    audit_rows = [r for r in added_rows if isinstance(r, AuditLogEntryRow)]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "fix_applied_local"
    assert audit_rows[0].actor == "api"


# ── PR creation (create_pr=True) ──────────────────────────────────────────────

async def test_apply_pr_sets_status_pr_opened(app):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    scan_row = _make_scan_row()
    auth_row = _make_auth_row()

    mock_provider = AsyncMock()
    mock_provider.create_branch = AsyncMock()
    mock_provider.commit_file = AsyncMock()
    mock_provider.get_file_content = AsyncMock(return_value="vulnerable()\n")
    mock_provider.create_pr = AsyncMock(
        return_value="https://github.com/acme/myrepo/pull/42"
    )

    session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(stmt, *args, **kwargs):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = fix_row
        elif call_count[0] == 2:
            result.scalar_one_or_none.return_value = finding_row
        elif call_count[0] == 3:
            result.scalar_one_or_none.return_value = scan_row
        else:
            result.scalar_one_or_none.return_value = auth_row
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.add = MagicMock()
    session.flush = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        with patch("core.api.routers.fixes.get_vcs_provider", return_value=mock_provider):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/v1/fixes/{FIX_ID}/apply",
                    json={
                        "create_pr": True,
                        "vcs_token": "ghp_test",
                        "pr_base_branch": "main",
                    },
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pr_opened"
    assert body["pr_url"] == "https://github.com/acme/myrepo/pull/42"
    assert fix_row.status == "pr_opened"


async def test_apply_pr_returns_403_when_no_authorization(app):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    scan_row = _make_scan_row()

    session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(stmt, *args, **kwargs):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = fix_row
        elif call_count[0] == 2:
            result.scalar_one_or_none.return_value = finding_row
        elif call_count[0] == 3:
            result.scalar_one_or_none.return_value = scan_row
        else:
            result.scalar_one_or_none.return_value = None  # no authorization
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.add = MagicMock()
    session.flush = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/fixes/{FIX_ID}/apply",
                json={"create_pr": True, "vcs_token": "ghp_test"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403


async def test_apply_pr_requires_vcs_token(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/fixes/{FIX_ID}/apply",
            json={"create_pr": True},
        )
    assert resp.status_code == 422


async def test_apply_pr_writes_three_audit_log_entries(app):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    scan_row = _make_scan_row()
    auth_row = _make_auth_row()
    added_rows = []

    mock_provider = AsyncMock()
    mock_provider.create_branch = AsyncMock()
    mock_provider.commit_file = AsyncMock()
    mock_provider.get_file_content = AsyncMock(return_value="vulnerable()\n")
    mock_provider.create_pr = AsyncMock(
        return_value="https://github.com/acme/myrepo/pull/42"
    )

    session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(stmt, *args, **kwargs):
        result = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = fix_row
        elif call_count[0] == 2:
            result.scalar_one_or_none.return_value = finding_row
        elif call_count[0] == 3:
            result.scalar_one_or_none.return_value = scan_row
        else:
            result.scalar_one_or_none.return_value = auth_row
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.add = MagicMock(side_effect=added_rows.append)
    session.flush = AsyncMock()

    async def override():
        yield session

    app.dependency_overrides[get_db] = override
    try:
        with patch("core.api.routers.fixes.get_vcs_provider", return_value=mock_provider):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.post(
                    f"/api/v1/fixes/{FIX_ID}/apply",
                    json={"create_pr": True, "vcs_token": "ghp_test", "pr_base_branch": "main"},
                )
    finally:
        app.dependency_overrides.clear()

    from core.db.tables import AuditLogEntryRow
    audit_rows = [r for r in added_rows if isinstance(r, AuditLogEntryRow)]
    actions = {r.action for r in audit_rows}
    assert "vcs_branch_created" in actions
    assert "vcs_file_committed" in actions
    assert "fix_pr_created" in actions
