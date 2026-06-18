# tests/core/agents/test_fix.py
from __future__ import annotations
import json
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from core.agents.fix import FixAgent
from core.agents.base import AgentContext
from core.model.entities import (
    Scan, ScanMode, SecurityApproach, ModelTier, FindingStatus,
)
from core.governance.gate import GateResult


def _make_scan() -> Scan:
    return Scan(
        target_ref="/tmp/fake_repo",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
        approach=SecurityApproach.penetration_testing,
    )


def _make_finding(exploit_likelihood: float = 0.85, status: str = "open") -> dict:
    return {
        "id": str(uuid4()),
        "scan_id": str(uuid4()),
        "rule_id": "python.lang.security.audit.formatted-sql-query.formatted-sql-query",
        "source_tool": "semgrep",
        "cwe": "CWE-89",
        "owasp_category": "A03:2021",
        "severity": "high",
        "exploit_likelihood": exploit_likelihood,
        "confidence": 0.9,
        "reachability": "reachable from HTTP input",
        "attack_scenario": "Attacker injects SQL via username parameter.",
        "location": {
            "file": "app.py",
            "line_start": 5,
            "line_end": 5,
            "snippet": "query = f\"SELECT * FROM users WHERE name='{username}'\"",
        },
        "dedup_key": "semgrep:sql-injection:app.py:5",
        "status": status,
        "explanation": "String interpolation used in SQL query.",
    }


MOCK_FIX_RESPONSE = json.dumps({
    "diff": (
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -5,1 +5,1 @@\n"
        "-    query = f\"SELECT * FROM users WHERE name='{username}'\"\n"
        "+    query = \"SELECT * FROM users WHERE name=%s\"\n"
    ),
    "test": "def test_no_sql_injection(): ...",
    "explanation": "Replaced string interpolation with parameterized query.",
    "confidence": 0.95,
})


@pytest.fixture
def mock_gate():
    gate = MagicMock()
    gate.complete = AsyncMock(return_value=GateResult(
        content=MOCK_FIX_RESPONSE,
        tokens_in=1200,
        tokens_out=300,
        cache_hit=False,
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        tier=ModelTier.balanced,
        cost_usd=0.009,
    ))
    return gate


async def test_fix_agent_returns_fixes_for_eligible_findings(mock_gate, tmp_path):
    src = tmp_path / "app.py"
    src.write_text("query = f\"SELECT * FROM users WHERE name='{username}'\"\n")

    scan = _make_scan()
    scan.target_ref = str(tmp_path)

    ctx = AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=mock_gate,
        approach=SecurityApproach.penetration_testing,
        extra={"triaged_findings": [_make_finding(exploit_likelihood=0.85)]},
    )

    agent = FixAgent()
    output = await agent.run(ctx)

    assert not output.skipped
    fixes = output.data["fixes"]
    assert len(fixes) == 1
    fix = fixes[0]
    assert fix["finding_id"] is not None
    assert "--- a/app.py" in fix["diff"]
    assert fix["status"] == "proposed"
    assert fix["explanation"] == "Replaced string interpolation with parameterized query."
    assert output.cost_usd == pytest.approx(0.009)


async def test_fix_agent_skips_low_exploit_likelihood(mock_gate, tmp_path):
    scan = _make_scan()
    scan.target_ref = str(tmp_path)
    ctx = AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=mock_gate,
        approach=SecurityApproach.penetration_testing,
        extra={"triaged_findings": [_make_finding(exploit_likelihood=0.4)]},
    )
    output = await FixAgent().run(ctx)
    assert output.data["fixes"] == []
    mock_gate.complete.assert_not_called()


async def test_fix_agent_skips_non_open_findings(mock_gate, tmp_path):
    scan = _make_scan()
    scan.target_ref = str(tmp_path)
    ctx = AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=mock_gate,
        approach=SecurityApproach.penetration_testing,
        extra={"triaged_findings": [_make_finding(exploit_likelihood=0.9, status="dismissed")]},
    )
    output = await FixAgent().run(ctx)
    assert output.data["fixes"] == []


async def test_fix_agent_uses_explained_findings_when_no_triaged(mock_gate, tmp_path):
    src = tmp_path / "app.py"
    src.write_text("x = 1\n")
    scan = _make_scan()
    scan.target_ref = str(tmp_path)
    ctx = AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=mock_gate,
        approach=SecurityApproach.penetration_testing,
        extra={"explained_findings": [_make_finding(exploit_likelihood=0.85)]},
    )
    output = await FixAgent().run(ctx)
    assert len(output.data["fixes"]) == 1


async def test_fix_agent_uses_complex_fix_tier_for_large_file(mock_gate, tmp_path):
    src = tmp_path / "app.py"
    src.write_text("\n".join(["x = 1"] * 250))
    scan = _make_scan()
    scan.target_ref = str(tmp_path)
    ctx = AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=mock_gate,
        approach=SecurityApproach.penetration_testing,
        extra={"triaged_findings": [_make_finding(exploit_likelihood=0.85)]},
    )
    await FixAgent().run(ctx)
    call_kwargs = mock_gate.complete.call_args
    assert call_kwargs.kwargs.get("tier_override") == ModelTier.top


async def test_fix_agent_handles_json_parse_error(mock_gate, tmp_path):
    src = tmp_path / "app.py"
    src.write_text("x = 1\n")
    mock_gate.complete = AsyncMock(return_value=GateResult(
        content="not valid json",
        tokens_in=100, tokens_out=10,
        cache_hit=False, model_id="claude-sonnet-4-6",
        provider="anthropic", tier=ModelTier.balanced, cost_usd=0.001,
    ))
    scan = _make_scan()
    scan.target_ref = str(tmp_path)
    ctx = AgentContext(
        scan=scan, skills=[], budget_slice_usd=0.0,
        gate=mock_gate, approach=SecurityApproach.penetration_testing,
        extra={"triaged_findings": [_make_finding(exploit_likelihood=0.85)]},
    )
    output = await FixAgent().run(ctx)
    assert output.data["fixes"] == []


async def test_fix_agent_redacts_snippet_before_llm_call(mock_gate, tmp_path):
    src = tmp_path / "app.py"
    src.write_text("api_key = 'sk-ant-abcdefghijklmnopqrstuvwxyz1234567890ABCD'\n")
    scan = _make_scan()
    scan.target_ref = str(tmp_path)
    finding = _make_finding(exploit_likelihood=0.85)
    finding["location"]["snippet"] = "api_key = 'sk-ant-abcdefghijklmnopqrstuvwxyz1234567890ABCD'"
    ctx = AgentContext(
        scan=scan, skills=[], budget_slice_usd=0.0,
        gate=mock_gate, approach=SecurityApproach.penetration_testing,
        extra={"triaged_findings": [finding]},
    )
    await FixAgent().run(ctx)
    call_args = mock_gate.complete.call_args
    messages = call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "sk-ant-" not in user_content
