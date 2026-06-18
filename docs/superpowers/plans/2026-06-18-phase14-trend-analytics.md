# Phase 14 — Trend Analytics & Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pure-computation analytics helpers, four analytics API endpoints, a CSV export endpoint, and full test coverage to the Argus security platform.

**Architecture:** Pure computation functions live in `core/analytics/trends.py` (no DB calls — accept pre-fetched lists of dicts). The analytics router queries `ScanRow` + `FindingRow` via SQLAlchemy async, maps rows to plain dicts, then delegates all math to the pure helpers. The CSV export router streams findings using FastAPI's `StreamingResponse`.

**Tech Stack:** FastAPI + Python 3.12, Pydantic v2, SQLAlchemy 2 async, pytest-asyncio, httpx (ASGI transport for API tests).

## Global Constraints

- Python 3.12 minimum
- SQLAlchemy 2 async (`AsyncSession`, `select()` statement style — no `session.query()`)
- Pydantic v2
- All new router files: `from __future__ import annotations` at top
- `get_db` dependency from `core.api.deps`
- Router prefix declared on the `APIRouter` object, NOT re-declared in `app.include_router`
- Test files: async functions, no `@pytest.mark.asyncio` decorator needed (project uses auto-mode via pyproject.toml)
- Do NOT commit changes

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `core/analytics/__init__.py` | Create | Empty package marker |
| `core/analytics/trends.py` | Create | Pure computation: `bucket_key`, `compute_finding_trend`, `compute_mttr`, `top_rules` |
| `core/api/routers/analytics.py` | Create | REST endpoints: `/analytics/trends`, `/analytics/mttr`, `/analytics/top-rules`, `/analytics/summary` |
| `core/api/routers/export.py` | Create | REST endpoint: `/scans/export/csv` — StreamingResponse |
| `core/api/app.py` | Modify | Wire in analytics_router and export_router |
| `tests/core/analytics/__init__.py` | Create | Empty package marker |
| `tests/core/analytics/test_trends.py` | Create | Unit tests for pure functions (no DB, no HTTP) |
| `tests/core/api/test_analytics.py` | Create | API integration tests using dependency_overrides[get_db] |

---

### Task 1: Analytics package — pure computation helpers

**Files:**
- Create: `core/analytics/__init__.py`
- Create: `core/analytics/trends.py`
- Create: `tests/core/analytics/__init__.py`
- Create: `tests/core/analytics/test_trends.py`

**Interfaces:**
- Produces:
  - `bucket_key(dt: datetime, granularity: Literal["day","week"]) -> str`
  - `compute_finding_trend(findings: list[dict], granularity="day", days_back=30) -> list[dict]`
    - Returns: `[{"bucket": str, "total": int, "critical": int, "high": int, "medium": int, "low": int}, ...]`
  - `compute_mttr(findings: list[dict]) -> dict`
    - Returns: `{"mttr_hours": float | None, "sample_size": int}`
  - `top_rules(findings: list[dict], top_n=10) -> list[dict]`
    - Returns: `[{"rule_id": str, "count": int}, ...]`

- [ ] **Step 1: Create empty package markers**

Create `core/analytics/__init__.py` — empty file.
Create `tests/core/analytics/__init__.py` — empty file.

- [ ] **Step 2: Write failing tests for `bucket_key`**

Create `tests/core/analytics/test_trends.py`:

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from core.analytics.trends import bucket_key, compute_finding_trend, compute_mttr, top_rules


def test_bucket_key_day():
    dt = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert bucket_key(dt, "day") == "2026-03-15"


def test_bucket_key_week():
    dt = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    # strftime %W: week number (Sunday=0), 2026-03-15 is week 10
    assert bucket_key(dt, "week") == "2026-W10"
