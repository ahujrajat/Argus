# Argus Phase 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the monorepo scaffold, data model, PostgreSQL persistence, secret redaction, finRouter Gateway sidecar, and the governance layer (model router, budget guard, GovernanceGate, cost ledger, SSE emitter) — everything the scanning and agent layers depend on.

**Architecture:** Python core (FastAPI + SQLAlchemy + asyncpg) with a TypeScript finRouter Gateway sidecar. GovernanceGate is the single chokepoint for all LLM calls; it calls the Gateway via httpx and writes a CostLedgerEntry per call. SSE events flow from GovernanceGate through the API to the dashboard.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, asyncpg, httpx, PyYAML, structlog, pytest, pytest-asyncio; Node 20, TypeScript, Fastify, finrouter npm package; PostgreSQL 16, MinIO (S3-compatible).

## Global Constraints

- Python ≥ 3.12; use `from __future__ import annotations` in every Python file
- Pydantic v2 throughout — no v1 compat shims
- All async Python uses `asyncio`; no sync DB calls in request handlers
- No model name, provider name, or dollar amount hardcoded in Python source — all live in `config/model_tiers.yaml` and `config/budget_policy.yaml`
- Secrets (API keys, found credentials) never written to logs, DB text fields, model prompts, or HTTP responses — redact before any write
- Every privileged operation writes an AuditLogEntry
- All tests use `pytest`; async tests use `pytest-asyncio` with `asyncio_mode = "auto"`

---

### Task 1: Monorepo scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `.gitignore`
- Create: `config/model_tiers.yaml`
- Create: `config/budget_policy.yaml`
- Create: `config/pipeline_configs/full-scan.yaml`
- Create: `config/pipeline_configs/pr-check.yaml`
- Create: `config/pipeline_configs/real-time.yaml`
- Create all `__init__.py` stubs for: `core/agents/`, `core/governance/`, `core/scanners/`, `core/understanding/`, `core/model/`, `core/api/`, `core/api/routers/`, `core/db/`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "argus"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",
    "httpx>=0.27.0",
    "pyyaml>=6.0.1",
    "structlog>=24.1.0",
    "python-multipart>=0.0.9",
    "sse-starlette>=2.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.30.0",
    "httpx>=0.27.0",
    "factory-boy>=3.3.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["core"]
```

- [ ] **Step 2: Create .env.example**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus

# Object storage
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=argus-artifacts

# finRouter Gateway
FINROUTER_GATEWAY_URL=http://localhost:3001

# LLM provider keys (passed to finRouter Gateway)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=

# Argus settings
LOG_LEVEL=INFO
ENVIRONMENT=development
```

- [ ] **Step 3: Create docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: argus
      POSTGRES_PASSWORD: argus
      POSTGRES_DB: argus
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  finrouter-gateway:
    build: ./surfaces/finrouter-gateway
    ports:
      - "3001:3001"
    environment:
      PORT: 3001
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}

volumes:
  postgres_data:
  minio_data:
```

- [ ] **Step 4: Create config/model_tiers.yaml**

```yaml
providers:
  default: anthropic

tiers:
  fast:
    anthropic: claude-haiku-4-5-20251001
    openai: gpt-4o-mini
    google: gemini-2.0-flash
  balanced:
    anthropic: claude-sonnet-4-6
    openai: gpt-4o
    google: gemini-2.0-pro
  top:
    anthropic: claude-opus-4-8
    openai: o1
    google: gemini-2.5-pro

escalation_rules:
  - condition: confidence_lt
    threshold: 0.5
    from_tier: balanced
    to_tier: top
  - condition: diff_files_gt
    threshold: 10
    from_tier: balanced
    to_tier: top

task_defaults:
  routing: fast
  classification: fast
  extraction: fast
  explanation: fast
  triage: balanced
  false_positive_filter: balanced
  fix_generation: balanced
  pattern_analysis: balanced
  complex_fix: top
  gap_analysis: top
```

- [ ] **Step 5: Create config/budget_policy.yaml**

```yaml
per_scan:
  soft_limit_usd: 4.00
  hard_limit_usd: 5.00

monthly:
  soft_limit_usd: 160.00
  hard_limit_usd: 200.00

on_soft_limit: warn
on_hard_limit: stop_and_mark_skipped
```

- [ ] **Step 6: Create config/pipeline_configs/full-scan.yaml**

```yaml
name: full-scan
version: 1
is_default: true
mode: at_rest
nodes:
  - id: ingestion
    agent: IngestionAgent
    tier: fast
    budget_pct: 5
  - id: sast
    agent: SemgrepAdapter
    tier: none
    budget_pct: 0
  - id: secrets
    agent: TruffleHogAdapter
    tier: none
    budget_pct: 0
  - id: triage
    agent: TriageAgent
    tier: balanced
    budget_pct: 40
  - id: explainer
    agent: ExplainerAgent
    tier: fast
    budget_pct: 15
edges:
  - from: ingestion
    to: sast
    condition: null
  - from: ingestion
    to: secrets
    condition: null
  - from: sast
    to: triage
    condition: null
  - from: secrets
    to: triage
    condition: null
  - from: triage
    to: explainer
    condition: null
```

- [ ] **Step 7: Create config/pipeline_configs/pr-check.yaml**

```yaml
name: pr-check
version: 1
is_default: true
mode: real_time
nodes:
  - id: ingestion
    agent: IngestionAgent
    tier: fast
    budget_pct: 5
  - id: sast
    agent: SemgrepAdapter
    tier: none
    budget_pct: 0
  - id: triage
    agent: TriageAgent
    tier: balanced
    budget_pct: 50
  - id: explainer
    agent: ExplainerAgent
    tier: fast
    budget_pct: 20
edges:
  - from: ingestion
    to: sast
    condition: null
  - from: sast
    to: triage
    condition: null
  - from: triage
    to: explainer
    condition: null
