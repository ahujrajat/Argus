# Phase 15: Production Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cursor-based pagination, full-text search, and OpenTelemetry tracing to the Argus security platform API.

**Architecture:** Introduce two focused helper modules (`core/api/pagination.py`, `core/api/search.py`) consumed by the existing scan and finding routers; add a new `core/observability/tracing.py` module wired into the FastAPI lifespan. All existing endpoints remain backward-compatible — cursor and search params are optional with defaults.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Python 3.12, opentelemetry-sdk>=1.24.0, opentelemetry-instrumentation-fastapi>=0.45b0, opentelemetry-exporter-otlp-proto-http>=1.24.0

## Global Constraints

- Python 3.12, Pydantic v2, SQLAlchemy 2 async, structlog
- Venv at `.venv` — all installs via `source .venv/bin/activate && uv pip install ...`
- Do NOT break existing tests — cursor/q/limit params must be optional with defaults
- Do NOT commit any changes
- Existing baseline: 402 tests passing

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `core/api/pagination.py` | `Page` dataclass, `encode_cursor`, `decode_cursor`, `paginate_list` |
| Create | `core/api/search.py` | `matches_query` full-text search helper |
| Modify | `core/api/routers/scans.py` | Add `limit`/`cursor` params to `GET /scans/` |
| Modify | `core/api/routers/findings.py` | Add `limit`/`cursor`/`q` params to `GET /scans/{scan_id}/findings` |
| Create | `core/observability/tracing.py` | OTel tracer setup, `setup_tracing`, `get_tracer` |
| Modify | `core/api/app.py` | Wire `setup_tracing("argus")` into lifespan |
| Modify | `pyproject.toml` | Add three OTel dependencies |
| Create | `tests/core/api/test_pagination.py` | Unit tests for pagination helper |
| Create | `tests/core/api/test_search.py` | Unit tests for `matches_query` |
| Create | `tests/core/observability/test_tracing.py` | Unit tests for tracing setup |

---

### Task 1: Pagination helper — `core/api/pagination.py`

**Files:**
- Create: `core/api/pagination.py`
- Test: `tests/core/api/test_pagination.py`

**Interfaces:**
- Produces:
  - `Page` dataclass with `items: list[Any]`, `next_cursor: str | None`, `total: int | None`
  - `encode_cursor(value: str) -> str`
  - `decode_cursor(cursor: str) -> str`
  - `paginate_list(items: list[Any], limit: int, cursor_field: str = "id") -> Page`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/api/test_pagination.py`:

```python
from __future__ import annotations
import pytest
from core.api.pagination import encode_cursor, decode_cursor, paginate_list, Page


def test_encode_decode_roundtrip():
    original = "some-uuid-1234"
    assert decode_cursor(encode_cursor(original)) == original


def test_encode_decode_roundtrip_special_chars():
    original = "abc+def/xyz=="
    assert decode_cursor(encode_cursor(original)) == original


def test_paginate_list_fewer_than_limit_returns_no_cursor():
    items = [{"id": str(i)} for i in range(3)]
    page = paginate_list(items, limit=10)
    assert page.next_cursor is None
    assert len(page.items) == 3


def test_paginate_list_exact_limit_returns_no_cursor():
    items = [{"id": str(i)} for i in range(10)]
    page = paginate_list(items, limit=10)
    assert page.next_cursor is None
    assert len(page.items) == 10


def test_paginate_list_more_than_limit_returns_cursor():
    # Caller passes limit+1 items to detect next page
    items = [{"id": str(i)} for i in range(11)]
    page = paginate_list(items, limit=10)
    assert page.next_cursor is not None
    assert len(page.items) == 10  # capped at limit
    assert decode_cursor(page.next_cursor) == "9"  # last item in page_items


def test_paginate_list_cursor_encodes_last_item_id():
    items = [{"id": f"item-{i}"} for i in range(6)]
    page = paginate_list(items, limit=5)
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "item-4"


def test_paginate_list_with_dicts():
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    page = paginate_list(items, limit=2)
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "b"
    assert len(page.items) == 2


class FakeObj:
    def __init__(self, id_val):
        self.id = id_val


def test_paginate_list_with_objects():
    items = [FakeObj(f"obj-{i}") for i in range(4)]
    page = paginate_list(items, limit=3)
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "obj-2"
    assert len(page.items) == 3