```

- [ ] **Step 3: Run to verify failure**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && source .venv/bin/activate && python -m pytest tests/core/analytics/test_trends.py::test_bucket_key_day -x -q 2>&1 | tail -10
```
Expected: ModuleNotFoundError or ImportError (file doesn't exist yet).

- [ ] **Step 4: Implement `core/analytics/trends.py`**

```python
# core/analytics/trends.py
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

Granularity = Literal["day", "week"]


def bucket_key(dt: datetime, granularity: Granularity) -> str:
    """Return YYYY-MM-DD for day, YYYY-Www for week."""
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    else:
        return dt.strftime("%Y-W%W")


def compute_finding_trend(
    findings: list[dict],
    granularity: Granularity = "day",
    days_back: int = 30,
) -> list[dict]:
    """
    Aggregate findings by bucket.
    Returns list of {"bucket": str, "total": int, "critical": int, "high": int, "medium": int, "low": int}
    sorted by bucket ascending. Buckets with zero findings are included (filled in).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)

    # Build ordered list of all expected buckets
    buckets: dict[str, dict] = {}
    current = cutoff
    while current <= now:
        key = bucket_key(current, granularity)
        if key not in buckets:
            buckets[key] = {"bucket": key, "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        current += timedelta(days=1)

    for f in findings:
        created_at: datetime = f["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at < cutoff:
            continue
        key = bucket_key(created_at, granularity)
        if key not in buckets:
            buckets[key] = {"bucket": key, "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        sev = (f.get("severity") or "").lower()
        buckets[key]["total"] += 1
        if sev in ("critical", "high", "medium", "low"):
            buckets[key][sev] += 1

    return sorted(buckets.values(), key=lambda x: x["bucket"])


def compute_mttr(findings: list[dict]) -> dict:
    """
    Compute mean time to remediate in hours.
    Returns {"mttr_hours": float | None, "sample_size": int}
    Only includes findings where resolved_at is not None.
    """
    durations: list[float] = []
    for f in findings:
        resolved_at = f.get("resolved_at")
        if resolved_at is None:
            continue
        created_at: datetime = f["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=timezone.utc)
        delta = resolved_at - created_at
        durations.append(delta.total_seconds() / 3600.0)

    if not durations:
        return {"mttr_hours": None, "sample_size": 0}

    return {
        "mttr_hours": round(sum(durations) / len(durations), 2),
        "sample_size": len(durations),
    }


def top_rules(findings: list[dict], top_n: int = 10) -> list[dict]:
    """
    Returns top_n most frequent rule_ids.
    Each item: {"rule_id": str, "count": int}
    """
    counts: Counter = Counter()
    for f in findings:
        rule_id = f.get("rule_id")
        if rule_id:
            counts[rule_id] += 1
    return [{"rule_id": rid, "count": cnt} for rid, cnt in counts.most_common(top_n)]
```

- [ ] **Step 5: Write complete unit tests**

Replace `tests/core/analytics/test_trends.py` with full test suite:

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from core.analytics.trends import bucket_key, compute_finding_trend, compute_mttr, top_rules


# --- bucket_key ---

def test_bucket_key_day():
    dt = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert bucket_key(dt, "day") == "2026-03-15"


def test_bucket_key_week():
    dt = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert bucket_key(dt, "week") == "2026-W10"


# --- compute_finding_trend ---

def _make_finding(days_ago: int, severity: str = "high") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "created_at": now - timedelta(days=days_ago),
        "severity": severity,
    }


def test_finding_trend_returns_correct_bucket_counts():
    findings = [
        _make_finding(1, "critical"),
        _make_finding(1, "high"),
        _make_finding(2, "medium"),
    ]
    result = compute_finding_trend(findings, granularity="day", days_back=7)
    # result is sorted by bucket ascending
    buckets = {r["bucket"]: r for r in result}
    now = datetime.now(timezone.utc)
    day1_key = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    day2_key = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    assert buckets[day1_key]["total"] == 2
    assert buckets[day1_key]["critical"] == 1
    assert buckets[day1_key]["high"] == 1
    assert buckets[day2_key]["total"] == 1
    assert buckets[day2_key]["medium"] == 1


def test_finding_trend_fills_empty_buckets():
    findings = [_make_finding(0, "low")]
    result = compute_finding_trend(findings, granularity="day", days_back=5)
    # Must have at least 6 buckets (days 0..5)
    assert len(result) >= 6
    # All non-today buckets have total=0
    now_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for r in result:
        if r["bucket"] != now_key:
            assert r["total"] == 0


def test_finding_trend_empty_input():
    result = compute_finding_trend([], granularity="day", days_back=3)
    assert isinstance(result, list)
    assert len(result) >= 4  # days 0..3
    for r in result:
        assert r["total"] == 0
        assert r["critical"] == 0


def test_finding_trend_sorted_ascending():
    findings = [_make_finding(i) for i in range(5)]
    result = compute_finding_trend(findings, granularity="day", days_back=10)
    buckets = [r["bucket"] for r in result]
    assert buckets == sorted(buckets)


# --- compute_mttr ---

def test_compute_mttr_correct_hours():
    now = datetime.now(timezone.utc)
    findings = [
        {"created_at": now - timedelta(hours=10), "resolved_at": now},
        {"created_at": now - timedelta(hours=20), "resolved_at": now},
    ]
    result = compute_mttr(findings)
    assert result["sample_size"] == 2
    assert result["mttr_hours"] == 15.0


