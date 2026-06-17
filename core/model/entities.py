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