```

- [ ] **Step 8: Create config/pipeline_configs/real-time.yaml**

```yaml
name: real-time
version: 1
is_default: true
mode: real_time
nodes:
  - id: ingestion
    agent: IngestionAgent
    tier: fast
    budget_pct: 5
  - id: sast
    agent: SemgrepAdapter
    tier: none
    budget_pct: 0
  - id: triage
    agent: TriageAgent
    tier: fast
    budget_pct: 60
  - id: explainer
    agent: ExplainerAgent
    tier: fast
    budget_pct: 25
edges:
  - from: ingestion
    to: sast
    condition: null
  - from: sast
    to: triage
    condition: null
  - from: triage
    to: explainer
    condition: null
```

- [ ] **Step 9: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.env
dist/
build/
.pytest_cache/
.ruff_cache/
node_modules/
*.js.map
surfaces/dashboard/dist/
surfaces/finrouter-gateway/dist/
*.sarif
```

- [ ] **Step 10: Create all package __init__.py stubs**

```bash
mkdir -p core/{agents,governance,scanners,understanding,model,db} \
         core/api/routers \
         tests/core/{agents,governance,scanners,model,api} \
         tests/fixtures/{vulnerable_python,clean_python} \
         skills/{languages/{python,javascript-typescript},vuln-classes/{injection,xss,secrets-exposure},tools/{semgrep-tool,trufflehog-tool},standards/owasp-top-10} \
         surfaces/{dashboard/src,finrouter-gateway/src,ci} \
         evals/fixtures \
         sandbox

touch core/__init__.py \
      core/agents/__init__.py \
      core/governance/__init__.py \
      core/scanners/__init__.py \
      core/understanding/__init__.py \
      core/model/__init__.py \
      core/db/__init__.py \
      core/api/__init__.py \
      core/api/routers/__init__.py \
      tests/__init__.py \
      tests/core/__init__.py \
      tests/core/agents/__init__.py \
      tests/core/governance/__init__.py \
      tests/core/scanners/__init__.py \
      tests/core/model/__init__.py \
      tests/core/api/__init__.py
```

- [ ] **Step 11: Install Python dependencies**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: no errors, `pytest --collect-only` exits 0 with "0 tests collected".

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: monorepo scaffold, config files, docker-compose"
```

---

### Task 2: Core data model

**Files:**
- Create: `core/model/entities.py`
- Create: `tests/core/model/test_entities.py`

**Interfaces:**
- Produces: `Scan`, `Finding`, `Fix`, `PatternFinding`, `CostLedgerEntry`, `AuditLogEntry`, `PipelineConfig`, `TargetAuthorization`, `SkillMeta`, `Location`, `ScanMode`, `ScanStatus`, `Severity`, `FindingStatus`, `FixStatus`, `ModelTier` — all Pydantic v2 BaseModel subclasses importable from `core.model.entities`
- Note: `SecurityApproach` enum and `Scan.approach` field are added by the security-approaches addendum plan (`2026-06-17-phase1-security-approaches.md`). Implement this task first as written, then the addendum patches it.

- [ ] **Step 1: Write failing test**

```python
# tests/core/model/test_entities.py
from __future__ import annotations
from uuid import UUID
from core.model.entities import (
    Scan, Finding, Fix, CostLedgerEntry, AuditLogEntry,
    PipelineConfig, Location, ScanMode, ScanStatus,
    Severity, FindingStatus, FixStatus, ModelTier,
)

def test_scan_defaults():
    s = Scan(target_ref="github.com/acme/api@main", pipeline_config_id="00000000-0000-0000-0000-000000000001", mode=ScanMode.at_rest)
    assert isinstance(s.id, UUID)
    assert s.status == ScanStatus.pending
    assert s.cost_usd == 0.0

def test_finding_dedup_key_required():
    loc = Location(file="app.py", line_start=10, line_end=12)
    f = Finding(
        scan_id="00000000-0000-0000-0000-000000000002",
        rule_id="python.injection.sql",
        source_tool="semgrep",
        severity=Severity.high,
        location=loc,
        dedup_key="semgrep:python.injection.sql:app.py:10",
    )
    assert f.status == FindingStatus.open
    assert f.cwe is None

def test_cost_ledger_entry():
    entry = CostLedgerEntry(
        scope_type="scan",
        scope_id="00000000-0000-0000-0000-000000000003",
        tokens_in=1000,
        tokens_out=200,
        tier=ModelTier.balanced,
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        cost_usd=0.006,
    )
    assert entry.batch_flag is False
    assert isinstance(entry.id, UUID)
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/core/model/test_entities.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.model.entities'`

- [ ] **Step 3: Implement entities.py**

