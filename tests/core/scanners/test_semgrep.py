from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4
from core.scanners.semgrep import SemgrepAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode
from core.understanding.context import CodeContext


@pytest.fixture
def ctx():
    scan = Scan(
        target_ref=str(Path("tests/fixtures/vulnerable_python").resolve()),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    cc = CodeContext(
        root=str(Path("tests/fixtures/vulnerable_python").resolve()),
        languages={"python": 1},
        frameworks=[],
        file_count=1,
        repo_map="app.py",
        entry_points=["app.py"],
    )
    gate = MagicMock()
    return AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=gate,
        extra={"code_context": cc.model_dump()},
    )


async def test_semgrep_finds_sql_injection(ctx):
    adapter = SemgrepAdapter()
    result = await adapter.scan(ctx)
    findings = result.data["findings"]
    assert len(findings) >= 1
    rule_ids = [f["rule_id"] for f in findings]
    assert any("sql" in rid.lower() or "injection" in rid.lower() for rid in rule_ids)


async def test_semgrep_cost_is_zero(ctx):
    adapter = SemgrepAdapter()
    result = await adapter.scan(ctx)
    assert result.cost_usd == 0.0