def test_compute_mttr_none_when_no_resolved():
    now = datetime.now(timezone.utc)
    findings = [
        {"created_at": now - timedelta(hours=5), "resolved_at": None},
    ]
    result = compute_mttr(findings)
    assert result["mttr_hours"] is None
    assert result["sample_size"] == 0


def test_compute_mttr_empty_input():
    result = compute_mttr([])
    assert result["mttr_hours"] is None
    assert result["sample_size"] == 0


def test_compute_mttr_partial_resolved():
    now = datetime.now(timezone.utc)
    findings = [
        {"created_at": now - timedelta(hours=4), "resolved_at": now},
        {"created_at": now - timedelta(hours=8), "resolved_at": None},
    ]
    result = compute_mttr(findings)
    assert result["sample_size"] == 1
    assert result["mttr_hours"] == 4.0


# --- top_rules ---

def test_top_rules_correct_ordering():
    findings = [
        {"rule_id": "sql-injection"},
        {"rule_id": "xss"},
        {"rule_id": "sql-injection"},
        {"rule_id": "sql-injection"},
        {"rule_id": "xss"},
        {"rule_id": "path-traversal"},
    ]
    result = top_rules(findings, top_n=10)
    assert result[0]["rule_id"] == "sql-injection"
    assert result[0]["count"] == 3
    assert result[1]["rule_id"] == "xss"
    assert result[1]["count"] == 2


def test_top_rules_respects_top_n():
    findings = [{"rule_id": f"rule-{i}"} for i in range(20)]
    result = top_rules(findings, top_n=5)
    assert len(result) == 5


def test_top_rules_empty_input():
    result = top_rules([])
    assert result == []
```

- [ ] **Step 6: Run unit tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && source .venv/bin/activate && python -m pytest tests/core/analytics/ -x -q 2>&1 | tail -15
```
Expected: all tests PASS, 0 failures.

---

### Task 2: Analytics router (`/analytics/*`)

**Files:**
- Create: `core/api/routers/analytics.py`

**Interfaces:**
- Consumes: `ScanRow`, `FindingRow` from `core.db.tables`; `get_db` from `core.api.deps`; `compute_finding_trend`, `compute_mttr`, `top_rules` from `core.analytics.trends`
- Produces: `router` (APIRouter with prefix="/analytics", tags=["analytics"])
  - `GET /analytics/trends?granularity=day&days_back=30` → `list[dict]`
  - `GET /analytics/mttr?days_back=90` → `dict`
  - `GET /analytics/top-rules?top_n=10&days_back=30` → `list[dict]`
  - `GET /analytics/summary?days_back=30` → `dict`

- [ ] **Step 1: Create `core/api/routers/analytics.py`**

```python
# core/api/routers/analytics.py
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import get_db
from core.analytics.trends import compute_finding_trend, compute_mttr, top_rules
from core.db.tables import FindingRow, ScanRow

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _recent_scans(db: AsyncSession, days_back: int) -> list[ScanRow]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    result = await db.execute(
        select(ScanRow).where(ScanRow.started_at >= cutoff)
    )
    return list(result.scalars().all())


async def _findings_for_scans(db: AsyncSession, scan_ids: list[str]) -> list[FindingRow]:
    if not scan_ids:
        return []
    result = await db.execute(
        select(FindingRow).where(FindingRow.scan_id.in_(scan_ids))
    )
    return list(result.scalars().all())


@router.get("/trends")
async def trends_endpoint(
    granularity: Literal["day", "week"] = "day",
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_map = {s.id: s for s in scans}
    scan_ids = list(scan_map.keys())
    findings = await _findings_for_scans(db, scan_ids)

    finding_dicts = [
        {
            "created_at": scan_map[f.scan_id].started_at or datetime.now(timezone.utc),
            "severity": f.severity,
        }
        for f in findings
        if f.scan_id in scan_map
    ]
    return compute_finding_trend(finding_dicts, granularity=granularity, days_back=days_back)


@router.get("/mttr")
async def mttr_endpoint(
    days_back: int = 90,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_map = {s.id: s for s in scans}
    scan_ids = list(scan_map.keys())

    if not scan_ids:
        return compute_mttr([])

    result = await db.execute(
        select(FindingRow).where(
            FindingRow.scan_id.in_(scan_ids),
            FindingRow.status == "fixed",
        )
    )
    findings = list(result.scalars().all())

    finding_dicts = [
        {
            "created_at": scan_map[f.scan_id].started_at or datetime.now(timezone.utc),
            "resolved_at": scan_map[f.scan_id].finished_at,
        }
        for f in findings
        if f.scan_id in scan_map
    ]
    return compute_mttr(finding_dicts)


@router.get("/top-rules")
async def top_rules_endpoint(
    top_n: int = 10,
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_ids = [s.id for s in scans]
    findings = await _findings_for_scans(db, scan_ids)

    finding_dicts = [{"rule_id": f.rule_id} for f in findings]
    return top_rules(finding_dicts, top_n=top_n)


@router.get("/summary")
async def summary_endpoint(
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    scans = await _recent_scans(db, days_back)
    scan_ids = [s.id for s in scans]
    findings = await _findings_for_scans(db, scan_ids)

    severity_counts: Counter = Counter()
    owasp_counts: Counter = Counter()
    for f in findings:
        severity_counts[f.severity.lower()] += 1
        if f.owasp_category:
            owasp_counts[f.owasp_category] += 1

    risk_weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}
    valid_scores = [s.cost_usd for s in scans if s.cost_usd is not None]
    avg_risk = (
        sum(
            risk_weights.get(sev, 0) * cnt
            for sev, cnt in severity_counts.items()
        ) / max(len(scans), 1)
    )

    return {
        "total_scans": len(scans),
        "total_findings": len(findings),
        "severity_breakdown": dict(severity_counts),
        "top_owasp_categories": dict(owasp_counts.most_common(5)),
        "average_risk_score": round(avg_risk, 2),
        "days_back": days_back,
    }
```

