from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from core.agents.ingestion import IngestionAgent
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Scan, ScanMode, ScanStatus, ModelTier
from core.understanding.context import CodeContext


@pytest.fixture
def ctx():
    scan = Scan(
        target_ref=str(Path("tests/fixtures/vulnerable_python").resolve()),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    gate = MagicMock()
    return AgentContext(scan=scan, skills=[], budget_slice_usd=0.25, gate=gate)


async def test_ingestion_detects_python(ctx):
    agent = IngestionAgent()
    result = await agent.run(ctx)
    assert isinstance(result, AgentOutput)
    assert result.skipped is False
    cc: CodeContext = CodeContext.model_validate(result.data["code_context"])
    assert "python" in cc.languages
    assert cc.file_count >= 1


async def test_ingestion_builds_repo_map(ctx):
    agent = IngestionAgent()
    result = await agent.run(ctx)
    cc = CodeContext.model_validate(result.data["code_context"])
    assert "app.py" in cc.repo_map
