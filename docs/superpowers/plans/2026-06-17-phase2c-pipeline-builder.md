# Phase 2c: Pipeline Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pipeline configurations fully data-driven — seeded from YAML at startup, served via a CRUD API, and editable in an interactive React Flow graph UI — so operators can clone factory pipelines and customise agent/tier/budget topology without touching code.

**Architecture:** Three-layer vertical: (1) DB schema gains an `is_factory` column; a seeder reads `config/pipeline_configs/*.yaml` and inserts factory rows once at startup; (2) a FastAPI router exposes full CRUD with 403 guards on factory rows and validates `sum(budget_pct) ≤ 100`; (3) the React dashboard replaces the Phase-1 read-only graph with a two-panel layout — left rail for pipeline list, right area for an interactive React Flow editor that calls the CRUD API. A fourth task wires the existing scan-trigger modal to pass the chosen pipeline name.

**Tech Stack:** Python 3.12 · FastAPI 0.111 · Pydantic v2 · SQLAlchemy async 2.0 · PostgreSQL / JSONB · PyYAML · Alembic · React 18 · TypeScript · @xyflow/react 12 · @tanstack/react-query 5 · Tailwind CSS 3

## Global Constraints

- `from __future__ import annotations` in every Python file — no exceptions
- Python ≥ 3.12; Pydantic v2 only (no `.dict()`, use `.model_dump()`)
- All tests use pytest with `asyncio_mode = "auto"` (already set in `pyproject.toml`)
- Factory pipeline configs (`is_factory = True`) must NEVER be overwritten or deleted via API — return HTTP 403
- `sum(budget_pct)` across all nodes in a pipeline definition must not exceed 100 — validate in POST and PUT
- Accenture light theme: `#A100FF` accent, white cards, lock icon on factory configs
- React Flow v12 (`@xyflow/react`) — same version already installed
- No new npm dependencies unless explicitly named in this plan
- DB column addition requires an Alembic migration (not a from-scratch schema reset)
- `is_default` field in YAML is informational only; `is_factory` is the immutability flag

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| **Create** | `core/db/migrations/versions/2a1b3c4d5e6f_add_is_factory_to_pipeline_configs.py` | Alembic migration adding `is_factory` column |
| **Modify** | `core/db/tables.py` | Add `is_factory` column to `PipelineConfigRow` |
| **Create** | `core/db/seed.py` | `seed_pipeline_configs(session)` — idempotent YAML → DB seeder |
| **Modify** | `core/api/app.py` | Add `lifespan` startup that calls the seeder; replace stub `/api/v1/pipelines`; include `pipelines_router` |
| **Create** | `core/api/routers/pipelines.py` | Full CRUD router: list, get, create, update, delete, clone |
| **Create** | `tests/core/api/test_pipelines.py` | Unit tests for all six endpoints |
| **Modify** | `surfaces/dashboard/src/api/client.ts` | Add `PipelineDTO`, `PipelineDetailDTO`, pipeline API calls, extend `TriggerScanRequest` |
| **Create** | `surfaces/dashboard/src/hooks/usePipelineEditor.ts` | `usePipelineEditor` — wraps ReactFlow state, tracks dirty flag, exposes actions |
| **Create** | `surfaces/dashboard/src/pages/pipeline/NodeConfigDrawer.tsx` | 280px slide-in drawer for editing one node's label / agent / tier / budget |
| **Create** | `surfaces/dashboard/src/pages/pipeline/PipelineToolbar.tsx` | Save / Clone / Reset / Delete toolbar row |
| **Modify** | `surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx` | Two-panel layout: pipeline list rail + editable React Flow graph |
| **Modify** | `surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx` | Add "Pipeline" dropdown |

---

## Task 1: DB Migration — Add `is_factory` Column

**Files:**
- Create: `core/db/migrations/versions/2a1b3c4d5e6f_add_is_factory_to_pipeline_configs.py`
- Modify: `core/db/tables.py`

**Interfaces:**
- Produces: `PipelineConfigRow.is_factory: Column(Boolean, default=False)` — consumed by Tasks 2, 3

---

- [ ] **Step 1.1: Write the failing test**

Create `tests/core/test_db.py` already exists — add this test at the bottom (do not delete existing tests):

```python
# append to tests/core/test_db.py
async def test_pipeline_config_row_has_is_factory_column():
    """Confirm the ORM model exposes is_factory before the migration runs."""
    from core.db.tables import PipelineConfigRow
    col_names = [c.key for c in PipelineConfigRow.__table__.columns]
    assert "is_factory" in col_names, f"is_factory missing from columns: {col_names}"
```

- [ ] **Step 1.2: Run to confirm it fails**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
.venv/bin/pytest tests/core/test_db.py::test_pipeline_config_row_has_is_factory_column -v
```

Expected output:
```
FAILED tests/core/test_db.py::test_pipeline_config_row_has_is_factory_column
AssertionError: is_factory missing from columns: ['id', 'name', 'version', ...]
```

- [ ] **Step 1.3: Add `is_factory` column to `PipelineConfigRow` in `core/db/tables.py`**

Open `/Users/rajat.a.ahuja/Dev/Argus/core/db/tables.py`. The `PipelineConfigRow` class currently ends at line 120 with `created_at`. Add one line after `is_default`:

```python
class PipelineConfigRow(Base):
    __tablename__ = "pipeline_configs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False, unique=True)
    version = Column(Integer, default=1)
    definition = Column(JSONB, nullable=False)
    is_default = Column(Boolean, default=False)
    is_factory = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 1.4: Run test to confirm it passes**

```bash
.venv/bin/pytest tests/core/test_db.py::test_pipeline_config_row_has_is_factory_column -v
```

Expected output:
```
PASSED tests/core/test_db.py::test_pipeline_config_row_has_is_factory_column
```