def test_paginate_list_custom_cursor_field():
    items = [{"name": f"x-{i}"} for i in range(4)]
    page = paginate_list(items, limit=3, cursor_field="name")
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == "x-2"


def test_page_dataclass_total_defaults_none():
    page = Page(items=[], next_cursor=None)
    assert page.total is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/test_pagination.py -v 2>&1 | tail -15
```

Expected: ImportError or ModuleNotFoundError for `core.api.pagination`

- [ ] **Step 3: Create `core/api/pagination.py`**

```python
from __future__ import annotations
import base64
from dataclasses import dataclass
from typing import Any


@dataclass
class Page:
    items: list[Any]
    next_cursor: str | None   # None means no more pages
    total: int | None = None  # optional total count


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def paginate_list(items: list[Any], limit: int, cursor_field: str = "id") -> Page:
    """
    Given a list already fetched from DB (fetch limit+1 to detect next page),
    return a Page with next_cursor set if there are more items.
    items should be dicts or objects with a cursor_field attribute/key.
    """
    has_more = len(items) > limit
    page_items = items[:limit]
    next_cursor = None
    if has_more:
        last = page_items[-1]
        val = last[cursor_field] if isinstance(last, dict) else getattr(last, cursor_field)
        next_cursor = encode_cursor(str(val))
    return Page(items=page_items, next_cursor=next_cursor)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/test_pagination.py -v 2>&1 | tail -20
```

Expected: all 10 tests PASS

---

### Task 2: Full-text search helper — `core/api/search.py`

**Files:**
- Create: `core/api/search.py`
- Test: `tests/core/api/test_search.py`

**Interfaces:**
- Produces: `matches_query(finding: dict, q: str) -> bool`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/api/test_search.py`:

```python
from __future__ import annotations
import pytest
from core.api.search import matches_query


def _finding(**kwargs) -> dict:
    base = {
        "rule_id": "",
        "source_tool": "",
        "cwe": "",
        "owasp_category": "",
        "explanation": "",
        "dedup_key": "",
        "location": {},
    }
    base.update(kwargs)
    return base


def test_matches_rule_id():
    f = _finding(rule_id="sql-injection")
    assert matches_query(f, "sql") is True


def test_matches_source_tool():
    f = _finding(source_tool="semgrep")
    assert matches_query(f, "semgrep") is True


def test_matches_cwe():
    f = _finding(cwe="CWE-89")
    assert matches_query(f, "CWE-89") is True


def test_matches_owasp_category():
    f = _finding(owasp_category="A01:2021")
    assert matches_query(f, "A01") is True


def test_matches_explanation():
    f = _finding(explanation="This is a SQL injection vulnerability")
    assert matches_query(f, "injection") is True


def test_matches_dedup_key():
    f = _finding(dedup_key="abc123")
    assert matches_query(f, "abc123") is True


def test_matches_location_file():
    f = _finding(location={"file": "src/api/db.py"})
    assert matches_query(f, "db.py") is True


def test_case_insensitive_match():
    f = _finding(rule_id="SQL-INJECTION")
    assert matches_query(f, "sql-injection") is True


def test_case_insensitive_query_upper():
    f = _finding(source_tool="semgrep")
    assert matches_query(f, "SEMGREP") is True


def test_no_match_returns_false():
    f = _finding(rule_id="xss", source_tool="bandit")
    assert matches_query(f, "nonexistent-term-xyz") is False


def test_empty_query_matches_everything():
    # "" is a substring of any string, so empty query always matches
    f = _finding(rule_id="anything")
    assert matches_query(f, "") is True


def test_location_not_dict_does_not_crash():
    f = _finding(location=None)
    # Should not raise; location.file lookup is skipped
    assert matches_query(f, "something") is False


def test_location_string_does_not_crash():
    f = _finding(location="some/path.py")
    # location is not a dict, so file lookup is skipped
    assert matches_query(f, "path.py") is False


def test_missing_fields_do_not_crash():
    f = {}  # completely empty finding
    assert matches_query(f, "anything") is False


def test_partial_match_in_file_path():
    f = _finding(location={"file": "/home/user/projects/app/utils.py"})
    assert matches_query(f, "utils") is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/test_search.py -v 2>&1 | tail -15
```

Expected: ImportError for `core.api.search`