---

### Task 3: Export router (`/scans/export/csv`)

**Files:**
- Create: `core/api/routers/export.py`

**Interfaces:**
- Produces: `router` (APIRouter with prefix="/scans", tags=["export"])
  - `GET /scans/export/csv?days_back=30` → `StreamingResponse` (text/csv)
  - Columns: `scan_id, target_ref, rule_id, severity, owasp_category, cwe, file, line, status, dedup_key`

- [ ] **Step 1: Create `core/api/routers/export.py`**

```python
# core/api/routers/export.py
from __future__ import annotations
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import get_db
from core.db.tables import FindingRow, ScanRow

router = APIRouter(prefix="/scans", tags=["export"])

_CSV_COLUMNS = [
    "scan_id", "target_ref", "rule_id", "severity",
    "owasp_category", "cwe", "file", "line", "status", "dedup_key",
]


@router.get("/export/csv")
async def export_findings_csv(
    days_back: int = 30,
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    scan_result = await db.execute(
        select(ScanRow).where(ScanRow.started_at >= cutoff)
    )
    scans = list(scan_result.scalars().all())
    scan_map = {s.id: s for s in scans}
    scan_ids = list(scan_map.keys())

    findings: list[FindingRow] = []
    if scan_ids:
        finding_result = await db.execute(
            select(FindingRow).where(FindingRow.scan_id.in_(scan_ids))
        )
        findings = list(finding_result.scalars().all())

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()

        for f in findings:
            scan = scan_map.get(f.scan_id)
            location = f.location or {}
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
            writer.writerow({
                "scan_id": f.scan_id,
                "target_ref": scan.target_ref if scan else "",
                "rule_id": f.rule_id,
                "severity": f.severity,
                "owasp_category": f.owasp_category or "",
                "cwe": f.cwe or "",
                "file": location.get("file", ""),
                "line": location.get("line", ""),
                "status": f.status,
                "dedup_key": f.dedup_key,
            })
            yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=findings.csv"},
    )
```

---

### Task 4: Wire routers into `core/api/app.py`

**Files:**
- Modify: `core/api/app.py`

**Interfaces:**
- Consumes: `router` from `core.api.routers.analytics`; `router` from `core.api.routers.export`

- [ ] **Step 1: Add imports after existing router imports**

In `core/api/app.py`, after `from core.api.routers.integrations import router as integrations_router`, add:

```python
from core.api.routers.analytics import router as analytics_router
from core.api.routers.export import router as export_router
```

- [ ] **Step 2: Register routers inside `create_app()`**

After `app.include_router(integrations_router, prefix="/api/v1")`, add:

```python
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(export_router, prefix="/api/v1")
```

---

### Task 5: API integration tests

**Files:**
- Create: `tests/core/api/test_analytics.py`

**Interfaces:**
- Consumes: `create_app` from `core.api.app`; `get_db` from `core.api.deps`
- Tests each of the 5 endpoints (4 analytics + 1 csv export) via ASGI client with dependency_overrides

- [ ] **Step 1: Create `tests/core/api/test_analytics.py`**

