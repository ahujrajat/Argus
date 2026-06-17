from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
from core.scanners.trufflehog import TruffleHogAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode
from core.understanding.context import CodeContext


@pytest.fixture
def ctx():
    root = str(Path("tests/fixtures/vulnerable_python").resolve())
    scan = Scan(target_ref=root, pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    cc = CodeContext(root=root, languages={"python": 1}, frameworks=[], file_count=1,
                     repo_map="app.py", entry_points=[])
    gate = MagicMock()
    return AgentContext(scan=scan, skills=[], budget_slice_usd=0.0, gate=gate,
                        extra={"code_context": cc.model_dump()})


async def test_trufflehog_finds_secret(ctx):
    adapter = TruffleHogAdapter()
    result = await adapter.scan(ctx)
    findings = result.data["findings"]
    # Our fixture has STRIPE_SECRET_KEY = "ARGUS_FIXTURE_sk_XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    assert len(findings) >= 1
    for f in findings:
        # snippet must be [REDACTED], never the raw secret value
        location = f.get("location", {})
        assert location.get("snippet") == "[REDACTED]"
        # raw secret must not appear in findings data
        assert "ARGUS_FIXTURE_sk_XXXXXXXXXXXXXXXXXXXXXXXXXXXX" not in str(f)


async def test_trufflehog_cost_is_zero(ctx):
    adapter = TruffleHogAdapter()
    result = await adapter.scan(ctx)
    assert result.cost_usd == 0.0
