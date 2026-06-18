from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


def _make_app(session):
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _scan_row(scan_id="11111111-1111-1111-1111-111111111111"):
    row = MagicMock()
    row.id = scan_id
    row.target_ref = "github.com/org/repo"
    row.status = "completed"
    return row


def _finding_row(rule_id, severity, owasp=None, cwe=None):
    row = MagicMock()
    row.rule_id = rule_id
    row.severity = severity
    row.owasp_category = owasp
    row.cwe = cwe
    return row


async def test_compliance_report_basic():
    scan = _scan_row("11111111-1111-1111-1111-111111111111")
    findings = [
        _finding_row("sqli", "high", owasp="A03:2021", cwe="CWE-89"),
        _finding_row("xss", "medium", owasp="A03:2021", cwe="CWE-79"),
        _finding_row("info-leak", "low", owasp="A02:2021", cwe="CWE-200"),
    ]

    session = AsyncMock()
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            r = MagicMock()
            r.scalar_one_or_none.return_value = scan
            return r
        else:
            r = MagicMock()
            r.scalars.return_value.all.return_value = findings
            return r

    session.execute = AsyncMock(side_effect=_execute)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/scans/11111111-1111-1111-1111-111111111111/report")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 3
    assert data["severity_breakdown"]["high"] == 1
    assert data["severity_breakdown"]["medium"] == 1
    assert data["severity_breakdown"]["low"] == 1
    assert "A03:2021" in data["owasp_top10"]
    assert data["owasp_top10"]["A03:2021"] == 2
    assert "CWE-89" in data["cwe_top10"]
    # risk_score: high=5, medium=2, low=1 → 8
    assert data["risk_score"] == 8


async def test_compliance_report_scan_not_found():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/scans/00000000-0000-0000-0000-000000000000/report")

    assert resp.status_code == 404


async def test_compliance_report_no_findings():
    scan = _scan_row("22222222-2222-2222-2222-222222222222")
    session = AsyncMock()
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            r = MagicMock()
            r.scalar_one_or_none.return_value = scan
            return r
        else:
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

    session.execute = AsyncMock(side_effect=_execute)

    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/scans/22222222-2222-2222-2222-222222222222/report")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 0
    assert data["risk_score"] == 0
    assert data["severity_breakdown"] == {}
    assert data["owasp_top10"] == {}