- [ ] **Step 3: Create `core/api/search.py`**

```python
from __future__ import annotations


def matches_query(finding: dict, q: str) -> bool:
    """
    Case-insensitive substring search across key finding fields:
    rule_id, source_tool, cwe, owasp_category, explanation, dedup_key,
    and location.file if location is a dict.
    """
    q_lower = q.lower()
    fields = [
        finding.get("rule_id", ""),
        finding.get("source_tool", ""),
        finding.get("cwe", ""),
        finding.get("owasp_category", ""),
        finding.get("explanation", ""),
        finding.get("dedup_key", ""),
        (finding.get("location") or {}).get("file", "") if isinstance(finding.get("location"), dict) else "",
    ]
    return any(q_lower in (f or "").lower() for f in fields)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/test_search.py -v 2>&1 | tail -20
```

Expected: all 15 tests PASS

---

### Task 3: Paginated scans list — update `core/api/routers/scans.py`

**Files:**
- Modify: `core/api/routers/scans.py` (lines 1-31, the imports and `list_scans` function)

**Interfaces:**
- Consumes: `decode_cursor(cursor: str) -> str` from `core.api.pagination`; `paginate_list(items, limit) -> Page` from `core.api.pagination`

- [ ] **Step 1: Update the `list_scans` function in `core/api/routers/scans.py`**

Replace the existing imports block and `list_scans` function. The new version adds `limit` and `cursor` query parameters, fetches `limit + 1` rows, and returns a paginated response.

Find and replace in `core/api/routers/scans.py`:

Old imports (lines 1-12):
```python
# core/api/routers/scans.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.tables import ScanRow, FindingRow
from core.model.entities import ScanMode, SecurityApproach

router = APIRouter(prefix="/scans", tags=["scans"])
```

New imports:
```python
# core/api/routers/scans.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.tables import ScanRow, FindingRow
from core.model.entities import ScanMode, SecurityApproach
from core.api.pagination import decode_cursor, paginate_list

router = APIRouter(prefix="/scans", tags=["scans"])
```

Old `list_scans` function (lines 26-31):
```python
@router.get("/")
async def list_scans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).order_by(ScanRow.started_at.desc()).limit(50))
    rows = result.scalars().all()
    return [{"id": r.id, "target_ref": r.target_ref, "status": r.status,
             "mode": r.mode, "approach": r.approach, "cost_usd": r.cost_usd} for r in rows]
```

New `list_scans` function:
```python
@router.get("/")
async def list_scans(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=200),
    cursor: str | None = Query(default=None),
):
    q = select(ScanRow).order_by(ScanRow.id)
    if cursor:
        q = q.where(ScanRow.id > decode_cursor(cursor))
    q = q.limit(limit + 1)
    result = await db.execute(q)
    rows = list(result.scalars().all())
    items = [
        {"id": r.id, "target_ref": r.target_ref, "status": r.status,
         "mode": r.mode, "approach": r.approach, "cost_usd": r.cost_usd}
        for r in rows
    ]
    page = paginate_list(items, limit)
    return {"items": page.items, "next_cursor": page.next_cursor, "limit": limit}
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/ -q 2>&1 | tail -10
```

Expected: all existing API tests still pass (no regressions)

---

### Task 4: Paginated + searchable findings list — update `core/api/routers/findings.py`

**Files:**
- Modify: `core/api/routers/findings.py`

**Interfaces:**
- Consumes: `decode_cursor` and `paginate_list` from `core.api.pagination`; `matches_query` from `core.api.search`

- [ ] **Step 1: Replace entire `core/api/routers/findings.py`**

```python
# core/api/routers/findings.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import FindingRow
from core.api.pagination import decode_cursor, paginate_list
from core.api.search import matches_query

router = APIRouter(prefix="/scans", tags=["findings"])


@router.get("/{scan_id}/findings")
async def list_findings(
    scan_id: UUID,
    severity: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FindingRow).where(FindingRow.scan_id == str(scan_id))
    if severity:
        stmt = stmt.where(FindingRow.severity == severity)
    if status:
        stmt = stmt.where(FindingRow.status == status)
    if cursor:
        stmt = stmt.where(FindingRow.id > decode_cursor(cursor))
    stmt = stmt.order_by(FindingRow.id).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    items = [
        {
            "id": r.id, "rule_id": r.rule_id, "source_tool": r.source_tool,
            "cwe": r.cwe, "owasp_category": r.owasp_category,
            "severity": r.severity, "confidence": r.confidence,
            "exploit_likelihood": r.exploit_likelihood,
            "reachability": r.reachability,
            "location": r.location, "status": r.status,
            "explanation": r.explanation,
            "dedup_key": r.dedup_key,
        }
        for r in rows
    ]
    if q:
        items = [item for item in items if matches_query(item, q)]
    page = paginate_list(items, limit)
    return {"items": page.items, "next_cursor": page.next_cursor, "limit": limit}
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/ -q 2>&1 | tail -10
```