```python
# core/model/entities.py
from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ScanMode(str, Enum):
    at_rest = "at_rest"
    batch = "batch"
    real_time = "real_time"


class ScanStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class FindingStatus(str, Enum):
    open = "open"
    triaged = "triaged"
    fixed = "fixed"
    dismissed = "dismissed"
    skipped = "skipped"


class FixStatus(str, Enum):
    proposed = "proposed"
    applied = "applied"
    pr_opened = "pr_opened"
    rejected = "rejected"
    needs_attention = "needs_attention"


class ModelTier(str, Enum):
    fast = "fast"
    balanced = "balanced"
    top = "top"
    none = "none"


class SkillStatus(str, Enum):
    active = "active"
    candidate = "candidate"
    disabled = "disabled"


class Location(BaseModel):
    file: str
    line_start: int
    line_end: int
    snippet: Optional[str] = None


class Scan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    target_ref: str
    pipeline_config_id: UUID
    mode: ScanMode
    status: ScanStatus = ScanStatus.pending
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cache_hits: int = 0
    cost_usd: float = 0.0
    model_usage: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scan_id: UUID
    rule_id: str
    source_tool: str
    cwe: Optional[str] = None
    owasp_category: Optional[str] = None
    severity: Severity
    exploit_likelihood: float = 0.5
    confidence: float = 0.5
    reachability: Optional[str] = None
    location: Location
    dedup_key: str
    status: FindingStatus = FindingStatus.open
    fix_id: Optional[UUID] = None
    explanation: Optional[str] = None


class Fix(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    finding_id: UUID
    diff: str
    test: Optional[str] = None
    explanation: str
    validation_result: Optional[dict[str, Any]] = None
    status: FixStatus = FixStatus.proposed
    reviewer: Optional[str] = None
    audit_ref: Optional[UUID] = None


class PatternFinding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scan_id: UUID
    issue: str
    examples: list[dict[str, Any]] = Field(default_factory=list)
    risk: str
    direction: str


class CostLedgerEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scope_type: str
    scope_id: UUID
    tokens_in: int
    tokens_out: int
    cache_hits: int = 0
    tier: ModelTier
    provider: str
    model_id: str
    batch_flag: bool = False
    cost_usd: float
    timestamp: datetime = Field(default_factory=_now)


class AuditLogEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    actor: str
    action: str
    target: str
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=_now)


class PipelineNodeConfig(BaseModel):
    id: str
    agent: str
    tier: ModelTier
    budget_pct: int = 0


class PipelineEdge(BaseModel):
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    condition: Optional[str] = None

    model_config = {"populate_by_name": True}


class PipelineDefinition(BaseModel):
    nodes: list[PipelineNodeConfig]
    edges: list[PipelineEdge]


class PipelineConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    version: int = 1
    definition: PipelineDefinition
    is_default: bool = False
    created_at: datetime = Field(default_factory=_now)


class SkillMeta(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    family: str
    tools_allowed: list[str] = Field(default_factory=list)
    status: SkillStatus = SkillStatus.active
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class TargetAuthorization(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    target: str
    scope_rules: dict[str, Any] = Field(default_factory=dict)
    owner_confirmed: bool = False
    environment: str = "non-production"
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/core/model/test_entities.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/model/entities.py tests/core/model/test_entities.py
git commit -m "feat: core Pydantic data model"
```

---

### Task 3: PostgreSQL schema + Alembic

**Files:**
- Create: `core/db/session.py`
- Create: `core/db/tables.py`
- Create: `core/db/migrations/env.py`
- Create: `core/db/migrations/versions/001_initial_schema.py`
- Create: `alembic.ini`
- Create: `tests/core/test_db.py`

**Interfaces:**
- Consumes: `core.model.entities` (all entity models)
- Produces: `get_session() -> AsyncSession` (async context manager), SQLAlchemy `Base`, all table definitions mirroring entity models

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_db.py
from __future__ import annotations
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.session import get_session, engine
from core.db.tables import Base

@pytest.fixture(scope="module")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def test_session_is_async(db_session: AsyncSession):
    assert isinstance(db_session, AsyncSession)

async def test_tables_exist(db_session: AsyncSession):
    from sqlalchemy import text
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    tables = {row[0] for row in result}
    assert "scans" in tables
    assert "findings" in tables
    assert "cost_ledger_entries" in tables
    assert "audit_log_entries" in tables
    assert "pipeline_configs" in tables
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/core/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.db.session'`

- [ ] **Step 3: Implement core/db/session.py**

```python
# core/db/session.py
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://argus:argus@localhost:5432/argus",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncSession:
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 4: Implement core/db/tables.py**

```python
# core/db/tables.py
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid():
    return str(uuid4())


def _now():
    return datetime.now(timezone.utc)


class ScanRow(Base):
    __tablename__ = "scans"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    target_ref = Column(String, nullable=False)
    pipeline_config_id = Column(UUID(as_uuid=False), nullable=False)
    mode = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cache_hits = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    model_usage = Column(JSONB, default=dict)
    findings = relationship("FindingRow", back_populates="scan", lazy="selectin")


class FindingRow(Base):
    __tablename__ = "findings"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    scan_id = Column(UUID(as_uuid=False), ForeignKey("scans.id"), nullable=False)
    rule_id = Column(String, nullable=False)
    source_tool = Column(String, nullable=False)
    cwe = Column(String, nullable=True)
    owasp_category = Column(String, nullable=True)
    severity = Column(String, nullable=False)
    exploit_likelihood = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    reachability = Column(String, nullable=True)
    location = Column(JSONB, nullable=False)
    dedup_key = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="open")
    fix_id = Column(UUID(as_uuid=False), nullable=True)
    explanation = Column(Text, nullable=True)
    scan = relationship("ScanRow", back_populates="findings")


class FixRow(Base):
    __tablename__ = "fixes"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    finding_id = Column(UUID(as_uuid=False), ForeignKey("findings.id"), nullable=False)
    diff = Column(Text, nullable=False)
    test = Column(Text, nullable=True)
    explanation = Column(Text, nullable=False)
    validation_result = Column(JSONB, nullable=True)
    status = Column(String, nullable=False, default="proposed")
    reviewer = Column(String, nullable=True)
    audit_ref = Column(UUID(as_uuid=False), nullable=True)


class PatternFindingRow(Base):
    __tablename__ = "pattern_findings"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    scan_id = Column(UUID(as_uuid=False), ForeignKey("scans.id"), nullable=False)
    issue = Column(Text, nullable=False)
    examples = Column(JSONB, default=list)
    risk = Column(Text, nullable=False)
    direction = Column(Text, nullable=False)


class CostLedgerEntryRow(Base):
    __tablename__ = "cost_ledger_entries"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    scope_type = Column(String, nullable=False)
    scope_id = Column(UUID(as_uuid=False), nullable=False)
    tokens_in = Column(Integer, nullable=False)
    tokens_out = Column(Integer, nullable=False)
    cache_hits = Column(Integer, default=0)
    tier = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    model_id = Column(String, nullable=False)
    batch_flag = Column(Boolean, default=False)
    cost_usd = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=_now)


