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
