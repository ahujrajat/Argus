from __future__ import annotations
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from core.agents.pattern import PatternAgent
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode


_PATTERN_RESPONSE = {
    "hotspots": [
        {"file": "app/auth.py", "finding_count": 3, "dominant_cwe": "CWE-89", "summary": "SQL injection in auth"},
    ],
    "vulnerability_clusters": [
        {
            "name": "SQL Injection cluster",
            "description": "Multiple SQLi findings in data access layer",
            "finding_count": 2,
            "cwe_list": ["CWE-89"],
            "affected_files": ["app/auth.py", "app/db.py"],
        }
    ],
    "gap_analysis": {
        "observed_categories": ["semgrep", "trufflehog"],
        "potential_gaps": ["No SCA scanner results — dependency vulnerabilities unchecked"],
    },
    "recommendations": ["Add Grype SCA scan to pipeline", "Focus remediation on auth.py"],
}

_FINDINGS = [
    {"rule_id": "CWE-89", "source_tool": "semgrep", "severity": "high",
     "dedup_key": "k1", "location": {"file": "app/auth.py", "line_start": 10, "line_end": 12}},
    {"rule_id": "CWE-89", "source_tool": "semgrep", "severity": "high",
     "dedup_key": "k2", "location": {"file": "app/db.py", "line_start": 20, "line_end": 22}},
]


def _make_ctx(extra: dict | None = None) -> AgentContext:
    scan = Scan(target_ref="/repo", pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    gate = AsyncMock()
    gate.complete = AsyncMock(return_value=MagicMock(
        content=json.dumps(_PATTERN_RESPONSE),
        cost_usd=0.05,
        tokens_in=800,
        tokens_out=300,
    ))
    return AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=1.0,
        gate=gate,
        extra=extra or {"triaged_findings": _FINDINGS},
    )


@pytest.mark.asyncio
async def test_pattern_agent_returns_summary():
    ctx = _make_ctx()
    result = await PatternAgent().run(ctx)

    assert not result.skipped
    summary = result.data["pattern_summary"]
    assert len(summary["hotspots"]) == 1
    assert summary["hotspots"][0]["file"] == "app/auth.py"
    assert len(summary["vulnerability_clusters"]) == 1
    assert len(summary["recommendations"]) == 2


@pytest.mark.asyncio
async def test_pattern_agent_fallback_on_json_error():
    scan = Scan(target_ref="/repo", pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    gate = AsyncMock()
    gate.complete = AsyncMock(return_value=MagicMock(
        content="not json ```",
        cost_usd=0.01,
    ))
    ctx = AgentContext(scan=scan, skills=[], budget_slice_usd=1.0, gate=gate,
                       extra={"triaged_findings": _FINDINGS})

    result = await PatternAgent().run(ctx)

    assert not result.skipped
    summary = result.data["pattern_summary"]
    assert summary["hotspots"] == []
    assert summary["vulnerability_clusters"] == []
    assert "gap_analysis" in summary


@pytest.mark.asyncio
async def test_pattern_agent_uses_raw_findings_when_no_triage():
    ctx = _make_ctx(extra={"findings": _FINDINGS})
    result = await PatternAgent().run(ctx)
    assert not result.skipped
    assert "pattern_summary" in result.data


@pytest.mark.asyncio
async def test_pattern_agent_records_cost():
    ctx = _make_ctx()
    result = await PatternAgent().run(ctx)
    assert result.cost_usd == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_pattern_agent_passes_scanner_names_to_prompt():
    ctx = _make_ctx()
    result = await PatternAgent().run(ctx)

    call_args = ctx.gate.complete.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "semgrep" in user_msg