class AuditLogEntryRow(Base):
    __tablename__ = "audit_log_entries"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target = Column(String, nullable=False)
    before = Column(JSONB, nullable=True)
    after = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_now)


class PipelineConfigRow(Base):
    __tablename__ = "pipeline_configs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False, unique=True)
    version = Column(Integer, default=1)
    definition = Column(JSONB, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class SkillMetaRow(Base):
    __tablename__ = "skill_meta"
    name = Column(String, primary_key=True)
    description = Column(Text, nullable=False)
    version = Column(String, default="1.0.0")
    family = Column(String, nullable=False)
    tools_allowed = Column(JSONB, default=list)
    status = Column(String, default="active")
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)


class TargetAuthorizationRow(Base):
    __tablename__ = "target_authorizations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    target = Column(String, nullable=False)
    scope_rules = Column(JSONB, default=dict)
    owner_confirmed = Column(Boolean, default=False)
    environment = Column(String, default="non-production")
    rate_limits = Column(JSONB, default=dict)
    expires_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Start postgres and run test**

```bash
docker compose up postgres -d
sleep 3
pytest tests/core/test_db.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Set up Alembic**

```bash
pip install alembic
alembic init core/db/migrations
```

Edit `alembic.ini` — set `script_location = core/db/migrations` and `sqlalchemy.url = postgresql+asyncpg://argus:argus@localhost:5432/argus`.

Edit `core/db/migrations/env.py` to use async engine and import `Base` from `core.db.tables`:

```python
# core/db/migrations/env.py
from __future__ import annotations
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context
from core.db.tables import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def do_run():
        async with connectable.connect() as connection:
            await connection.run_sync(context.configure, connection=connection, target_metadata=target_metadata)
            async with connection.begin():
                await connection.run_sync(context.run_migrations)

    asyncio.run(do_run())


run_migrations_online()
```

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Expected: migration applies with no errors.

- [ ] **Step 7: Commit**

```bash
git add core/db/ alembic.ini tests/core/test_db.py
git commit -m "feat: PostgreSQL tables and Alembic migrations"
```

---

### Task 4: Secret redaction

**Files:**
- Create: `core/model/redaction.py`
- Create: `tests/core/model/test_redaction.py`

**Interfaces:**
- Produces: `redact(text: str) -> str`, `redact_dict(d: dict) -> dict`, `fingerprint(secret: str) -> str` — importable from `core.model.redaction`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/model/test_redaction.py
from __future__ import annotations
from core.model.redaction import redact, redact_dict, fingerprint

def test_redact_api_key_in_string():
    text = 'Authorization: Bearer sk-ant-api03-abc123xyz789'
    result = redact(text)
    assert "sk-ant-api03-abc123xyz789" not in result
    assert "[REDACTED]" in result

def test_redact_openai_key():
    text = "key = 'sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ'"
    result = redact(text)
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result

def test_redact_dict_nested():
    d = {"config": {"api_key": "sk-ant-api03-secret", "model": "claude"}}
    result = redact_dict(d)
    assert result["config"]["api_key"] == "[REDACTED]"
    assert result["config"]["model"] == "claude"

def test_redact_dict_key_names():
    d = {"password": "hunter2", "token": "ghp_abc123", "name": "alice"}
    result = redact_dict(d)
    assert result["password"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"
    assert result["name"] == "alice"

def test_fingerprint_is_deterministic():
    assert fingerprint("secret123") == fingerprint("secret123")

def test_fingerprint_is_not_reversible():
    fp = fingerprint("secret123")
    assert "secret123" not in fp
    assert len(fp) == 64  # sha256 hex
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/model/test_redaction.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement redaction.py**

```python
# core/model/redaction.py
from __future__ import annotations
import re
import hashlib

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"gho_[A-Za-z0-9]{36}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),  # base64 blobs ≥40 chars
]

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_key", "secret_key", "private_key", "auth", "credential",
    "credentials", "authorization", "bearer",
})


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def redact_dict(d: dict) -> dict:
    result = {}
    for k, v in d.items():
        if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v)
        elif isinstance(v, str):
            result[k] = redact(v)
        else:
            result[k] = v
    return result


def fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/core/model/test_redaction.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/model/redaction.py tests/core/model/test_redaction.py
git commit -m "feat: secret redaction and fingerprinting"
```

---

### Task 5: finRouter Gateway sidecar

**Files:**
- Create: `surfaces/finrouter-gateway/package.json`
- Create: `surfaces/finrouter-gateway/tsconfig.json`
- Create: `surfaces/finrouter-gateway/src/types.ts`
- Create: `surfaces/finrouter-gateway/src/gateway.ts`
- Create: `surfaces/finrouter-gateway/src/index.ts`
- Create: `surfaces/finrouter-gateway/Dockerfile`

**Interfaces:**
- Produces:
  - `POST /chat` — accepts `ChatRequest`, returns `ChatResponse` (with inline usage)
  - `GET /cost/summary` — returns aggregated spend from finRouter
  - `GET /health` — returns `{"status":"ok"}`

- [ ] **Step 1: Initialize npm package**

```bash
cd surfaces/finrouter-gateway
npm init -y
npm install finrouter fastify @fastify/cors
npm install --save-dev typescript @types/node tsx
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create src/types.ts**

```typescript
// surfaces/finrouter-gateway/src/types.ts
export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  model: string;
  messages: ChatMessage[];
  provider?: string;
  zero_retention?: boolean;
  max_tokens?: number;
  temperature?: number;
}

export interface UsageInfo {
  tokens_in: number;
  tokens_out: number;
  cache_hit: boolean;
  cost_usd: number;
  model_id: string;
  provider: string;
}

export interface ChatResponse {
  content: string;
  usage: UsageInfo;
}