```python
# tests/core/api/test_analytics.py
from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock


def _make_app(session):
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return app


def _scan_row(scan_id="aaaa0000-0000-0000-0000-000000000001"):
    row = MagicMock()
    row.id = scan_id
    row.target_ref = "github.com/org/repo"
    row.status = "completed"
    row.started_at = datetime.now(timezone.utc) - timedelta(days=1)
    row.finished_at = datetime.now(timezone.utc)
    row.cost_usd = 0.05
    return row


def _finding_row(
    scan_id="aaaa0000-0000-0000-0000-000000000001",
    rule_id="sql-injection",
    severity="high",
    owasp="A03:2021",
    cwe="CWE-89",
    status="open",
):
    row = MagicMock()
    row.scan_id = scan_id
    row.rule_id = rule_id
    row.severity = severity
    row.owasp_category = owasp
    row.cwe = cwe
    row.status = status
    row.location = {"file": "app/db.py", "line": 42}
    row.dedup_key = f"dk-{rule_id}"
    return row


def _make_session(scans, findings):
    """Return an AsyncMock session that returns scans first, then findings for each subsequent execute."""
    session = AsyncMock()
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalars.return_value.all.return_value = scans
        else:
            r.scalars.return_value.all.return_value = findings
        return r

    session.execute = AsyncMock(side_effect=_execute)
    return session


# --- /analytics/trends ---

async def test_trends_returns_list():
    scan = _scan_row()
    finding = _finding_row()
    session = _make_session([scan], [finding])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/trends?days_back=7")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Each bucket has expected keys
    for item in data:
        assert "bucket" in item
        assert "total" in item
        assert "critical" in item


async def test_trends_empty_db():
    session = _make_session([], [])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/trends?days_back=3")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for item in data:
        assert item["total"] == 0


# --- /analytics/mttr ---

async def test_mttr_returns_dict_with_mttr_hours():
    scan = _scan_row()
    finding = _finding_row(status="fixed")
    session = _make_session([scan], [finding])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/mttr?days_back=90")
    assert resp.status_code == 200
    data = resp.json()
    assert "mttr_hours" in data
    assert "sample_size" in data


async def test_mttr_none_when_no_fixed_findings():
    scan = _scan_row()
    # No fixed findings — second execute returns empty list
    session = _make_session([scan], [])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/mttr")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mttr_hours"] is None
    assert data["sample_size"] == 0


# --- /analytics/top-rules ---

async def test_top_rules_returns_list():
    scan = _scan_row()
    findings = [_finding_row(rule_id="sql-injection") for _ in range(3)] + \
               [_finding_row(rule_id="xss") for _ in range(2)]
    session = _make_session([scan], findings)
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/top-rules?top_n=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert data[0]["rule_id"] == "sql-injection"
        assert data[0]["count"] == 3


async def test_top_rules_empty():
    session = _make_session([], [])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/top-rules")
    assert resp.status_code == 200
    assert resp.json() == []


# --- /analytics/summary ---

async def test_summary_returns_totals():
    scan = _scan_row()
    findings = [
        _finding_row(severity="critical", owasp="A03:2021"),
        _finding_row(severity="high", owasp="A03:2021"),
        _finding_row(severity="medium", owasp="A02:2021"),
    ]
    session = _make_session([scan], findings)
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/summary?days_back=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scans"] == 1
    assert data["total_findings"] == 3
    assert "severity_breakdown" in data
    assert "top_owasp_categories" in data
    assert "average_risk_score" in data


async def test_summary_empty_db():
    session = _make_session([], [])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scans"] == 0
    assert data["total_findings"] == 0


# --- /scans/export/csv ---

async def test_csv_export_returns_200_with_csv_content_type():
    scan = _scan_row()
    finding = _finding_row()
    session = _make_session([scan], [finding])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/scans/export/csv?days_back=30")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


async def test_csv_export_has_header_row():
    session = _make_session([], [])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/scans/export/csv?days_back=1")
    assert resp.status_code == 200
    lines = resp.text.strip().split("\n")
    header = lines[0]
    assert "scan_id" in header
    assert "severity" in header
    assert "rule_id" in header


async def test_csv_export_contains_finding_data():
    scan = _scan_row()
    finding = _finding_row(rule_id="path-traversal", severity="critical")
    session = _make_session([scan], [finding])
    app = _make_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/scans/export/csv?days_back=30")
    assert resp.status_code == 200
    assert "path-traversal" in resp.text
    assert "critical" in resp.text
```

- [ ] **Step 2: Run all tests to verify pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && source .venv/bin/activate && python -m pytest tests/core/analytics/ tests/core/api/test_analytics.py -x -q 2>&1 | tail -20
```
Expected: all tests PASS, 0 failures.
