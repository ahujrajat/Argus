# tests/core/api/test_analytics.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from datetime import datetime, timezone, timedelta


def _make_scan_row(scan_id: str | None = None, started_at=None, finished_at=None, target_ref="repo/main"):
    row = MagicMock()
    row.id = scan_id or str(uuid4())
    row.target_ref = target_ref
    row.started_at = started_at or datetime.now(timezone.utc) - timedelta(days=1)
    row.finished_at = finished_at
    return row


def _make_finding_row(
    scan_id: str,
    rule_id: str = "sql-injection",
    severity: str = "high",
    status: str = "open",
    owasp_category: str | None = "A03",
    cwe: str | None = "CWE-89",
    dedup_key: str | None = None,
):
    row = MagicMock()
    row.id = str(uuid4())
    row.scan_id = scan_id
    row.rule_id = rule_id
    row.severity = severity
    row.status = status
    row.owasp_category = owasp_category
    row.cwe = cwe
    row.dedup_key = dedup_key or f"dk-{uuid4()}"
    row.location = {"file": "app.py", "line": 42}
    return row


@pytest.fixture
async def analytics_client():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()
    mock_session = AsyncMock()

    # Default: empty results
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /analytics/trends
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trends_returns_list_empty_db(analytics_client):
    client, session = analytics_client
    scan_result = MagicMock()
    scan_result.scalars.return_value.all.return_value = []
    # findings query would also return empty
    session.execute = AsyncMock(return_value=scan_result)

    resp = await client.get("/api/v1/analytics/trends?granularity=day&days_back=7")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Should have filled-in zero buckets for 7 days
    assert len(data) >= 7


@pytest.mark.asyncio
async def test_trends_returns_list_with_findings(analytics_client):
    client, session = analytics_client

    scan_id = str(uuid4())
    scan = _make_scan_row(scan_id=scan_id, started_at=datetime.now(timezone.utc) - timedelta(days=2))
    finding = _make_finding_row(scan_id=scan_id, severity="critical")

    # First call: scans; second call: findings
    scan_result = MagicMock()
    scan_result.scalars.return_value.all.return_value = [scan]

    finding_result = MagicMock()
    finding_result.scalars.return_value.all.return_value = [finding]

    session.execute = AsyncMock(side_effect=[scan_result, finding_result])

    resp = await client.get("/api/v1/analytics/trends?granularity=day&days_back=30")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # At least one bucket should have total > 0
    totals = [b["total"] for b in data]
    assert sum(totals) == 1


# ---------------------------------------------------------------------------
# /analytics/mttr
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mttr_returns_dict_no_findings(analytics_client):
    client, session = analytics_client
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)

    resp = await client.get("/api/v1/analytics/mttr?days_back=90")
    assert resp.status_code == 200
    data = resp.json()
    assert "mttr_hours" in data
    assert data["mttr_hours"] is None
    assert data["sample_size"] == 0


@pytest.mark.asyncio
async def test_mttr_returns_dict_with_fixed_findings(analytics_client):
    client, session = analytics_client

    scan_id = str(uuid4())
    now = datetime.now(timezone.utc)
    scan = _make_scan_row(
        scan_id=scan_id,
        started_at=now - timedelta(hours=10),
        finished_at=now,
    )
    finding = _make_finding_row(scan_id=scan_id, status="fixed")

    scan_result = MagicMock()
    scan_result.scalars.return_value.all.return_value = [scan]

    fixed_result = MagicMock()
    fixed_result.scalars.return_value.all.return_value = [finding]

    session.execute = AsyncMock(side_effect=[scan_result, fixed_result])

    resp = await client.get("/api/v1/analytics/mttr?days_back=90")
    assert resp.status_code == 200
    data = resp.json()
    assert "mttr_hours" in data
    assert data["sample_size"] == 1
    assert data["mttr_hours"] == 10.0


# ---------------------------------------------------------------------------
# /analytics/top-rules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_top_rules_returns_list_empty(analytics_client):
    client, session = analytics_client
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)

    resp = await client.get("/api/v1/analytics/top-rules?top_n=10&days_back=30")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data == []


@pytest.mark.asyncio
async def test_top_rules_returns_sorted_list(analytics_client):
    client, session = analytics_client

    scan_id = str(uuid4())
    scan = _make_scan_row(scan_id=scan_id)
    findings = [
        _make_finding_row(scan_id=scan_id, rule_id="sql-injection"),
        _make_finding_row(scan_id=scan_id, rule_id="sql-injection"),
        _make_finding_row(scan_id=scan_id, rule_id="xss"),
    ]

    scan_result = MagicMock()
    scan_result.scalars.return_value.all.return_value = [scan]

    finding_result = MagicMock()
    finding_result.scalars.return_value.all.return_value = findings

    session.execute = AsyncMock(side_effect=[scan_result, finding_result])

    resp = await client.get("/api/v1/analytics/top-rules?top_n=10&days_back=30")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["rule_id"] == "sql-injection"
    assert data[0]["count"] == 2


# ---------------------------------------------------------------------------
# /analytics/summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_returns_dict_empty_db(analytics_client):
    client, session = analytics_client
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)

    resp = await client.get("/api/v1/analytics/summary?days_back=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_scans" in data
    assert "total_findings" in data
    assert data["total_scans"] == 0
    assert data["total_findings"] == 0


@pytest.mark.asyncio
async def test_summary_returns_dict_with_data(analytics_client):
    client, session = analytics_client

    scan_id = str(uuid4())
    scan = _make_scan_row(scan_id=scan_id)
    findings = [
        _make_finding_row(scan_id=scan_id, severity="high", owasp_category="A03"),
        _make_finding_row(scan_id=scan_id, severity="critical", owasp_category="A01"),
    ]

    scan_result = MagicMock()
    scan_result.scalars.return_value.all.return_value = [scan]

    finding_result = MagicMock()
    finding_result.scalars.return_value.all.return_value = findings

    session.execute = AsyncMock(side_effect=[scan_result, finding_result])

    resp = await client.get("/api/v1/analytics/summary?days_back=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_scans" in data
    assert "total_findings" in data
    assert data["total_scans"] == 1
    assert data["total_findings"] == 2
    # severity_breakdown key (the router uses "severity_breakdown")
    assert "severity_breakdown" in data


# ---------------------------------------------------------------------------
# /scans/export/csv
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_csv_export_returns_200_text_csv_empty(analytics_client):
    client, session = analytics_client
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)

    resp = await client.get("/api/v1/scans/export/csv?days_back=30")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_csv_export_contains_header_row(analytics_client):
    client, session = analytics_client
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)

    resp = await client.get("/api/v1/scans/export/csv?days_back=30")
    assert resp.status_code == 200
    content = resp.text
    assert "scan_id" in content
    assert "severity" in content
    assert "rule_id" in content


@pytest.mark.asyncio
async def test_csv_export_with_findings(analytics_client):
    client, session = analytics_client

    scan_id = str(uuid4())
    scan = _make_scan_row(scan_id=scan_id)
    finding = _make_finding_row(
        scan_id=scan_id,
        rule_id="sql-injection",
        severity="critical",
        owasp_category="A03",
        cwe="CWE-89",
    )

    scan_result = MagicMock()
    scan_result.scalars.return_value.all.return_value = [scan]

    finding_result = MagicMock()
    finding_result.scalars.return_value.all.return_value = [finding]

    session.execute = AsyncMock(side_effect=[scan_result, finding_result])

    resp = await client.get("/api/v1/scans/export/csv?days_back=30")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.text
    assert "sql-injection" in content
    assert "critical" in content