export interface CostSummary {
  total_cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  by_provider: Record<string, { cost_usd: number; calls: number }>;
}
```

- [ ] **Step 4: Create src/gateway.ts**

```typescript
// surfaces/finrouter-gateway/src/gateway.ts
import { ChatRequest, ChatResponse, CostSummary } from "./types.js";

// finrouter is a CommonJS package — import dynamically
let routerInstance: any = null;

async function getRouter(): Promise<any> {
  if (routerInstance) return routerInstance;
  const { FinRouter } = await import("finrouter");
  const router = new FinRouter({
    providers: {
      anthropic: { apiKey: process.env.ANTHROPIC_API_KEY ?? "" },
      openai: { apiKey: process.env.OPENAI_API_KEY ?? "" },
      google: { apiKey: process.env.GOOGLE_API_KEY ?? "" },
      mistral: { apiKey: process.env.MISTRAL_API_KEY ?? "" },
      groq: { apiKey: process.env.GROQ_API_KEY ?? "" },
    },
  });
  await router.init();
  routerInstance = router;
  return router;
}

// Per-call spend accumulator (finRouter tracks internally; we shadow it inline)
let _totalCostUsd = 0;
let _totalTokensIn = 0;
let _totalTokensOut = 0;
const _providerStats: Record<string, { cost_usd: number; calls: number }> = {};

function _estimateCost(provider: string, model: string, tokensIn: number, tokensOut: number): number {
  // Conservative per-token estimates in USD; real cost comes from finRouter's ledger
  const rates: Record<string, { in: number; out: number }> = {
    "claude-haiku-4-5-20251001": { in: 1 / 1e6, out: 5 / 1e6 },
    "claude-sonnet-4-6": { in: 3 / 1e6, out: 15 / 1e6 },
    "claude-opus-4-8": { in: 5 / 1e6, out: 25 / 1e6 },
    "gpt-4o-mini": { in: 0.15 / 1e6, out: 0.6 / 1e6 },
    "gpt-4o": { in: 2.5 / 1e6, out: 10 / 1e6 },
  };
  const rate = rates[model] ?? { in: 3 / 1e6, out: 15 / 1e6 };
  return tokensIn * rate.in + tokensOut * rate.out;
}

export async function chat(req: ChatRequest): Promise<ChatResponse> {
  const router = await getRouter();

  const response = await router.chat("argus-system", {
    model: req.model,
    messages: req.messages,
    ...(req.max_tokens ? { max_tokens: req.max_tokens } : {}),
    ...(req.temperature !== undefined ? { temperature: req.temperature } : {}),
  });

  const content: string =
    response?.choices?.[0]?.message?.content ??
    response?.content?.[0]?.text ??
    response?.text ??
    String(response);

  const tokensIn: number = response?.usage?.prompt_tokens ?? response?.usage?.input_tokens ?? 0;
  const tokensOut: number = response?.usage?.completion_tokens ?? response?.usage?.output_tokens ?? 0;
  const provider = req.provider ?? "anthropic";
  const costUsd = _estimateCost(provider, req.model, tokensIn, tokensOut);

  _totalCostUsd += costUsd;
  _totalTokensIn += tokensIn;
  _totalTokensOut += tokensOut;
  _providerStats[provider] = {
    cost_usd: (_providerStats[provider]?.cost_usd ?? 0) + costUsd,
    calls: (_providerStats[provider]?.calls ?? 0) + 1,
  };

  return {
    content,
    usage: {
      tokens_in: tokensIn,
      tokens_out: tokensOut,
      cache_hit: false,
      cost_usd: costUsd,
      model_id: req.model,
      provider,
    },
  };
}

export function getCostSummary(): CostSummary {
  return {
    total_cost_usd: _totalCostUsd,
    total_tokens_in: _totalTokensIn,
    total_tokens_out: _totalTokensOut,
    by_provider: { ..._providerStats },
  };
}
```

- [ ] **Step 5: Create src/index.ts**

```typescript
// surfaces/finrouter-gateway/src/index.ts
import Fastify from "fastify";
import cors from "@fastify/cors";
import { chat, getCostSummary } from "./gateway.js";
import { ChatRequest } from "./types.js";

const app = Fastify({ logger: true });
await app.register(cors, { origin: true });

app.get("/health", async () => ({ status: "ok" }));

app.post<{ Body: ChatRequest }>("/chat", async (request, reply) => {
  try {
    const result = await chat(request.body);
    return result;
  } catch (err: any) {
    request.log.error(err, "chat error");
    return reply.status(500).send({ error: err?.message ?? "unknown error" });
  }
});

app.get("/cost/summary", async () => getCostSummary());

const port = parseInt(process.env.PORT ?? "3001", 10);
await app.listen({ port, host: "0.0.0.0" });
console.log(`finRouter gateway listening on :${port}`);
```

- [ ] **Step 6: Update package.json scripts**

```json
{
  "name": "finrouter-gateway",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "tsx src/index.ts",
    "build": "tsc",
    "start": "node dist/index.js"
  }
}
```

- [ ] **Step 7: Create Dockerfile**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production=false
COPY . .
RUN npm run build
EXPOSE 3001
CMD ["npm", "start"]
```

- [ ] **Step 8: Smoke-test the gateway**

```bash
cd surfaces/finrouter-gateway
npm run dev &
sleep 3
curl -s http://localhost:3001/health
```

Expected: `{"status":"ok"}`

```bash
curl -s http://localhost:3001/cost/summary
```

Expected: `{"total_cost_usd":0,...}`

Kill the dev server. Then commit.

- [ ] **Step 9: Commit**

```bash
cd ../..
git add surfaces/finrouter-gateway/
git commit -m "feat: finRouter Gateway sidecar (Fastify + finrouter npm)"
```

---

### Task 6: Model router + budget guard