- [ ] **Step 1.5: Create the Alembic migration**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
.venv/bin/alembic revision --autogenerate -m "add_is_factory_to_pipeline_configs"
```

This creates a new file under `core/db/migrations/versions/`. Open that file (the name will contain `add_is_factory_to_pipeline_configs`) and verify the `upgrade()` body contains:

```python
op.add_column('pipeline_configs', sa.Column('is_factory', sa.Boolean(), nullable=True))
```

If the autogenerated body is blank (because Alembic can't connect to the DB in this environment), write the migration manually. Create the file at the path Alembic printed, or create it yourself at `core/db/migrations/versions/2a1b3c4d5e6f_add_is_factory_to_pipeline_configs.py` with this exact content:

```python
# core/db/migrations/versions/2a1b3c4d5e6f_add_is_factory_to_pipeline_configs.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision: str = "2a1b3c4d5e6f"
down_revision: str | None = "1c040f64f366"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_configs",
        sa.Column("is_factory", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("pipeline_configs", "is_factory")
```

- [ ] **Step 1.6: Commit**

```bash
git add core/db/tables.py core/db/migrations/versions/ tests/core/test_db.py
git commit -m "feat(db): add is_factory column to pipeline_configs"
```

---

## Task 2: Pipeline Seeder

**Files:**
- Create: `core/db/seed.py`

**Interfaces:**
- Consumes: `PipelineConfigRow` (Task 1), `config/pipeline_configs/*.yaml` (existing)
- Produces: `seed_pipeline_configs(session: AsyncSession) -> None` — called by Task 3's lifespan hook

---

- [ ] **Step 2.1: Write the failing tests**

Create `tests/core/test_seed.py`:

```python
# tests/core/test_seed.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # row not found → insert
    session.execute = AsyncMock(return_value=result)
    return session


async def test_seed_inserts_factory_rows_for_all_yamls(mock_session):
    """seed_pipeline_configs inserts one row per YAML file that doesn't already exist."""
    from core.db.seed import seed_pipeline_configs
    await seed_pipeline_configs(mock_session)
    # three YAML files exist: full-scan, pr-check, real-time
    assert mock_session.add.call_count == 3


async def test_seed_skips_existing_rows(mock_session):
    """If a row with the same name already exists, seed does not insert a duplicate."""
    existing = MagicMock()  # non-None return from scalar_one_or_none
    mock_session.execute.return_value.scalar_one_or_none.return_value = existing
    from core.db.seed import seed_pipeline_configs
    await seed_pipeline_configs(mock_session)
    mock_session.add.assert_not_called()


async def test_seed_sets_is_factory_true(mock_session):
    """All rows inserted by the seeder have is_factory=True."""
    from core.db.seed import seed_pipeline_configs
    from core.db.tables import PipelineConfigRow
    await seed_pipeline_configs(mock_session)
    for call_args in mock_session.add.call_args_list:
        row: PipelineConfigRow = call_args[0][0]
        assert row.is_factory is True, f"Expected is_factory=True on row '{row.name}'"


async def test_seed_definition_matches_yaml_nodes(mock_session):
    """The definition stored in DB matches the YAML node list for full-scan."""
    from core.db.seed import seed_pipeline_configs
    from core.db.tables import PipelineConfigRow
    await seed_pipeline_configs(mock_session)
    rows_by_name = {
        call_args[0][0].name: call_args[0][0]
        for call_args in mock_session.add.call_args_list
    }
    full_scan = rows_by_name["full-scan"]
    node_ids = [n["id"] for n in full_scan.definition["nodes"]]
    assert "ingestion" in node_ids
    assert "triage" in node_ids
```

- [ ] **Step 2.2: Run to confirm they fail**

```bash
.venv/bin/pytest tests/core/test_seed.py -v
```

Expected output:
```
FAILED tests/core/test_seed.py::test_seed_inserts_factory_rows_for_all_yamls
ModuleNotFoundError: No module named 'core.db.seed'
```

- [ ] **Step 2.3: Implement `core/db/seed.py`**

```python
# core/db/seed.py
from __future__ import annotations
from pathlib import Path
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.tables import PipelineConfigRow

_CONFIGS_DIR = Path(__file__).parent.parent.parent / "config" / "pipeline_configs"


async def seed_pipeline_configs(session: AsyncSession) -> None:
    """Insert factory pipeline configs from YAML files if they don't already exist.

    Idempotent: existing rows (matched by name) are never overwritten.
    All inserted rows have is_factory=True.
    """
    for yaml_path in sorted(_CONFIGS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text())
        name: str = data["name"]

        result = await session.execute(
            select(PipelineConfigRow).where(PipelineConfigRow.name == name)
        )
        if result.scalar_one_or_none() is not None:
            continue

        definition = {
            "nodes": [
                {
                    "id": n["id"],
                    "agent": n["agent"],
                    "tier": n["tier"],
                    "budget_pct": n.get("budget_pct", 0),
                }
                for n in data.get("nodes", [])
            ],
            "edges": [
                {
                    "from": e["from"],
                    "to": e["to"],
                    "condition": e.get("condition"),
                }
                for e in data.get("edges", [])
            ],
        }
        row = PipelineConfigRow(
            name=name,
            version=data.get("version", 1),
            definition=definition,
            is_default=data.get("is_default", False),
            is_factory=True,
        )
        session.add(row)
```

- [ ] **Step 2.4: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/core/test_seed.py -v
```

Expected output:
```
PASSED tests/core/test_seed.py::test_seed_inserts_factory_rows_for_all_yamls
PASSED tests/core/test_seed.py::test_seed_skips_existing_rows
PASSED tests/core/test_seed.py::test_seed_sets_is_factory_true
PASSED tests/core/test_seed.py::test_seed_definition_matches_yaml_nodes
```

- [ ] **Step 2.5: Commit**

```bash
git add core/db/seed.py tests/core/test_seed.py
git commit -m "feat(db): add pipeline config seeder from YAML factory files"
```

---

## Task 3: Wire Seeder Into App Startup

**Files:**
- Modify: `core/api/app.py`

**Interfaces:**
- Consumes: `seed_pipeline_configs` (Task 2)
- Produces: seeder is called once on startup; stub `GET /api/v1/pipelines` stub is removed (will be replaced in Task 4)

---

- [ ] **Step 3.1: Write the failing test**

Add to `tests/core/api/test_scans.py` (do not delete existing tests):

```python
# append to tests/core/api/test_scans.py
async def test_startup_calls_seed(monkeypatch):
    """App lifespan calls seed_pipeline_configs exactly once on startup."""
    calls = []

    async def fake_seed(session):
        calls.append(session)

    monkeypatch.setattr("core.db.seed.seed_pipeline_configs", fake_seed)

    from httpx import AsyncClient, ASGITransport
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/api/v1/health")

    assert len(calls) == 1, f"Expected 1 seed call, got {len(calls)}"
```

- [ ] **Step 3.2: Run to confirm it fails**

```bash
.venv/bin/pytest tests/core/api/test_scans.py::test_startup_calls_seed -v
```

Expected output:
```
FAILED tests/core/api/test_scans.py::test_startup_calls_seed
AssertionError: Expected 1 seed call, got 0
```

- [ ] **Step 3.3: Rewrite `core/api/app.py` to add lifespan and remove the stub**

Replace the entire file content:

```python
# core/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from core.db.seed import seed_pipeline_configs
    from core.db.session import get_session
    async with get_session() as session:
        await seed_pipeline_configs(session)
    yield


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus
    app = FastAPI(
        title="Argus Security Platform",
        version="0.1.0",
        docs_url="/docs",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    @app.get("/api/v1/fixes/{fix_id}")
    async def get_fix(fix_id: UUID):
        from fastapi import HTTPException
        raise HTTPException(501, "Fix generation available in Phase 2")

    return app


# Module-level instance for uvicorn
app = create_app()
```

**Note:** `GET /api/v1/pipelines` stub is intentionally removed here — Task 4 replaces it with the real router.

- [ ] **Step 3.4: Run test to confirm it passes**

The test monkeypatches the seed function so no DB connection is needed:

```bash
.venv/bin/pytest tests/core/api/test_scans.py::test_startup_calls_seed -v
```

Expected output:
```
PASSED tests/core/api/test_scans.py::test_startup_calls_seed
```

- [ ] **Step 3.5: Run all existing API tests to confirm nothing is broken**

```bash
.venv/bin/pytest tests/core/api/ -v
```

Expected output: all previously passing tests still pass.

- [ ] **Step 3.6: Commit**

```bash
git add core/api/app.py tests/core/api/test_scans.py
git commit -m "feat(api): wire seeder into app startup via lifespan"
```

---

## Task 4: Pipeline CRUD API Router

**Files:**
- Create: `core/api/routers/pipelines.py`
- Modify: `core/api/app.py` (add `include_router` call)
- Create: `tests/core/api/test_pipelines.py`

**Interfaces:**
- Consumes: `PipelineConfigRow` (Task 1), `PipelineDefinition`, `PipelineNodeConfig`, `PipelineEdge` from `core.model.entities`
- Produces:
  - `GET /api/v1/pipelines` → `list[PipelineListItem]`
  - `GET /api/v1/pipelines/{id}` → `PipelineDetailResponse`
  - `POST /api/v1/pipelines` → `PipelineDetailResponse` (201)
  - `PUT /api/v1/pipelines/{id}` → `PipelineDetailResponse` (or 403)
  - `DELETE /api/v1/pipelines/{id}` → 204 (or 403)
  - `POST /api/v1/pipelines/{id}/clone` → `PipelineDetailResponse` (201)

---

- [ ] **Step 4.1: Write the failing tests**

Create `tests/core/api/test_pipelines.py`:

```python
# tests/core/api/test_pipelines.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ── helpers ────────────────────────────────────────────────────────────────

def _make_row(
    name: str = "test-pipe",
    is_factory: bool = False,
    is_default: bool = False,
    version: int = 1,
) -> MagicMock:
    row = MagicMock()
    row.id = str(uuid4())
    row.name = name
    row.version = version
    row.is_default = is_default
    row.is_factory = is_factory
    row.created_at = None
    row.definition = {
        "nodes": [
            {"id": "ingestion", "agent": "IngestionAgent", "tier": "fast", "budget_pct": 5},
            {"id": "triage",    "agent": "TriageAgent",    "tier": "balanced", "budget_pct": 40},
        ],
        "edges": [{"from": "ingestion", "to": "triage", "condition": None}],
    }
    return row


VALID_DEFINITION = {
    "nodes": [
        {"id": "ingestion", "agent": "IngestionAgent", "tier": "fast", "budget_pct": 5},
        {"id": "triage",    "agent": "TriageAgent",    "tier": "balanced", "budget_pct": 40},
    ],
    "edges": [{"from": "ingestion", "to": "triage", "condition": None}],
}


# ── fixture ────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    # Patch lifespan seed so no DB is needed at startup
    async def _noop_seed(session):
        pass

    with patch("core.db.seed.seed_pipeline_configs", _noop_seed):
        from core.api.app import create_app
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


# ── GET /api/v1/pipelines ──────────────────────────────────────────────────

async def test_list_pipelines_returns_list(client):
    rows = [_make_row("full-scan", is_factory=True), _make_row("my-pipe")]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows

    with patch("core.api.routers.pipelines.get_db") as mock_get_db:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_db.return_value = mock_session

        async def _override():
            yield mock_session

        from core.api.app import create_app
        from core.api.routers.pipelines import router
        from core.api.deps import get_db

        # Use the app's dependency override mechanism
        app = create_app()
        app.dependency_overrides[get_db] = _override  # type: ignore[index]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/pipelines")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


async def test_list_pipelines_includes_node_count(client):
    rows = [_make_row("full-scan", is_factory=True)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/pipelines")

    assert resp.status_code == 200
    items = resp.json()
    assert items[0]["node_count"] == 2
    assert items[0]["is_factory"] is True


# ── GET /api/v1/pipelines/{id} ─────────────────────────────────────────────

async def test_get_pipeline_returns_definition():
    row = _make_row("full-scan", is_factory=True)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/pipelines/{row.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert "definition" in body
    assert body["is_factory"] is True


async def test_get_pipeline_404_when_missing():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/pipelines/{uuid4()}")

    assert resp.status_code == 404


# ── POST /api/v1/pipelines ─────────────────────────────────────────────────

async def test_create_pipeline_returns_201():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # name not taken

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/pipelines",
            json={"name": "custom-pipe", "definition": VALID_DEFINITION},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "custom-pipe"
    assert body["is_factory"] is False


async def test_create_pipeline_rejects_budget_over_100():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    bad_definition = {
        "nodes": [
            {"id": "a", "agent": "TriageAgent", "tier": "balanced", "budget_pct": 60},
            {"id": "b", "agent": "ExplainerAgent", "tier": "fast", "budget_pct": 60},
        ],
        "edges": [],
    }

    async def _override():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/pipelines",
            json={"name": "over-budget", "definition": bad_definition},
        )

    assert resp.status_code == 422
    assert "budget_pct" in resp.text.lower()


# ── PUT /api/v1/pipelines/{id} ─────────────────────────────────────────────

async def test_update_factory_pipeline_returns_403():
    row = _make_row("full-scan", is_factory=True)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.put(
            f"/api/v1/pipelines/{row.id}",
            json={"definition": VALID_DEFINITION},
        )

    assert resp.status_code == 403


async def test_update_user_pipeline_bumps_version():
    row = _make_row("my-pipe", is_factory=False, version=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.put(
            f"/api/v1/pipelines/{row.id}",
            json={"definition": VALID_DEFINITION},
        )

    assert resp.status_code == 200
    assert resp.json()["version"] == 2


# ── DELETE /api/v1/pipelines/{id} ─────────────────────────────────────────

async def test_delete_factory_pipeline_returns_403():
    row = _make_row("full-scan", is_factory=True)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/pipelines/{row.id}")

    assert resp.status_code == 403


async def test_delete_user_pipeline_returns_204():
    row = _make_row("my-pipe", is_factory=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/pipelines/{row.id}")

    assert resp.status_code == 204


# ── POST /api/v1/pipelines/{id}/clone ─────────────────────────────────────

async def test_clone_factory_pipeline_creates_editable_copy():
    source = _make_row("full-scan", is_factory=True)
    name_check = MagicMock()
    name_check.scalar_one_or_none.return_value = None  # new name is free

    source_result = MagicMock()
    source_result.scalar_one_or_none.return_value = source

    call_count = 0

    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def _override():
        mock_session = AsyncMock()

        async def _execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return source_result   # fetch original
            return name_check          # name uniqueness check

        mock_session.execute = _execute
        yield mock_session

    app.dependency_overrides[get_db] = _override  # type: ignore[index]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/pipelines/{source.id}/clone",
            json={"name": "my-custom-scan"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-custom-scan"
    assert body["is_factory"] is False
```

- [ ] **Step 4.2: Run to confirm they fail**

```bash
.venv/bin/pytest tests/core/api/test_pipelines.py -v 2>&1 | head -40
```

Expected output:
```
FAILED ... ImportError: cannot import name 'pipelines' from 'core.api.routers'
```

- [ ] **Step 4.3: Implement `core/api/routers/pipelines.py`**

```python
# core/api/routers/pipelines.py
from __future__ import annotations
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
from core.api.deps import get_db
from core.db.tables import PipelineConfigRow
from core.model.entities import PipelineDefinition

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# ── request / response schemas ────────────────────────────────────────────

class PipelineListItem(BaseModel):
    id: str
    name: str
    version: int
    is_default: bool
    is_factory: bool
    node_count: int
    created_at: datetime | None


class PipelineDetailResponse(BaseModel):
    id: str
    name: str
    version: int
    is_default: bool
    is_factory: bool
    definition: dict[str, Any]
    created_at: datetime | None


class CreatePipelineRequest(BaseModel):
    name: str
    definition: dict[str, Any]
    is_default: bool = False

    @field_validator("definition")
    @classmethod
    def budget_pct_must_not_exceed_100(cls, v: dict[str, Any]) -> dict[str, Any]:
        nodes = v.get("nodes", [])
        total = sum(n.get("budget_pct", 0) for n in nodes)
        if total > 100:
            raise ValueError(
                f"total budget_pct across all nodes is {total}, must not exceed 100"
            )
        return v


class UpdatePipelineRequest(BaseModel):
    definition: dict[str, Any]
    is_default: bool | None = None

    @field_validator("definition")
    @classmethod
    def budget_pct_must_not_exceed_100(cls, v: dict[str, Any]) -> dict[str, Any]:
        nodes = v.get("nodes", [])
        total = sum(n.get("budget_pct", 0) for n in nodes)
        if total > 100:
            raise ValueError(
                f"total budget_pct across all nodes is {total}, must not exceed 100"
            )
        return v


class ClonePipelineRequest(BaseModel):
    name: str


# ── helpers ───────────────────────────────────────────────────────────────

def _row_to_list_item(row: PipelineConfigRow) -> PipelineListItem:
    node_count = len((row.definition or {}).get("nodes", []))
    return PipelineListItem(
        id=row.id,
        name=row.name,
        version=row.version,
        is_default=row.is_default,
        is_factory=row.is_factory,
        node_count=node_count,
        created_at=row.created_at,
    )


def _row_to_detail(row: PipelineConfigRow) -> PipelineDetailResponse:
    return PipelineDetailResponse(
        id=row.id,
        name=row.name,
        version=row.version,
        is_default=row.is_default,
        is_factory=row.is_factory,
        definition=row.definition,
        created_at=row.created_at,
    )


async def _get_or_404(pipeline_id: UUID, db: AsyncSession) -> PipelineConfigRow:
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.id == str(pipeline_id))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return row


# ── endpoints ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[PipelineListItem])
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineConfigRow).order_by(PipelineConfigRow.name))
    rows = result.scalars().all()
    return [_row_to_list_item(r) for r in rows]


@router.get("/{pipeline_id}", response_model=PipelineDetailResponse)
async def get_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await _get_or_404(pipeline_id, db)
    return _row_to_detail(row)


@router.post("/", response_model=PipelineDetailResponse, status_code=201)
async def create_pipeline(
    body: CreatePipelineRequest,
    db: AsyncSession = Depends(get_db),
):
    # Check name uniqueness
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.name == body.name)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Pipeline '{body.name}' already exists")

    row = PipelineConfigRow(
        id=str(uuid4()),
        name=body.name,
        version=1,
        definition=body.definition,
        is_default=body.is_default,
        is_factory=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return _row_to_detail(row)


@router.put("/{pipeline_id}", response_model=PipelineDetailResponse)
async def update_pipeline(
    pipeline_id: UUID,
    body: UpdatePipelineRequest,
    db: AsyncSession = Depends(get_db),
):
    row = await _get_or_404(pipeline_id, db)
    if row.is_factory:
        raise HTTPException(status_code=403, detail="Factory pipelines are read-only")

    row.definition = body.definition
    row.version = row.version + 1
    if body.is_default is not None:
        row.is_default = body.is_default
    await db.flush()
    return _row_to_detail(row)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await _get_or_404(pipeline_id, db)
    if row.is_factory:
        raise HTTPException(status_code=403, detail="Factory pipelines cannot be deleted")
    await db.delete(row)


@router.post("/{pipeline_id}/clone", response_model=PipelineDetailResponse, status_code=201)
async def clone_pipeline(
    pipeline_id: UUID,
    body: ClonePipelineRequest,
    db: AsyncSession = Depends(get_db),
):
    source = await _get_or_404(pipeline_id, db)

    # Check name uniqueness
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.name == body.name)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Pipeline '{body.name}' already exists")

    new_row = PipelineConfigRow(
        id=str(uuid4()),
        name=body.name,
        version=1,
        definition=source.definition,
        is_default=False,
        is_factory=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_row)
    await db.flush()
    return _row_to_detail(new_row)
```

- [ ] **Step 4.4: Register the router in `core/api/app.py`**

Add two lines to `create_app` in `/Users/rajat.a.ahuja/Dev/Argus/core/api/app.py`. After the existing `from core.api.routers.cost import router as cost_router` import line, add:

```python
from core.api.routers.pipelines import router as pipelines_router
```

And after `app.include_router(cost_router, prefix="/api/v1")`, add:

```python
    app.include_router(pipelines_router, prefix="/api/v1")
```

The full imports block at the top of `app.py` should now read:

```python
# core/api/app.py
from __future__ import annotations
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.routers.pipelines import router as pipelines_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus
```

And `create_app` includes:

```python
    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")
    app.include_router(pipelines_router, prefix="/api/v1")
```

- [ ] **Step 4.5: Run all pipeline tests**

```bash
.venv/bin/pytest tests/core/api/test_pipelines.py -v
```

Expected output:
```
PASSED tests/core/api/test_pipelines.py::test_list_pipelines_returns_list
PASSED tests/core/api/test_pipelines.py::test_list_pipelines_includes_node_count
PASSED tests/core/api/test_pipelines.py::test_get_pipeline_returns_definition
PASSED tests/core/api/test_pipelines.py::test_get_pipeline_404_when_missing
PASSED tests/core/api/test_pipelines.py::test_create_pipeline_returns_201
PASSED tests/core/api/test_pipelines.py::test_create_pipeline_rejects_budget_over_100
PASSED tests/core/api/test_pipelines.py::test_update_factory_pipeline_returns_403
PASSED tests/core/api/test_pipelines.py::test_update_user_pipeline_bumps_version
PASSED tests/core/api/test_pipelines.py::test_delete_factory_pipeline_returns_403
PASSED tests/core/api/test_pipelines.py::test_delete_user_pipeline_returns_204
PASSED tests/core/api/test_pipelines.py::test_clone_factory_pipeline_creates_editable_copy
```

- [ ] **Step 4.6: Run the full test suite to check for regressions**

```bash
.venv/bin/pytest tests/core/ -v --ignore=tests/e2e
```

Expected: all tests pass.

- [ ] **Step 4.7: Commit**

```bash
git add core/api/routers/pipelines.py core/api/app.py tests/core/api/test_pipelines.py
git commit -m "feat(api): add pipeline CRUD router with factory guard and budget validation"
```

---

## Task 5: Frontend — API Client Types and Calls

**Files:**
- Modify: `surfaces/dashboard/src/api/client.ts`

**Interfaces:**
- Produces:
  - `PipelineListItem` TS interface
  - `PipelineDetailDTO` TS interface  
  - `NodeConfigDTO` TS interface
  - `EdgeDTO` TS interface
  - `api.listPipelines()` → `Promise<PipelineListItem[]>`
  - `api.getPipeline(id)` → `Promise<PipelineDetailDTO>`
  - `api.createPipeline(body)` → `Promise<PipelineDetailDTO>`
  - `api.updatePipeline(id, body)` → `Promise<PipelineDetailDTO>`
  - `api.deletePipeline(id)` → `Promise<void>`
  - `api.clonePipeline(id, name)` → `Promise<PipelineDetailDTO>`
  - `TriggerScanRequest.pipeline_config_name` field added

---

- [ ] **Step 5.1: No automated test for client.ts — verify via TypeScript compiler**

TypeScript type-checking is the test here. Run before making changes to capture the current baseline:

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -5
```

Expected: build succeeds (exit 0). If it fails, note the existing errors before continuing.

- [ ] **Step 5.2: Update `surfaces/dashboard/src/api/client.ts`**

Replace the entire file with:

```typescript
// surfaces/dashboard/src/api/client.ts
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type SecurityApproach =
  | "penetration_testing"
  | "adversary_emulation"
  | "breach_and_attack_simulation"
  | "assumed_breach"
  | "blue_team"
  | "purple_team";

export const APPROACH_LABELS: Record<SecurityApproach, string> = {
  penetration_testing: "Penetration Testing",
  adversary_emulation: "Adversary Emulation",
  breach_and_attack_simulation: "Breach & Attack Simulation",
  assumed_breach: "Assumed Breach",
  blue_team: "Blue Team",
  purple_team: "Purple Team",
};

export const APPROACH_DESCRIPTIONS: Record<SecurityApproach, string> = {
  penetration_testing: "Breadth-first: find and exploit all vulnerabilities in scope",
  adversary_emulation: "Replay threat actor TTPs mapped to MITRE ATT&CK",
  breach_and_attack_simulation: "Validate controls: would WAF/SIEM/EDR catch this?",
  assumed_breach: "Post-compromise: lateral movement, privilege escalation, persistence",
  blue_team: "Defensive: detection engineering, hardening, control gap analysis",
  purple_team: "Red + blue feedback loop: every attack paired with a detection rule",
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

// ── DTOs ──────────────────────────────────────────────────────────────────

export interface FindingDTO {
  id: string;
  rule_id: string;
  source_tool: string;
  cwe: string | null;
  owasp_category: string | null;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: number;
  exploit_likelihood: number;
  reachability: string | null;
  location: { file: string; line_start: number; line_end: number; snippet?: string };
  status: string;
  explanation: string | null;
  attack_scenario?: string;
  priority_score?: number;
}

export interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  approach: SecurityApproach;
  cost_usd: number;
  started_at: string | null;
}

export interface CostEntryDTO {
  id: string;
  scope_type: string;
  scope_id: string;
  tokens_in: number;
  tokens_out: number;
  tier: string;
  provider: string;
  model_id: string;
  cost_usd: number;
  timestamp: string;
}

export type ModelTier = "fast" | "balanced" | "top" | "none";

export interface NodeConfigDTO {
  id: string;
  agent: string;
  tier: ModelTier;
  budget_pct: number;
}

export interface EdgeDTO {
  from: string;
  to: string;
  condition: string | null;
}

export interface PipelineDefinitionDTO {
  nodes: NodeConfigDTO[];
  edges: EdgeDTO[];
}

export interface PipelineListItem {
  id: string;
  name: string;
  version: number;
  is_default: boolean;
  is_factory: boolean;
  node_count: number;
  created_at: string | null;
}

export interface PipelineDetailDTO {
  id: string;
  name: string;
  version: number;
  is_default: boolean;
  is_factory: boolean;
  definition: PipelineDefinitionDTO;
  created_at: string | null;
}

export interface TriggerScanRequest {
  target_ref: string;
  mode?: string;
  approach?: SecurityApproach;
  pipeline_config_name?: string;
}

// ── API calls ─────────────────────────────────────────────────────────────

export const api = {
  // scans
  listScans: () => get<ScanDTO[]>("/api/v1/scans/"),
  triggerScan: (body: TriggerScanRequest) =>
    post<{ scan_id: string }>("/api/v1/scans/", body),
  getScanFindings: (scanId: string) =>
    get<FindingDTO[]>(`/api/v1/scans/${scanId}/findings`),

  // cost
  getCostLedger: () => get<CostEntryDTO[]>("/api/v1/cost/ledger"),
  getCostSummary: () =>
    get<{ total_cost_usd: number; total_tokens_in: number; total_calls: number }>(
      "/api/v1/cost/summary"
    ),

  // pipelines
  listPipelines: () => get<PipelineListItem[]>("/api/v1/pipelines/"),
  getPipeline: (id: string) => get<PipelineDetailDTO>(`/api/v1/pipelines/${id}`),
  createPipeline: (body: { name: string; definition: PipelineDefinitionDTO; is_default?: boolean }) =>
    post<PipelineDetailDTO>("/api/v1/pipelines/", body),
  updatePipeline: (id: string, body: { definition: PipelineDefinitionDTO; is_default?: boolean }) =>
    put<PipelineDetailDTO>(`/api/v1/pipelines/${id}`, body),
  deletePipeline: (id: string) => del(`/api/v1/pipelines/${id}`),
  clonePipeline: (id: string, name: string) =>
    post<PipelineDetailDTO>(`/api/v1/pipelines/${id}/clone`, { name }),
};
```

- [ ] **Step 5.3: Confirm TypeScript compiles**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -10
```

Expected: `✓ built in` with exit code 0. Fix any type errors before continuing.

- [ ] **Step 5.4: Commit**

```bash
git add surfaces/dashboard/src/api/client.ts
git commit -m "feat(ui): add pipeline DTO types and CRUD API calls to client"
```

---

## Task 6: `usePipelineEditor` Hook

**Files:**
- Create: `surfaces/dashboard/src/hooks/usePipelineEditor.ts`

**Interfaces:**
- Consumes: `PipelineDetailDTO`, `NodeConfigDTO`, `EdgeDTO` from `client.ts` (Task 5)
- Produces:
  ```typescript
  usePipelineEditor(pipeline: PipelineDetailDTO | null): {
    nodes: Node[];
    edges: Edge[];
    isDirty: boolean;
    selectedNodeId: string | null;
    onNodesChange: (changes: NodeChange[]) => void;
    onEdgesChange: (changes: EdgeChange[]) => void;
    selectNode: (id: string | null) => void;
    updateNode: (id: string, data: Partial<AgentNodeData>) => void;
    removeNode: (id: string) => void;
    addEdge: (edge: Edge) => void;
    resetToSaved: () => void;
    toPipelineDefinition: () => PipelineDefinitionDTO;
  }
  ```

---

- [ ] **Step 6.1: No automated test — verify via TypeScript compilation**

This hook will be type-checked when `PipelinePage.tsx` is updated in Task 7. For now, TypeScript compilation in Step 6.3 confirms correctness.

- [ ] **Step 6.2: Create `surfaces/dashboard/src/hooks/usePipelineEditor.ts`**

```typescript
// surfaces/dashboard/src/hooks/usePipelineEditor.ts
import { useCallback, useEffect, useState } from "react";
import {
  Node,
  Edge,
  NodeChange,
  EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge as rfAddEdge,
  Connection,
} from "@xyflow/react";
import { PipelineDetailDTO, PipelineDefinitionDTO, ModelTier } from "../api/client";

export interface AgentNodeData {
  label: string;
  agent: string;
  tier: ModelTier;
  budget_pct: number;
  [key: string]: unknown;
}

// Layout nodes left-to-right with a simple column assignment based on
// topology order. Falls back to grid if no edges exist.
function layoutNodes(
  nodeDefs: PipelineDetailDTO["definition"]["nodes"],
  edges: PipelineDetailDTO["definition"]["edges"]
): Node<AgentNodeData>[] {
  // Build an in-degree map to sort columns
  const inDegree: Record<string, number> = {};
  for (const n of nodeDefs) inDegree[n.id] = 0;
  for (const e of edges) {
    if (e.to in inDegree) inDegree[e.to]++;
  }

  // BFS-style column assignment
  const col: Record<string, number> = {};
  const queue = nodeDefs.filter((n) => inDegree[n.id] === 0).map((n) => n.id);
  let colIndex = 0;
  const visited = new Set<string>();
  while (queue.length > 0) {
    const batch = [...queue];
    queue.length = 0;
    for (const id of batch) {
      if (visited.has(id)) continue;
      visited.add(id);
      col[id] = colIndex;
      for (const e of edges) {
        if (e.from === id && !visited.has(e.to)) queue.push(e.to);
      }
    }
    colIndex++;
  }
  // Anything still unvisited goes in last column
  for (const n of nodeDefs) {
    if (!(n.id in col)) col[n.id] = colIndex;
  }

  // Count nodes per column for vertical spacing
  const colCounts: Record<number, number> = {};
  const colOffset: Record<number, number> = {};
  for (const n of nodeDefs) {
    const c = col[n.id] ?? 0;
    colCounts[c] = (colCounts[c] ?? 0) + 1;
  }
  const colRow: Record<number, number> = {};

  return nodeDefs.map((n) => {
    const c = col[n.id] ?? 0;
    const rowInCol = colRow[c] ?? 0;
    colRow[c] = rowInCol + 1;
    const total = colCounts[c] ?? 1;
    const y = (rowInCol - (total - 1) / 2) * 120 + 150;
    return {
      id: n.id,
      type: "agent",
      position: { x: c * 220, y },
      data: {
        label: n.id.charAt(0).toUpperCase() + n.id.slice(1),
        agent: n.agent,
        tier: n.tier,
        budget_pct: n.budget_pct,
      },
    };
  });
}

function toRfEdges(
  edges: PipelineDetailDTO["definition"]["edges"]
): Edge[] {
  return edges.map((e, i) => ({
    id: `e-${e.from}-${e.to}-${i}`,
    source: e.from,
    target: e.to,
    style: { stroke: "#D1D5DB", strokeWidth: 1.5 },
  }));
}

export function usePipelineEditor(pipeline: PipelineDetailDTO | null) {
  const [savedNodes, setSavedNodes] = useState<Node<AgentNodeData>[]>([]);
  const [savedEdges, setSavedEdges] = useState<Edge[]>([]);
  const [nodes, setNodes] = useState<Node<AgentNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [isDirty, setIsDirty] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    if (!pipeline) return;
    const n = layoutNodes(pipeline.definition.nodes, pipeline.definition.edges);
    const e = toRfEdges(pipeline.definition.edges);
    setSavedNodes(n);
    setSavedEdges(e);
    setNodes(n);
    setEdges(e);
    setIsDirty(false);
    setSelectedNodeId(null);
  }, [pipeline?.id]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((prev) => applyNodeChanges(changes, prev) as Node<AgentNodeData>[]);
    setIsDirty(true);
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((prev) => applyEdgeChanges(changes, prev));
    setIsDirty(true);
  }, []);

  const selectNode = useCallback((id: string | null) => {
    setSelectedNodeId(id);
  }, []);

  const updateNode = useCallback(
    (id: string, data: Partial<AgentNodeData>) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === id ? { ...n, data: { ...n.data, ...data } } : n
        )
      );
      setIsDirty(true);
    },
    []
  );

  const removeNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
    setEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id));
    setSelectedNodeId((prev) => (prev === id ? null : prev));
    setIsDirty(true);
  }, []);

  const addEdge = useCallback((connection: Connection | Edge) => {
    setEdges((prev) =>
      rfAddEdge(
        { ...connection, style: { stroke: "#D1D5DB", strokeWidth: 1.5 } },
        prev
      )
    );
    setIsDirty(true);
  }, []);

  const resetToSaved = useCallback(() => {
    setNodes(savedNodes);
    setEdges(savedEdges);
    setIsDirty(false);
    setSelectedNodeId(null);
  }, [savedNodes, savedEdges]);

  const toPipelineDefinition = useCallback((): PipelineDefinitionDTO => {
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        agent: n.data.agent,
        tier: n.data.tier,
        budget_pct: n.data.budget_pct,
      })),
      edges: edges.map((e) => ({
        from: e.source,
        to: e.target,
        condition: null,
      })),
    };
  }, [nodes, edges]);

  return {
    nodes,
    edges,
    isDirty,
    selectedNodeId,
    onNodesChange,
    onEdgesChange,
    selectNode,
    updateNode,
    removeNode,
    addEdge,
    resetToSaved,
    toPipelineDefinition,
  };
}
```

- [ ] **Step 6.3: Verify TypeScript compilation**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -10
```

Expected: exit 0. Fix any type errors.

- [ ] **Step 6.4: Commit**

```bash
git add surfaces/dashboard/src/hooks/usePipelineEditor.ts
git commit -m "feat(ui): add usePipelineEditor hook for pipeline graph state management"
```

---

## Task 7: `NodeConfigDrawer` Component

**Files:**
- Create: `surfaces/dashboard/src/pages/pipeline/NodeConfigDrawer.tsx`

**Interfaces:**
- Consumes: `AgentNodeData`, `updateNode`, `removeNode`, `selectNode` from `usePipelineEditor` (Task 6)
- Produces:
  ```typescript
  <NodeConfigDrawer
    nodeId: string
    data: AgentNodeData
    allNodes: Node<AgentNodeData>[]
    onUpdate: (id: string, data: Partial<AgentNodeData>) => void
    onRemove: (id: string) => void
    onClose: () => void
    isFactory: boolean
  />
  ```

---

- [ ] **Step 7.1: Create `surfaces/dashboard/src/pages/pipeline/NodeConfigDrawer.tsx`**

```tsx
// surfaces/dashboard/src/pages/pipeline/NodeConfigDrawer.tsx
import { useState } from "react";
import { Node } from "@xyflow/react";
import { AgentNodeData } from "../../hooks/usePipelineEditor";
import { ModelTier } from "../../api/client";

const AGENTS = [
  "IngestionAgent",
  "SemgrepAdapter",
  "TruffleHogAdapter",
  "TriageAgent",
  "ExplainerAgent",
  "FixAgent",
] as const;

const TIERS: { value: ModelTier; label: string; dot: string }[] = [
  { value: "fast",     label: "Fast",          dot: "#A100FF" },
  { value: "balanced", label: "Balanced",       dot: "#F59E0B" },
  { value: "top",      label: "Top",            dot: "#EF4444" },
  { value: "none",     label: "Deterministic",  dot: "#9CA3AF" },
];

interface Props {
  nodeId: string;
  data: AgentNodeData;
  allNodes: Node<AgentNodeData>[];
  onUpdate: (id: string, data: Partial<AgentNodeData>) => void;
  onRemove: (id: string) => void;
  onClose: () => void;
  isFactory: boolean;
}

export function NodeConfigDrawer({
  nodeId,
  data,
  allNodes,
  onUpdate,
  onRemove,
  onClose,
  isFactory,
}: Props) {
  const [label, setLabel] = useState(data.label);
  const [agent, setAgent] = useState(data.agent);
  const [tier, setTier] = useState<ModelTier>(data.tier);
  const [budgetPct, setBudgetPct] = useState(data.budget_pct);

  const otherBudget = allNodes
    .filter((n) => n.id !== nodeId)
    .reduce((sum, n) => sum + (n.data.budget_pct ?? 0), 0);
  const remaining = 100 - otherBudget;

  function handleApply() {
    onUpdate(nodeId, { label, agent, tier, budget_pct: budgetPct });
    onClose();
  }

  return (
    <div
      className="absolute top-0 right-0 h-full bg-white border-l border-gray-100 shadow-xl flex flex-col z-10"
      style={{ width: 280 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <span className="text-sm font-bold text-gray-900">Node Config</span>
        <button
          onClick={onClose}
          className="w-7 h-7 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center text-gray-500 text-lg leading-none"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4">
        {/* Label */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Label
          </label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:border-transparent disabled:opacity-50 disabled:bg-gray-50"
            style={{ ["--tw-ring-color" as string]: "#A100FF" }}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={isFactory}
          />
        </div>

        {/* Agent */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Agent
          </label>
          <select
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:border-transparent disabled:opacity-50 disabled:bg-gray-50 bg-white"
            style={{ ["--tw-ring-color" as string]: "#A100FF" }}
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            disabled={isFactory}
          >
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>

        {/* Tier */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Tier
          </label>
          <div className="flex flex-col gap-1.5">
            {TIERS.map((t) => (
              <label
                key={t.value}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border cursor-pointer transition-all ${
                  tier === t.value
                    ? "border-[#A100FF] bg-accent-50"
                    : "border-gray-100 bg-gray-50 hover:border-gray-200"
                } ${isFactory ? "pointer-events-none opacity-60" : ""}`}
              >
                <input
                  type="radio"
                  name="tier"
                  value={t.value}
                  checked={tier === t.value}
                  onChange={() => setTier(t.value)}
                  disabled={isFactory}
                  className="sr-only"
                />
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ background: t.dot }}
                />
                <span className={`text-sm font-medium ${tier === t.value ? "text-[#A100FF]" : "text-gray-700"}`}>
                  {t.label}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Budget */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Budget %
          </label>
          <input
            type="number"
            min={0}
            max={remaining}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:border-transparent disabled:opacity-50 disabled:bg-gray-50"
            style={{ ["--tw-ring-color" as string]: "#A100FF" }}
            value={budgetPct}
            onChange={(e) => setBudgetPct(Math.min(remaining, Math.max(0, Number(e.target.value))))}
            disabled={isFactory}
          />
          <p className="text-xs text-gray-400 mt-1">
            {remaining - budgetPct}% remaining across pipeline
          </p>
        </div>
      </div>

      {/* Footer actions */}
      {!isFactory && (
        <div className="px-4 py-3 border-t border-gray-100 flex flex-col gap-2">
          <button
            onClick={handleApply}
            className="w-full text-white font-semibold rounded-xl py-2.5 text-sm transition-all"
            style={{ background: "#A100FF" }}
            onMouseOver={(e) => { e.currentTarget.style.background = "#8200CC"; }}
            onMouseOut={(e) => { e.currentTarget.style.background = "#A100FF"; }}
          >
            Apply
          </button>
          <button
            onClick={() => { onRemove(nodeId); onClose(); }}
            className="w-full font-semibold rounded-xl py-2.5 text-sm border border-red-200 text-red-600 hover:bg-red-50 transition-all"
          >
            Remove Node
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7.2: Verify TypeScript compilation**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -10
```

Expected: exit 0.

- [ ] **Step 7.3: Commit**

```bash
git add surfaces/dashboard/src/pages/pipeline/NodeConfigDrawer.tsx
git commit -m "feat(ui): add NodeConfigDrawer slide-in panel for node editing"
```

---

## Task 8: `PipelineToolbar` Component

**Files:**
- Create: `surfaces/dashboard/src/pages/pipeline/PipelineToolbar.tsx`

**Interfaces:**
- Consumes: `isDirty` from `usePipelineEditor` (Task 6)
- Produces:
  ```typescript
  <PipelineToolbar
    pipelineId: string
    pipelineName: string
    isFactory: boolean
    isDirty: boolean
    isSaving: boolean
    onSave: () => void
    onClone: () => void
    onReset: () => void
    onDelete: () => void
  />
  ```

---

- [ ] **Step 8.1: Create `surfaces/dashboard/src/pages/pipeline/PipelineToolbar.tsx`**

```tsx
// surfaces/dashboard/src/pages/pipeline/PipelineToolbar.tsx
interface Props {
  pipelineName: string;
  isFactory: boolean;
  isDirty: boolean;
  isSaving: boolean;
  onSave: () => void;
  onClone: () => void;
  onReset: () => void;
  onDelete: () => void;
}

export function PipelineToolbar({
  pipelineName,
  isFactory,
  isDirty,
  isSaving,
  onSave,
  onClone,
  onReset,
  onDelete,
}: Props) {
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-white border-b border-gray-100">
      <span className="text-sm font-semibold text-gray-700 mr-2 flex-shrink-0">
        {pipelineName}
      </span>

      {isFactory && (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-gray-100 rounded-full text-xs font-semibold text-gray-500 mr-2">
          {/* lock icon */}
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          Factory · Read-only
        </span>
      )}

      {isDirty && !isFactory && (
        <span className="inline-flex items-center px-2.5 py-1 bg-amber-50 rounded-full text-xs font-semibold text-amber-600 mr-2">
          Unsaved changes
        </span>
      )}

      <div className="ml-auto flex items-center gap-2">
        {/* Save — only for user-owned, only when dirty */}
        {!isFactory && (
          <button
            onClick={onSave}
            disabled={!isDirty || isSaving}
            className="px-3.5 py-1.5 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-40"
            style={{ background: !isDirty || isSaving ? "#D1D5DB" : "#A100FF" }}
            onMouseOver={(e) => { if (isDirty && !isSaving) e.currentTarget.style.background = "#8200CC"; }}
            onMouseOut={(e) => { if (isDirty && !isSaving) e.currentTarget.style.background = "#A100FF"; }}
          >
            {isSaving ? "Saving…" : "Save Changes"}
          </button>
        )}

        {/* Clone */}
        <button
          onClick={onClone}
          className="px-3.5 py-1.5 rounded-lg text-sm font-semibold text-[#A100FF] border border-[#A100FF] hover:bg-accent-50 transition-all"
        >
          Clone as New
        </button>

        {/* Reset — only for user-owned when dirty */}
        {!isFactory && isDirty && (
          <button
            onClick={onReset}
            className="px-3.5 py-1.5 rounded-lg text-sm font-semibold text-gray-600 border border-gray-200 hover:bg-gray-50 transition-all"
          >
            Reset
          </button>
        )}

        {/* Delete — only for user-owned */}
        {!isFactory && (
          <button
            onClick={onDelete}
            className="px-3.5 py-1.5 rounded-lg text-sm font-semibold text-red-600 border border-red-200 hover:bg-red-50 transition-all"
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 8.2: Verify TypeScript compilation**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -10
```

Expected: exit 0.

- [ ] **Step 8.3: Commit**

```bash
git add surfaces/dashboard/src/pages/pipeline/PipelineToolbar.tsx
git commit -m "feat(ui): add PipelineToolbar with save/clone/reset/delete actions"
```

---

## Task 9: Interactive `PipelinePage`

**Files:**
- Modify: `surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx`

**Interfaces:**
- Consumes: `usePipelineEditor` (Task 6), `NodeConfigDrawer` (Task 7), `PipelineToolbar` (Task 8), `api.listPipelines`, `api.getPipeline`, `api.updatePipeline`, `api.deletePipeline`, `api.clonePipeline` (Task 5)

---

- [ ] **Step 9.1: Replace `surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx`**

```tsx
// surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx
import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  Node,
  Edge,
  Handle,
  Position,
  NodeProps,
  Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, PipelineListItem, PipelineDetailDTO } from "../../api/client";
import { usePipelineEditor, AgentNodeData } from "../../hooks/usePipelineEditor";
import { NodeConfigDrawer } from "./NodeConfigDrawer";
import { PipelineToolbar } from "./PipelineToolbar";

// ── Tier colour palette (matches Phase 1) ────────────────────────────────

const TIER_COLOR: Record<string, { bg: string; text: string; dot: string }> = {
  fast:     { bg: "#F5E5FF", text: "#6200CC", dot: "#A100FF" },
  balanced: { bg: "#FEF3C7", text: "#92400E", dot: "#F59E0B" },
  top:      { bg: "#FEE2E2", text: "#991B1B", dot: "#EF4444" },
  none:     { bg: "#F3F4F6", text: "#6B7280", dot: "#9CA3AF" },
};

// ── Agent node renderer ───────────────────────────────────────────────────

function AgentNode({ data, selected }: NodeProps<Node<AgentNodeData>>) {
  const colors = TIER_COLOR[data.tier] ?? TIER_COLOR.none;
  return (
    <div
      className={`bg-white border-2 rounded-xl px-5 py-4 min-w-[165px] shadow-card hover:shadow-card-hover transition-all ${
        selected ? "border-[#A100FF]" : "border-gray-200"
      }`}
    >
      <Handle type="target" position={Position.Left} style={{ background: "#D1D5DB", width: 8, height: 8 }} />
      <p className="text-sm font-bold text-gray-900">{data.label}</p>
      <p className="text-[11px] text-gray-400 mt-0.5 font-mono">{data.agent}</p>
      <div className="flex items-center gap-2 mt-2.5">
        <span
          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold"
          style={{ background: colors.bg, color: colors.text }}
        >
          <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: colors.dot }} />
          {data.tier === "none" ? "deterministic" : data.tier}
        </span>
      </div>
      {data.budget_pct > 0 && (
        <p className="text-[11px] text-gray-400 mt-1.5">{data.budget_pct}% budget</p>
      )}
      <Handle type="source" position={Position.Right} style={{ background: "#D1D5DB", width: 8, height: 8 }} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

// ── Left panel: pipeline list ─────────────────────────────────────────────

interface PipelineListProps {
  items: PipelineListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function PipelineList({ items, selectedId, onSelect }: PipelineListProps) {
  const factory = items.filter((p) => p.is_factory);
  const user = items.filter((p) => !p.is_factory);

  function renderItem(p: PipelineListItem) {
    const selected = p.id === selectedId;
    return (
      <button
        key={p.id}
        onClick={() => onSelect(p.id)}
        className={`w-full text-left px-3 py-2.5 rounded-lg transition-all flex items-center gap-2 ${
          selected ? "bg-accent-50 border border-accent-100" : "hover:bg-gray-50 border border-transparent"
        }`}
      >
        {p.is_factory && (
          <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        )}
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-semibold truncate ${selected ? "text-[#A100FF]" : "text-gray-800"}`}>
            {p.name}
          </p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            {p.node_count} nodes · v{p.version}
          </p>
        </div>
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-1 p-2">
      {factory.length > 0 && (
        <>
          <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 py-1">Factory</p>
          {factory.map(renderItem)}
        </>
      )}
      {user.length > 0 && (
        <>
          <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 py-1 mt-2">Your Pipelines</p>
          {user.map(renderItem)}
        </>
      )}
    </div>
  );
}

// ── Clone name modal ──────────────────────────────────────────────────────

interface CloneModalProps {
  onConfirm: (name: string) => void;
  onCancel: () => void;
}

function CloneModal({ onConfirm, onCancel }: CloneModalProps) {
  const [name, setName] = useState("");
  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-xl w-96 p-6 flex flex-col gap-4">
        <h3 className="text-base font-bold text-gray-900">Clone Pipeline</h3>
        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:border-transparent"
          style={{ ["--tw-ring-color" as string]: "#A100FF" }}
          placeholder="my-custom-scan"
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && name) onConfirm(name); }}
        />
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-gray-600 border border-gray-200 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            disabled={!name}
            onClick={() => name && onConfirm(name)}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-40"
            style={{ background: "#A100FF" }}
          >
            Clone
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

export function PipelinePage() {
  const qc = useQueryClient();
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [showCloneModal, setShowCloneModal] = useState(false);

  // Fetch pipeline list
  const { data: pipelineList = [] } = useQuery({
    queryKey: ["pipelines"],
    queryFn: api.listPipelines,
    onSuccess: (items: PipelineListItem[]) => {
      // Auto-select first item on initial load
      if (!selectedPipelineId && items.length > 0) {
        setSelectedPipelineId(items[0].id);
      }
    },
  });

  // Fetch selected pipeline detail
  const { data: selectedPipeline = null } = useQuery<PipelineDetailDTO | null>({
    queryKey: ["pipeline", selectedPipelineId],
    queryFn: () =>
      selectedPipelineId ? api.getPipeline(selectedPipelineId) : Promise.resolve(null),
    enabled: !!selectedPipelineId,
  });

  const editor = usePipelineEditor(selectedPipeline);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: () => {
      if (!selectedPipelineId) throw new Error("No pipeline selected");
      return api.updatePipeline(selectedPipelineId, {
        definition: editor.toPipelineDefinition(),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipeline", selectedPipelineId] });
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });

  // Clone mutation
  const cloneMutation = useMutation({
    mutationFn: (name: string) => {
      if (!selectedPipelineId) throw new Error("No pipeline selected");
      return api.clonePipeline(selectedPipelineId, name);
    },
    onSuccess: (newPipeline) => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
      setSelectedPipelineId(newPipeline.id);
      setShowCloneModal(false);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!selectedPipelineId) throw new Error("No pipeline selected");
      return api.deletePipeline(selectedPipelineId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
      setSelectedPipelineId(pipelineList[0]?.id ?? null);
    },
  });

  const isFactory = selectedPipeline?.is_factory ?? false;
  const isEditable = !!selectedPipeline && !isFactory;

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (isEditable) editor.selectNode(node.id);
    },
    [isEditable, editor]
  );

  const handlePaneClick = useCallback(() => {
    editor.selectNode(null);
  }, [editor]);

  const selectedNodeData = editor.selectedNodeId
    ? editor.nodes.find((n) => n.id === editor.selectedNodeId)
    : null;

  return (
    <div className="flex flex-col h-full gap-0">
      {/* Page header */}
      <div className="flex items-center justify-between px-6 py-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Pipeline Builder</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Configure agent topology and resource budgets
          </p>
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="flex flex-1 min-h-0 gap-0">
        {/* Left rail */}
        <div className="w-56 flex-shrink-0 bg-white border-r border-gray-100 overflow-y-auto">
          <PipelineList
            items={pipelineList}
            selectedId={selectedPipelineId}
            onSelect={setSelectedPipelineId}
          />
        </div>

        {/* Graph area */}
        <div className="flex-1 flex flex-col min-w-0 bg-white">
          {selectedPipeline ? (
            <>
              <PipelineToolbar
                pipelineName={selectedPipeline.name}
                isFactory={isFactory}
                isDirty={editor.isDirty}
                isSaving={saveMutation.isPending}
                onSave={() => saveMutation.mutate()}
                onClone={() => setShowCloneModal(true)}
                onReset={editor.resetToSaved}
                onDelete={() => {
                  if (window.confirm(`Delete pipeline "${selectedPipeline.name}"?`)) {
                    deleteMutation.mutate();
                  }
                }}
              />
              <div className="relative flex-1 min-h-0">
                <ReactFlow
                  nodes={editor.nodes}
                  edges={editor.edges}
                  nodeTypes={nodeTypes}
                  onNodesChange={isEditable ? editor.onNodesChange : undefined}
                  onEdgesChange={isEditable ? editor.onEdgesChange : undefined}
                  onConnect={isEditable ? (conn: Connection) => editor.addEdge(conn) : undefined}
                  onNodeClick={handleNodeClick}
                  onPaneClick={handlePaneClick}
                  nodesDraggable={isEditable}
                  nodesConnectable={isEditable}
                  elementsSelectable={isEditable}
                  fitView
                  fitViewOptions={{ padding: 0.25 }}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background color="#E5E7EB" gap={24} size={1} />
                  <Controls
                    showInteractive={false}
                    style={{ background: "white", border: "1px solid #E5E7EB", borderRadius: 8 }}
                  />
                </ReactFlow>

                {/* Node config drawer */}
                {editor.selectedNodeId && selectedNodeData && (
                  <NodeConfigDrawer
                    nodeId={editor.selectedNodeId}
                    data={selectedNodeData.data}
                    allNodes={editor.nodes}
                    onUpdate={editor.updateNode}
                    onRemove={editor.removeNode}
                    onClose={() => editor.selectNode(null)}
                    isFactory={isFactory}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
              Select a pipeline from the left panel
            </div>
          )}
        </div>
      </div>

      {showCloneModal && (
        <CloneModal
          onConfirm={(name) => cloneMutation.mutate(name)}
          onCancel={() => setShowCloneModal(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 9.2: Verify TypeScript compilation**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -20
```

Expected: exit 0. Common type errors to watch for:
- `onSuccess` callback on `useQuery` — if the version of `@tanstack/react-query` installed doesn't support `onSuccess` in options, move the auto-select logic into a `useEffect` watching `pipelineList`.
- `Connection` import — verify `@xyflow/react` v12 exports `Connection`; if not, replace with `Edge`.

If `onSuccess` causes a type error (it was removed in react-query v5 `useQuery`), replace the query with:

```typescript
  const { data: pipelineList = [] } = useQuery({
    queryKey: ["pipelines"],
    queryFn: api.listPipelines,
  });

  // Auto-select first pipeline
  useEffect(() => {
    if (!selectedPipelineId && pipelineList.length > 0) {
      setSelectedPipelineId(pipelineList[0].id);
    }
  }, [pipelineList, selectedPipelineId]);
```

Add `import { useState, useCallback, useEffect } from "react";` at the top.

- [ ] **Step 9.3: Commit**

```bash
git add surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx
git commit -m "feat(ui): replace read-only pipeline graph with interactive two-panel editor"
```

---

## Task 10: Pipeline Selector in Scan Trigger Modal

**Files:**
- Modify: `surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx`

**Interfaces:**
- Consumes: `api.listPipelines` (Task 5), `PipelineListItem` (Task 5), `TriggerScanRequest.pipeline_config_name` (Task 5)

---

- [ ] **Step 10.1: Replace `surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx`**

```tsx
// surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx
import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, SecurityApproach, APPROACH_LABELS, APPROACH_DESCRIPTIONS } from "../../api/client";

interface Props { onClose: () => void; }

const APPROACHES: SecurityApproach[] = [
  "penetration_testing", "adversary_emulation", "breach_and_attack_simulation",
  "assumed_breach", "blue_team", "purple_team",
];

const APPROACH_ICON: Record<SecurityApproach, React.ReactNode> = {
  penetration_testing: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L9.121 9.121m0 5.758a3 3 0 10-4.243-4.243 3 3 0 004.243 4.243z" />
    </svg>
  ),
  adversary_emulation: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  ),
  breach_and_attack_simulation: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  assumed_breach: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
    </svg>
  ),
  blue_team: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  purple_team: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
    </svg>
  ),
};

export function TriggerScanModal({ onClose }: Props) {
  const [targetRef, setTargetRef] = useState("");
  const [approach, setApproach] = useState<SecurityApproach>("penetration_testing");
  const [mode, setMode] = useState<"at_rest" | "real_time">("at_rest");
  const [pipelineName, setPipelineName] = useState("full-scan");
  const qc = useQueryClient();

  const { data: pipelines = [] } = useQuery({
    queryKey: ["pipelines"],
    queryFn: api.listPipelines,
  });

  // Default to first pipeline once list loads
  useEffect(() => {
    if (pipelines.length > 0 && pipelineName === "full-scan") {
      const defaultPipe = pipelines.find((p) => p.name === "full-scan") ?? pipelines[0];
      setPipelineName(defaultPipe.name);
    }
  }, [pipelines]);

  const mutation = useMutation({
    mutationFn: () =>
      api.triggerScan({
        target_ref: targetRef,
        mode,
        approach,
        pipeline_config_name: pipelineName,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scans"] }); onClose(); },
  });

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.15)] w-[620px] max-h-[90vh] overflow-y-auto">
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "#A100FF" }}>
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <h2 className="text-lg font-bold text-gray-900">New Security Scan</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center text-gray-500 hover:text-gray-700 transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-5 flex flex-col gap-5">
          {/* Target */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Target
            </label>
            <input
              className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm font-mono text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:border-transparent"
              style={{ ["--tw-ring-color" as string]: "#A100FF" }}
              placeholder="/path/to/repo  or  github.com/org/repo@main"
              value={targetRef}
              onChange={(e) => setTargetRef(e.target.value)}
            />
          </div>

          {/* Pipeline selector */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Pipeline
            </label>
            <select
              className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:border-transparent bg-white"
              style={{ ["--tw-ring-color" as string]: "#A100FF" }}
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
            >
              {pipelines.map((p) => (
                <option key={p.id} value={p.name}>
                  {p.name}{p.is_factory ? " (factory)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Security approach */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Security Approach
            </label>
            <div className="grid grid-cols-2 gap-2">
              {APPROACHES.map((a) => {
                const selected = approach === a;
                return (
                  <button
                    key={a}
                    onClick={() => setApproach(a)}
                    className={`text-left px-4 py-3 rounded-xl border-2 transition-all ${
                      selected
                        ? "border-[#A100FF] bg-accent-50"
                        : "border-gray-100 bg-gray-50 hover:border-gray-200 hover:bg-white"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className={selected ? "text-[#A100FF]" : "text-gray-400"}>
                        {APPROACH_ICON[a]}
                      </span>
                      <span className={`text-sm font-semibold ${selected ? "text-[#A100FF]" : "text-gray-700"}`}>
                        {APPROACH_LABELS[a]}
                      </span>
                      {selected && (
                        <span className="ml-auto w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: "#A100FF" }}>
                          <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 leading-snug">{APPROACH_DESCRIPTIONS[a]}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Mode */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Mode</label>
            <div className="flex gap-2">
              {(["at_rest", "real_time"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 py-2 rounded-lg border text-sm font-medium transition-all ${
                    mode === m
                      ? "border-[#A100FF] bg-accent-50 text-[#A100FF]"
                      : "border-gray-200 text-gray-600 hover:border-gray-300"
                  }`}
                >
                  {m === "at_rest" ? "At Rest — full scan" : "Real Time — diff only"}
                </button>
              ))}
            </div>
          </div>

          {/* Submit */}
          <button
            onClick={() => mutation.mutate()}
            disabled={!targetRef || mutation.isPending}
            className="w-full text-white font-semibold rounded-xl py-3 transition-all disabled:opacity-40"
            style={{ background: !targetRef || mutation.isPending ? "#D1D5DB" : "#A100FF" }}
            onMouseOver={(e) => { if (targetRef && !mutation.isPending) e.currentTarget.style.background = "#8200CC"; }}
            onMouseOut={(e) => { if (targetRef && !mutation.isPending) e.currentTarget.style.background = "#A100FF"; }}
          >
            {mutation.isPending ? "Starting…" : `Start ${APPROACH_LABELS[approach]} Scan`}
          </button>

          {mutation.isError && (
            <p className="text-sm text-red-500 text-center">{String(mutation.error)}</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 10.2: Verify TypeScript compilation**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -10
```

Expected: exit 0.

- [ ] **Step 10.3: Run all Python tests to confirm no backend regressions**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
.venv/bin/pytest tests/core/ -v --ignore=tests/e2e
```

Expected: all pass.

- [ ] **Step 10.4: Commit**

```bash
git add surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx
git commit -m "feat(ui): add pipeline selector dropdown to scan trigger modal"
```

---

## Spec Coverage Self-Check

| Spec requirement | Task | Status |
|-----------------|------|--------|
| `is_factory` column added to `PipelineConfigRow` | Task 1 | covered |
| Alembic migration for `is_factory` | Task 1 | covered |
| `seed_pipeline_configs(session)` reads `config/pipeline_configs/*.yaml` | Task 2 | covered |
| Seeder is idempotent — skips existing rows | Task 2 | covered |
| Seeder called at app startup | Task 3 | covered |
| `GET /api/v1/pipelines` — list with `node_count` | Task 4 | covered |
| `GET /api/v1/pipelines/{id}` — full detail | Task 4 | covered |
| `POST /api/v1/pipelines` — create non-factory | Task 4 | covered |
| `PUT /api/v1/pipelines/{id}` — update, bumps version | Task 4 | covered |
| `PUT` returns 403 for factory | Task 4 | covered |
| `DELETE /api/v1/pipelines/{id}` — delete user pipeline | Task 4 | covered |
| `DELETE` returns 403 for factory | Task 4 | covered |
| `POST /api/v1/pipelines/{id}/clone` — clones any pipeline | Task 4 | covered |
| `sum(budget_pct) ≤ 100` validation | Task 4 | covered |
| `PipelineDTO`, pipeline API calls in `client.ts` | Task 5 | covered |
| `pipeline_config_name` added to `TriggerScanRequest` | Task 5 | covered |
| `usePipelineEditor` hook with full interface | Task 6 | covered |
| `NodeConfigDrawer` with label/agent/tier/budget/remove | Task 7 | covered |
| `PipelineToolbar` with save/clone/reset/delete | Task 8 | covered |
| `PipelinePage` two-panel layout | Task 9 | covered |
| Factory configs read-only in UI (lock icon) | Task 8, 9 | covered |
| User config nodes draggable/connectable | Task 9 | covered |
| "Save Changes" calls `PUT` API | Task 9 | covered |
| Pipeline dropdown in `TriggerScanModal` | Task 10 | covered |
| Default to "full-scan" in modal | Task 10 | covered |

All spec requirements covered. No placeholders.
