from __future__ import annotations
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from pathlib import Path
from core.skills.creator import SkillCreatorAgent
from core.skills.base import Skill, SkillLoader
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode


_GENERATED_SKILL = {
    "name": "jwt-analysis",
    "version": 1,
    "description": "Detect JWT implementation vulnerabilities",
    "languages": ["python", "javascript"],
    "frameworks": [],
    "activation": "active",
    "body": (
        "- Check for algorithm confusion (alg:none)\n"
        "- Verify signature validation is not skipped\n"
        "- Check for hardcoded signing secrets"
    ),
    "rules_dir": None,
}


def _make_ctx(gate_response: str) -> AgentContext:
    scan = Scan(target_ref="/repo", pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    gate = AsyncMock()
    gate.complete = AsyncMock(return_value=MagicMock(
        content=gate_response,
        cost_usd=0.08,
    ))
    return AgentContext(scan=scan, skills=[], budget_slice_usd=2.0, gate=gate, extra={})


@pytest.mark.asyncio
async def test_creator_generates_and_saves_skill(tmp_path):
    loader = SkillLoader(builtin_dir=tmp_path / "builtin", generated_dir=tmp_path / "gen")
    ctx = _make_ctx(json.dumps(_GENERATED_SKILL))

    creator = SkillCreatorAgent(loader=loader)
    skill, path = await creator.create(
        name="jwt-analysis",
        description="Detect JWT vulnerabilities",
        languages=["python", "javascript"],
        frameworks=[],
        examples=[],
        ctx=ctx,
    )

    assert skill.name == "jwt-analysis"
    assert skill.activation == "active"
    assert path.exists()
    assert path.suffix == ".yaml"


@pytest.mark.asyncio
async def test_creator_raises_on_json_parse_error(tmp_path):
    loader = SkillLoader(builtin_dir=tmp_path / "builtin", generated_dir=tmp_path / "gen")
    ctx = _make_ctx("```not valid json```")

    creator = SkillCreatorAgent(loader=loader)
    with pytest.raises(ValueError, match="non-JSON"):
        await creator.create(
            name="jwt-analysis",
            description="desc",
            languages=[],
            frameworks=[],
            examples=[],
            ctx=ctx,
        )


@pytest.mark.asyncio
async def test_creator_sends_examples_in_prompt(tmp_path):
    loader = SkillLoader(builtin_dir=tmp_path / "builtin", generated_dir=tmp_path / "gen")
    ctx = _make_ctx(json.dumps(_GENERATED_SKILL))

    examples = [{"rule_id": "jwt-none-alg", "severity": "critical"}]
    creator = SkillCreatorAgent(loader=loader)
    await creator.create(
        name="jwt-analysis",
        description="desc",
        languages=["python"],
        frameworks=[],
        examples=examples,
        ctx=ctx,
    )

    call_args = ctx.gate.complete.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "jwt-none-alg" in user_msg


@pytest.mark.asyncio
async def test_creator_run_skips_when_no_params(tmp_path):
    loader = SkillLoader(builtin_dir=tmp_path / "builtin", generated_dir=tmp_path / "gen")
    ctx = _make_ctx(json.dumps(_GENERATED_SKILL))
    ctx.extra = {}

    creator = SkillCreatorAgent(loader=loader)
    result = await creator.run(ctx)

    assert result.skipped
    assert result.skip_reason == "missing_params"