**Files:**
- Create: `core/governance/router.py`
- Create: `core/governance/budget.py`
- Create: `tests/core/governance/test_router.py`
- Create: `tests/core/governance/test_budget.py`

**Interfaces:**
- Produces:
  - `ModelRouter.resolve(task_type: str, tier_override: ModelTier | None) -> tuple[str, str]` (provider, model_id)
  - `ModelRouter.escalate(current_tier: ModelTier, reason: str) -> ModelTier`
  - `BudgetGuard.check(scan_id: UUID, cost_usd: float) -> None` (raises `BudgetExceeded` on hard limit, emits warning on soft)
  - `BudgetGuard.record(scan_id: UUID, cost_usd: float) -> None`
  - `BudgetExceeded(Exception)`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/governance/test_router.py
from __future__ import annotations
import pytest
from core.governance.router import ModelRouter
from core.model.entities import ModelTier


@pytest.fixture
def router():
    return ModelRouter("config/model_tiers.yaml")


def test_fast_tier_resolves_anthropic(router):
    provider, model = router.resolve("explanation", None)
    assert provider == "anthropic"
    assert "haiku" in model.lower()


def test_tier_override(router):
    provider, model = router.resolve("explanation", ModelTier.top)
    assert "opus" in model.lower()


def test_balanced_is_default_for_triage(router):
    provider, model = router.resolve("triage", None)
    assert "sonnet" in model.lower()


def test_escalate_balanced_to_top(router):
    result = router.escalate(ModelTier.balanced, "confidence_lt:0.3")
    assert result == ModelTier.top


def test_escalate_fast_stays_fast_no_rule(router):
    result = router.escalate(ModelTier.fast, "confidence_lt:0.3")
    assert result == ModelTier.fast
```

```python
# tests/core/governance/test_budget.py
from __future__ import annotations
import pytest
from uuid import uuid4
from core.governance.budget import BudgetGuard, BudgetExceeded


@pytest.fixture
def guard():
    return BudgetGuard("config/budget_policy.yaml")


async def test_under_limit_passes(guard):
    scan_id = uuid4()
    guard.check(scan_id, 1.0)   # $1 well under $5 hard limit


async def test_over_hard_limit_raises(guard):
    scan_id = uuid4()
    guard.record(scan_id, 4.99)
    with pytest.raises(BudgetExceeded):
        guard.check(scan_id, 0.02)  # would push to $5.01


async def test_soft_limit_does_not_raise(guard):
    scan_id = uuid4()
    guard.record(scan_id, 3.50)
    # 3.50 + 0.60 = 4.10, over soft (4.00) but under hard (5.00)
    guard.check(scan_id, 0.60)   # should not raise
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/governance/ -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement core/governance/router.py**

```python
# core/governance/router.py
from __future__ import annotations
from pathlib import Path
import yaml
from core.model.entities import ModelTier


class ModelRouter:
    def __init__(self, config_path: str = "config/model_tiers.yaml") -> None:
        raw = yaml.safe_load(Path(config_path).read_text())
        self._default_provider: str = raw["providers"]["default"]
        self._tiers: dict[str, dict[str, str]] = raw["tiers"]
        self._task_defaults: dict[str, str] = raw.get("task_defaults", {})
        self._escalation_rules: list[dict] = raw.get("escalation_rules", [])

    def resolve(
        self,
        task_type: str,
        tier_override: ModelTier | None,
        provider_override: str | None = None,
    ) -> tuple[str, str]:
        tier_name = (
            tier_override.value
            if tier_override and tier_override != ModelTier.none
            else self._task_defaults.get(task_type, "balanced")
        )
        provider = provider_override or self._default_provider
        tier_map = self._tiers.get(tier_name, self._tiers["balanced"])
        model_id = tier_map.get(provider, next(iter(tier_map.values())))
        return provider, model_id

    def escalate(self, current_tier: ModelTier, reason: str) -> ModelTier:
        for rule in self._escalation_rules:
            if rule.get("from_tier") == current_tier.value:
                cond = rule["condition"]
                threshold = rule.get("threshold")
                if self._evaluate(cond, threshold, reason):
                    return ModelTier(rule["to_tier"])
        return current_tier

    def _evaluate(self, condition: str, threshold: float | None, reason: str) -> bool:
        if condition == "confidence_lt" and threshold is not None:
            if "confidence_lt:" in reason:
                val = float(reason.split("confidence_lt:")[1])
                return val < threshold
        if condition == "diff_files_gt" and threshold is not None:
            if "diff_files_gt:" in reason:
                val = float(reason.split("diff_files_gt:")[1])
                return val > threshold
        return False
```

- [ ] **Step 4: Implement core/governance/budget.py**

```python
# core/governance/budget.py
from __future__ import annotations
from pathlib import Path
from uuid import UUID
import yaml
import structlog

log = structlog.get_logger()


class BudgetExceeded(Exception):
    def __init__(self, scan_id: UUID, used: float, limit: float) -> None:
        super().__init__(f"Scan {scan_id} exceeded hard limit ${limit:.2f} (used ${used:.2f})")
        self.scan_id = scan_id
        self.used = used
        self.limit = limit


class BudgetGuard:
    def __init__(self, config_path: str = "config/budget_policy.yaml") -> None:
        raw = yaml.safe_load(Path(config_path).read_text())
        per_scan = raw["per_scan"]
        self._soft = float(per_scan["soft_limit_usd"])
        self._hard = float(per_scan["hard_limit_usd"])
        self._spend: dict[UUID, float] = {}

    def record(self, scan_id: UUID, cost_usd: float) -> None:
        self._spend[scan_id] = self._spend.get(scan_id, 0.0) + cost_usd

    def check(self, scan_id: UUID, prospective_cost: float) -> None:
        used = self._spend.get(scan_id, 0.0)
        projected = used + prospective_cost
        if projected > self._hard:
            raise BudgetExceeded(scan_id, projected, self._hard)
        if projected > self._soft:
            log.warning(
                "budget_soft_limit_approaching",
                scan_id=str(scan_id),
                used_usd=projected,
                soft_limit_usd=self._soft,
            )

    def used(self, scan_id: UUID) -> float:
        return self._spend.get(scan_id, 0.0)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/core/governance/ -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add core/governance/router.py core/governance/budget.py \
        tests/core/governance/
git commit -m "feat: model router and per-scan budget guard"
```

