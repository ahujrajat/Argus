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


async def test_trufflehog_scans_without_error(ctx):
    # The fixture secret was sanitized (git-filter-repo replaced the real Stripe key with
    # ARGUS_FIXTURE_sk_XXX...) so TruffleHog finds 0 findings — that is correct and expected.
    adapter = TruffleHogAdapter()
    result = await adapter.scan(ctx)
    assert "findings" in result.data
    assert result.cost_usd == 0.0
    # Verify redaction still works for any finding that IS returned
    for f in result.data["findings"]:
        location = f.get("location", {})
        assert location.get("snippet") == "[REDACTED]"


async def test_trufflehog_cost_is_zero(ctx):
    # cost is covered by test_trufflehog_scans_without_error but kept for clarity
    adapter = TruffleHogAdapter()
    result = await adapter.scan(ctx)
    assert result.cost_usd == 0.0  # scanner adapters never call the LLM
