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
    approach = Column(String, nullable=False, default="penetration_testing")
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