Expected: all existing API tests still pass

---

### Task 5: Install OTel packages and update `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Install OTel packages into venv**

```bash
source .venv/bin/activate && uv pip install "opentelemetry-sdk>=1.24.0" "opentelemetry-instrumentation-fastapi>=0.45b0" "opentelemetry-exporter-otlp-proto-http>=1.24.0" 2>&1 | tail -5
```

Expected: Successfully installed ... lines with the three packages

- [ ] **Step 2: Add OTel packages to `pyproject.toml` dependencies**

In `pyproject.toml`, find the end of the `dependencies` list (before the closing `]` of the `dependencies` array) and add the three entries. The current last dependency is `"croniter>=2.0.0"`. Replace:

```toml
    "croniter>=2.0.0",
]
```

with:

```toml
    "croniter>=2.0.0",
    "opentelemetry-sdk>=1.24.0",
    "opentelemetry-instrumentation-fastapi>=0.45b0",
    "opentelemetry-exporter-otlp-proto-http>=1.24.0",
]
```

- [ ] **Step 3: Verify packages are importable**

```bash
source .venv/bin/activate && python -c "from opentelemetry import trace; from opentelemetry.sdk.trace import TracerProvider; print('ok')"
```

Expected: `ok`

---

### Task 6: OpenTelemetry tracing module — `core/observability/tracing.py`

**Files:**
- Create: `core/observability/tracing.py`
- Modify: `core/api/app.py` (add `setup_tracing` call in lifespan)
- Test: `tests/core/observability/test_tracing.py`

**Interfaces:**
- Produces:
  - `setup_tracing(service_name: str = "argus") -> None`
  - `get_tracer() -> trace.Tracer`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/observability/test_tracing.py`:

```python
from __future__ import annotations
import os
import pytest
from unittest.mock import patch
from opentelemetry import trace as otel_trace


def test_setup_tracing_runs_without_error():
    from core.observability.tracing import setup_tracing
    # Should not raise
    setup_tracing("test-service")


def test_get_tracer_returns_tracer_instance():
    from core.observability import tracing as tracing_mod
    # Reset module-level _tracer so get_tracer triggers setup
    tracing_mod._tracer = None
    tracer = tracing_mod.get_tracer()
    # opentelemetry.trace.Tracer is a protocol; check it has start_as_current_span
    assert hasattr(tracer, "start_as_current_span")


def test_get_tracer_returns_same_instance_on_repeat_calls():
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None
    t1 = tracing_mod.get_tracer()
    t2 = tracing_mod.get_tracer()
    assert t1 is t2


def test_setup_tracing_uses_console_exporter_by_default(monkeypatch):
    """When OTEL_EXPORTER_OTLP_ENDPOINT is not set, ConsoleSpanExporter is used."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from core.observability.tracing import setup_tracing
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None
    # Should not raise; uses console exporter path
    setup_tracing("argus-console-test")
    assert tracing_mod._tracer is not None


def test_setup_tracing_uses_otlp_when_env_var_set(monkeypatch):
    """When OTEL_EXPORTER_OTLP_ENDPOINT is set, OTLPSpanExporter branch is taken."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None

    with patch("core.observability.tracing.BatchSpanProcessor") as mock_bsp, \
         patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_otlp:
        from core.observability.tracing import setup_tracing
        setup_tracing("argus-otlp-test")
        # BatchSpanProcessor was called (at least once)
        assert mock_bsp.called