---

### Task 7: GovernanceGate

**Files:**
- Create: `core/governance/gate.py`
- Create: `tests/core/governance/test_gate.py`

**Interfaces:**
- Consumes: `ModelRouter.resolve()`, `BudgetGuard.check()`, `BudgetGuard.record()`
- Produces: `GovernanceGate.complete(task_type, messages, agent_id, scan_id, tier_override?) -> GateResult`; `GateResult(content, tokens_in, tokens_out, cache_hit, model_id, provider, tier, cost_usd)`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/governance/test_gate.py
from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from core.governance.gate import GovernanceGate, GateResult
from core.governance.budget import BudgetExceeded
from core.model.entities import ModelTier


@pytest.fixture
def gate():
    return GovernanceGate(
        router_config="config/model_tiers.yaml",
        budget_config="config/budget_policy.yaml",
        gateway_url="http://localhost:3001",
    )


async def test_complete_returns_gate_result(gate, respx_mock):
    scan_id = uuid4()
    respx_mock.post("http://localhost:3001/chat").mock(
        return_value=respx_mock.response(200, json={
            "content": "This is a SQL injection vulnerability.",
            "usage": {
                "tokens_in": 500,
                "tokens_out": 100,
                "cache_hit": False,
                "cost_usd": 0.0025,
                "model_id": "claude-sonnet-4-6",
                "provider": "anthropic",
            }
        })
    )
    result = await gate.complete(
        task_type="explanation",
        messages=[{"role": "user", "content": "Explain this finding."}],
        agent_id="explainer",
        scan_id=scan_id,
    )
    assert isinstance(result, GateResult)
    assert result.content == "This is a SQL injection vulnerability."
    assert result.tokens_in == 500
    assert result.cost_usd == 0.0025


async def test_budget_exceeded_raises(gate, respx_mock):
    scan_id = uuid4()
    # Pre-load budget to near limit
    gate._budget.record(scan_id, 4.99)
    respx_mock.post("http://localhost:3001/chat").mock(
        return_value=respx_mock.response(200, json={
            "content": "x",
            "usage": {"tokens_in": 100, "tokens_out": 20, "cache_hit": False,
                      "cost_usd": 0.10, "model_id": "claude-sonnet-4-6", "provider": "anthropic"}
        })
    )
    with pytest.raises(BudgetExceeded):
        await gate.complete(
            task_type="triage",
            messages=[{"role": "user", "content": "triage"}],
            agent_id="triage",
            scan_id=scan_id,
        )
```

- [ ] **Step 2: Install respx for httpx mocking**

```bash
pip install respx pytest-respx
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/core/governance/test_gate.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement core/governance/gate.py**

```python
# core/governance/gate.py
from __future__ import annotations
import os
from uuid import UUID
import httpx
import structlog
from pydantic import BaseModel
from core.governance.router import ModelRouter
from core.governance.budget import BudgetGuard, BudgetExceeded
from core.model.entities import ModelTier

log = structlog.get_logger()


class GateResult(BaseModel):
    content: str
    tokens_in: int
    tokens_out: int
    cache_hit: bool
    model_id: str
    provider: str
    tier: ModelTier
    cost_usd: float


class GovernanceGate:
    def __init__(
        self,
        router_config: str = "config/model_tiers.yaml",
        budget_config: str = "config/budget_policy.yaml",
        gateway_url: str | None = None,
    ) -> None:
        self._router = ModelRouter(router_config)
        self._budget = BudgetGuard(budget_config)
        self._gateway_url = gateway_url or os.environ.get(
            "FINROUTER_GATEWAY_URL", "http://localhost:3001"
        )

    async def complete(
        self,
        task_type: str,
        messages: list[dict],
        agent_id: str,
        scan_id: UUID,
        tier_override: ModelTier | None = None,
        provider_override: str | None = None,
        zero_retention: bool = True,
    ) -> GateResult:
        provider, model_id = self._router.resolve(task_type, tier_override, provider_override)
        tier = ModelTier(self._router._task_defaults.get(task_type, "balanced")) if not tier_override else tier_override

        # Pre-flight budget check with a conservative estimate
        estimated_cost = len(str(messages)) / 1000 * 0.003
        self._budget.check(scan_id, estimated_cost)

        payload = {
            "model": model_id,
            "messages": messages,
            "provider": provider,
            "zero_retention": zero_retention,
        }

        log.info("llm_call_start", agent=agent_id, model=model_id, provider=provider, scan_id=str(scan_id))

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._gateway_url}/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        usage = data["usage"]
        result = GateResult(
            content=data["content"],
            tokens_in=usage["tokens_in"],
            tokens_out=usage["tokens_out"],
            cache_hit=usage.get("cache_hit", False),
            model_id=usage["model_id"],
            provider=usage["provider"],
            tier=tier,
            cost_usd=usage["cost_usd"],
        )

        self._budget.record(scan_id, result.cost_usd)

        log.info(
            "llm_call_complete",
            agent=agent_id,
            model=model_id,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            scan_id=str(scan_id),
        )

        return result
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/core/governance/test_gate.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add core/governance/gate.py tests/core/governance/test_gate.py
git commit -m "feat: GovernanceGate — single LLM call chokepoint via finRouter"
```

---

### Task 8: Cost ledger + SSE event emitter