def test_setup_tracing_service_name_in_resource():
    """Resource is created with the given service name."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None

    with patch("core.observability.tracing.TracerProvider") as mock_provider_cls:
        mock_provider = mock_provider_cls.return_value
        mock_provider.add_span_processor = lambda x: None
        mock_provider.get_tracer = lambda name: otel_trace.get_tracer(name)

        from core.observability.tracing import setup_tracing
        setup_tracing("my-custom-service")

        # Resource passed to TracerProvider should have service.name
        call_kwargs = mock_provider_cls.call_args
        resource_arg = call_kwargs.kwargs.get("resource") or call_kwargs.args[0] if call_kwargs.args else None
        if resource_arg is not None:
            assert resource_arg.attributes.get("service.name") == "my-custom-service"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/core/observability/test_tracing.py -v 2>&1 | tail -15
```

Expected: ImportError for `core.observability.tracing`

- [ ] **Step 3: Create `core/observability/tracing.py`**

```python
from __future__ import annotations
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

_tracer: trace.Tracer | None = None


def setup_tracing(service_name: str = "argus") -> None:
    """Configure SDK. Uses OTLP if OTEL_EXPORTER_OTLP_ENDPOINT is set, else Console."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    global _tracer
    _tracer = trace.get_tracer(service_name)


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        setup_tracing()
    return _tracer
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/core/observability/test_tracing.py -v 2>&1 | tail -15
```

Expected: all 6 tests PASS

- [ ] **Step 5: Wire `setup_tracing` into `core/api/app.py` lifespan**

Add import at the top of `core/api/app.py` (after the existing `from core.observability.metrics import metrics_text` line):

```python
from core.observability.tracing import setup_tracing
```

In the lifespan function, add `setup_tracing("argus")` as the first call inside `async with get_session()` block — before the `yield`. Replace the lifespan function body:

Old lifespan:
```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        from core.scheduler.runner import scheduler_loop

        async with get_session() as session:
            await seed_pipeline_configs(session)

        scheduler_task = asyncio.create_task(scheduler_loop())
        yield
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
```

New lifespan:
```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        from core.scheduler.runner import scheduler_loop

        setup_tracing("argus")

        async with get_session() as session:
            await seed_pipeline_configs(session)

        scheduler_task = asyncio.create_task(scheduler_loop())
        yield
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 6: Verify app startup test still passes**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/test_scans.py -v 2>&1 | tail -15
```

Expected: all scans tests pass (including `test_startup_calls_seed`)

---

### Task 7: Full test suite verification

- [ ] **Step 1: Run all new tests**

```bash
source .venv/bin/activate && python -m pytest tests/core/api/test_pagination.py tests/core/api/test_search.py tests/core/observability/test_tracing.py -v 2>&1 | tail -30
```

Expected: all new tests PASS (10 pagination + 15 search + 6 tracing = 31 tests)

- [ ] **Step 2: Run full test suite**

```bash
source .venv/bin/activate && python -m pytest --ignore=tests/e2e -q 2>&1 | tail -10
```

Expected: ≥ 433 passed (402 original + 31 new), 0 failed

---

## Self-Review Against Spec

| Spec requirement | Task covering it |
|---|---|
| `core/api/pagination.py` with `Page`, `encode_cursor`, `decode_cursor`, `paginate_list` | Task 1 |
| `core/api/search.py` with `matches_query` | Task 2 |
| `GET /scans/` with `limit`/`cursor` params, fetch `limit+1`, `{"items",[...], "next_cursor","limit"}` response | Task 3 |
| `GET /scans/{scan_id}/findings` with `limit`/`cursor`/`q` params | Task 4 |
| `core/observability/tracing.py` with `setup_tracing`/`get_tracer` | Task 6 |
| Wire `setup_tracing` in `app.py` lifespan | Task 6 Step 5 |
| Install OTel packages via `uv pip install` | Task 5 Step 1 |
| Add OTel deps to `pyproject.toml` | Task 5 Step 2 |
| `tests/core/api/test_pagination.py` — roundtrip, no-next, has-next, dict+object | Task 1 |
| `tests/core/api/test_search.py` — all field matches, case-insensitive, no-match | Task 2 |
| `tests/core/observability/test_tracing.py` — setup runs, get_tracer returns Tracer, OTLP branch | Task 6 |
| Backward-compatible — cursor/q/limit are optional with defaults | Tasks 3, 4 (all new params use `Query(default=...)`) |
| Run existing test suite first to confirm no breakage | Task 7 Step 2 |