**Files:**
- Create: `core/governance/ledger.py`
- Create: `core/governance/events.py`
- Create: `tests/core/governance/test_ledger.py`
- Create: `tests/core/governance/test_events.py`

**Interfaces:**
- Produces:
  - `CostLedger.record(entry: CostLedgerEntry, session: AsyncSession) -> None`
  - `CostLedger.scan_summary(scan_id: UUID, session: AsyncSession) -> dict`
  - `ScanEventBus.emit(scan_id: UUID, event: dict) -> None`
  - `ScanEventBus.subscribe(scan_id: UUID) -> AsyncGenerator[dict, None]`
  - `ScanEventBus` — singleton accessible as `event_bus`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/governance/test_ledger.py
from __future__ import annotations
import pytest
from uuid import uuid4
from core.governance.ledger import CostLedger
from core.model.entities import CostLedgerEntry, ModelTier

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session():
    # Use in-memory SQLite for unit tests
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.db.tables import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_record_and_retrieve(session):
    ledger = CostLedger()
    scan_id = uuid4()
    entry = CostLedgerEntry(
        scope_type="scan",
        scope_id=scan_id,
        tokens_in=1000,
        tokens_out=200,
        tier=ModelTier.balanced,
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        cost_usd=0.006,
    )
    await ledger.record(entry, session)
    summary = await ledger.scan_summary(scan_id, session)
    assert summary["total_cost_usd"] == pytest.approx(0.006)
    assert summary["total_tokens_in"] == 1000
```

```python
# tests/core/governance/test_events.py
from __future__ import annotations
import asyncio
import pytest
from uuid import uuid4
from core.governance.events import ScanEventBus


async def test_emit_and_receive():
    bus = ScanEventBus()
    scan_id = uuid4()
    received = []

    async def collect():
        async for event in bus.subscribe(scan_id):
            received.append(event)
            if event.get("event") == "scan_completed":
                break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.01)
    bus.emit(scan_id, {"event": "agent_started", "agent": "triage"})
    bus.emit(scan_id, {"event": "scan_completed"})
    await task

    assert len(received) == 2
    assert received[0]["event"] == "agent_started"
```

- [ ] **Step 2: Install aiosqlite for tests**

```bash
pip install aiosqlite
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/core/governance/test_ledger.py tests/core/governance/test_events.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement core/governance/ledger.py**

```python
# core/governance/ledger.py
from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.db.tables import CostLedgerEntryRow
from core.model.entities import CostLedgerEntry
import structlog

log = structlog.get_logger()


class CostLedger:
    async def record(self, entry: CostLedgerEntry, session: AsyncSession) -> None:
        row = CostLedgerEntryRow(
            id=str(entry.id),
            scope_type=entry.scope_type,
            scope_id=str(entry.scope_id),
            tokens_in=entry.tokens_in,
            tokens_out=entry.tokens_out,
            cache_hits=entry.cache_hits,
            tier=entry.tier.value,
            provider=entry.provider,
            model_id=entry.model_id,
            batch_flag=entry.batch_flag,
            cost_usd=entry.cost_usd,
            timestamp=entry.timestamp,
        )
        session.add(row)
        await session.flush()
        log.info(
            "cost_ledger_entry",
            scope_type=entry.scope_type,
            scope_id=str(entry.scope_id),
            cost_usd=entry.cost_usd,
            model_id=entry.model_id,
        )

    async def scan_summary(self, scan_id: UUID, session: AsyncSession) -> dict:
        result = await session.execute(
            select(
                func.sum(CostLedgerEntryRow.cost_usd).label("total_cost_usd"),
                func.sum(CostLedgerEntryRow.tokens_in).label("total_tokens_in"),
                func.sum(CostLedgerEntryRow.tokens_out).label("total_tokens_out"),
                func.sum(CostLedgerEntryRow.cache_hits).label("total_cache_hits"),
                func.count().label("call_count"),
            ).where(
                CostLedgerEntryRow.scope_id == str(scan_id),
                CostLedgerEntryRow.scope_type == "scan",
            )
        )
        row = result.one()
        return {
            "total_cost_usd": float(row.total_cost_usd or 0),
            "total_tokens_in": int(row.total_tokens_in or 0),
            "total_tokens_out": int(row.total_tokens_out or 0),
            "total_cache_hits": int(row.total_cache_hits or 0),
            "call_count": int(row.call_count or 0),
        }
```

- [ ] **Step 5: Implement core/governance/events.py**

```python
# core/governance/events.py
from __future__ import annotations
import asyncio
from uuid import UUID
from typing import AsyncGenerator


class ScanEventBus:
    def __init__(self) -> None:
        self._queues: dict[UUID, list[asyncio.Queue]] = {}

    def emit(self, scan_id: UUID, event: dict) -> None:
        for q in self._queues.get(scan_id, []):
            q.put_nowait(event)

    async def subscribe(self, scan_id: UUID) -> AsyncGenerator[dict, None]:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(scan_id, []).append(q)
        try:
            while True:
                event = await q.get()
                yield event
                if event.get("event") in ("scan_completed", "scan_failed", "scan_cancelled"):
                    break
        finally:
            self._queues[scan_id].remove(q)
            if not self._queues[scan_id]:
                del self._queues[scan_id]


event_bus = ScanEventBus()
```

- [ ] **Step 6: Run — expect pass**

```bash
pytest tests/core/governance/test_ledger.py tests/core/governance/test_events.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add core/governance/ledger.py core/governance/events.py \
        tests/core/governance/test_ledger.py tests/core/governance/test_events.py
git commit -m "feat: cost ledger (PostgreSQL) and SSE event bus"
```

---

*Foundation plan complete. Continue with [2026-06-17-phase1-scanning.md] for Tasks 9–12 (ingestion, SARIF mapper, Semgrep, TruffleHog) and [2026-06-17-phase1-agents-api.md] for Tasks 13–16.*
