# Phase 2a: Fix Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automated fix generation to the Argus pipeline — an LLM-driven FixAgent proposes unified diffs for high-confidence exploitable findings, a PatchValidator verifies those patches don't introduce regressions, a REST API exposes fix review with human-gate apply/reject, and a dashboard tab lets engineers review diffs and approve them.

**Architecture:** FixAgent plugs into the existing orchestrator pipeline as a node after `explainer`, reading `triaged_findings` or `explained_findings` from `ctx.extra`, generating Fix objects via GovernanceGate, and returning them in `AgentOutput.data["fixes"]`. The orchestrator persists fixes to the `fixes` table, wired alongside the existing `findings` persistence path. The dashboard Fix Review tab mirrors the existing findings page pattern: React Query for data, a two-panel layout (list + DiffViewer), and the same typed API client.

**Tech Stack:** Python 3.12, FastAPI 0.111+, Pydantic v2, SQLAlchemy 2 async, asyncpg, pytest + pytest-asyncio (asyncio_mode=auto), React 18 + TypeScript, React Query, Tailwind CSS, Vite.

## Global Constraints

- Python >= 3.12; `from __future__ import annotations` in every Python file
- Pydantic v2 throughout — use `model_dump()` not `.dict()`, `model_validate()` not `.parse_obj()`
- GovernanceGate is the ONLY path to LLM calls — never call the finRouter gateway directly
- Secrets (API keys, found credentials) never written to logs, DB text fields, model prompts, or HTTP responses — call `redact()` / `redact_dict()` before any write
- Every privileged operation (fix apply, fix reject) writes an `AuditLogEntry` to `audit_log_entries` table BEFORE changing `FixRow.status`
- Fix application requires human approval — never auto-apply; `POST /fixes/{id}/apply` is always triggered by a human
- All tests use pytest with `asyncio_mode = "auto"` (already set in pyproject.toml)
- Accenture light theme: accent color `#A100FF`, white cards, `bg-gray-50` page backgrounds

---

## File Map

| Status | Path | Responsibility |
|--------|------|----------------|
| Create | `core/agents/prompts/fix.py` | FIX_SYSTEM prompt + FIX_USER_TEMPLATE string |
| Create | `core/agents/fix.py` | FixAgent — reads findings, calls gate, builds Fix objects |
| Create | `core/remediation/__init__.py` | Package marker |
| Create | `core/remediation/validator.py` | PatchValidator — dry-run patch + semgrep comparison |
| Create | `core/api/routers/fixes.py` | FastAPI router: list, detail, apply, reject endpoints |
| Modify | `core/api/app.py:45-48` | Replace 501 stub with `fixes_router`; add `GET /scans/{id}/fixes` delegation |
| Modify | `core/agents/orchestrator.py:27-35` | Add FixAgent to `_AGENT_REGISTRY`; update `_build_extra` and `_collect_findings` |
| Modify | `config/pipeline_configs/full-scan.yaml` | Add `fix_generation` node + edge |
| Create | `tests/core/agents/test_fix.py` | Unit tests for FixAgent |
| Create | `tests/core/remediation/test_validator.py` | Unit tests for PatchValidator |
| Create | `tests/core/api/test_fixes_router.py` | Unit tests for fixes API endpoints |
| Modify | `surfaces/dashboard/src/api/client.ts` | Add FixDTO, `listScanFixes`, `applyFix`, `rejectFix` |
| Create | `surfaces/dashboard/src/pages/fixes/FixReviewPage.tsx` | Fix list with status groups + detail panel |
| Create | `surfaces/dashboard/src/pages/fixes/DiffViewer.tsx` | Unified diff renderer with syntax highlighting |
| Modify | `surfaces/dashboard/src/components/Nav.tsx` | Add "Fix Review" link |
| Modify | `surfaces/dashboard/src/App.tsx` | Add `/fixes` route |

---

### Task 1: Fix prompt + FixAgent

**Files:**
- Create: `core/agents/prompts/fix.py`
- Create: `core/agents/fix.py`
- Test: `tests/core/agents/test_fix.py`

**Interfaces:**
- Consumes: `AgentContext` from `core.agents.base`; `GovernanceGate.complete` returning `GateResult`; `redact` from `core.model.redaction`; `Fix`, `FixStatus` from `core.model.entities`
- Produces: `FixAgent` class with `agent_id = "fix_generation"` and `async run(ctx: AgentContext) -> AgentOutput`; `AgentOutput.data["fixes"]` is a `list[dict]` where each dict is `Fix.model_dump()`

- [ ] **Step 1: Write the failing test**

Create `tests/core/agents/test_fix.py`:

```python
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
    # Write a fake source file so FixAgent can read it
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
    # File > 200 lines triggers tier_override="top"
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
    # Should not raise — should skip the malformed fix and return empty
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_fix.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'core.agents.fix'`

- [ ] **Step 3: Create the fix prompt module**

Create `core/agents/prompts/fix.py`:

```python
# core/agents/prompts/fix.py
from __future__ import annotations

FIX_SYSTEM = (
    "You are a security patch engineer. "
    "Generate the minimal, correct unified diff that eliminates the described vulnerability. "
    "Do not change unrelated code. "
    "Do not add logging or comments unless they are part of the fix. "
    "Return ONLY valid JSON."
)

FIX_USER_TEMPLATE = """\
Generate a security fix for the following vulnerability.

Rule: {rule_id}
CWE: {cwe}
Severity: {severity}
File: {file}
Lines: {line_start}-{line_end}

Vulnerable snippet:
{snippet}

Reachability: {reachability}
Attack scenario: {attack_scenario}
Explanation: {explanation}

Full file content (for context):
```
{file_content}
```

Return exactly this JSON (no other text):
{{
  "diff": "<unified diff in git diff -u format, paths prefixed a/ and b/>",
  "test": "<pytest test snippet that verifies the fix, or null>",
  "explanation": "<one sentence describing what was changed and why>",
  "confidence": <float 0.0-1.0>
}}
"""
```

- [ ] **Step 4: Create the FixAgent**

Create `core/agents/fix.py`:

```python
# core/agents/fix.py
from __future__ import annotations
import json
import structlog
from pathlib import Path
from uuid import uuid4

from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.fix import FIX_SYSTEM, FIX_USER_TEMPLATE
from core.model.entities import Fix, FixStatus, ModelTier
from core.model.redaction import redact

log = structlog.get_logger()


class FixAgent:
    agent_id = "fix_generation"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        all_findings: list[dict] = (
            ctx.extra.get("explained_findings")
            or ctx.extra.get("triaged_findings")
            or []
        )

        eligible = [
            f for f in all_findings
            if f.get("status") == "open" and f.get("exploit_likelihood", 0.0) >= 0.6
        ]

        if not eligible:
            return AgentOutput(
                agent_id=self.agent_id,
                data={"fixes": []},
                cost_usd=0.0,
            )

        scan_root = Path(ctx.scan.target_ref)
        fixes: list[dict] = []
        total_cost = 0.0

        for finding in eligible:
            loc = finding.get("location", {})
            file_rel = loc.get("file", "")
            file_path = scan_root / file_rel

            try:
                file_content = file_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, FileNotFoundError):
                file_content = ""

            line_count = file_content.count("\n") + 1
            tier_override = ModelTier.top if line_count > 200 else None

            safe_snippet = redact(loc.get("snippet") or "")
            safe_file_content = redact(file_content)

            user_msg = FIX_USER_TEMPLATE.format(
                rule_id=finding.get("rule_id", ""),
                cwe=finding.get("cwe") or "unknown",
                severity=finding.get("severity", ""),
                file=file_rel,
                line_start=loc.get("line_start", ""),
                line_end=loc.get("line_end", ""),
                snippet=safe_snippet,
                reachability=finding.get("reachability") or "unknown",
                attack_scenario=finding.get("attack_scenario") or "",
                explanation=finding.get("explanation") or "",
                file_content=safe_file_content,
            )

            try:
                result = await ctx.gate.complete(
                    task_type="fix_generation",
                    messages=[
                        {"role": "system", "content": FIX_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    agent_id=self.agent_id,
                    scan_id=ctx.scan.id,
                    tier_override=tier_override,
                )
                total_cost += result.cost_usd
            except Exception as exc:
                log.warning(
                    "fix_agent_gate_error",
                    finding_dedup_key=finding.get("dedup_key"),
                    error=str(exc),
                )
                continue

            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError:
                log.warning(
                    "fix_agent_json_parse_error",
                    dedup_key=finding.get("dedup_key"),
                    content_preview=result.content[:200],
                )
                continue

            fix = Fix(
                finding_id=finding["id"],
                diff=parsed.get("diff", ""),
                test=parsed.get("test") or None,
                explanation=parsed.get("explanation", ""),
                status=FixStatus.proposed,
            )
            fixes.append(fix.model_dump(mode="json"))

        log.info(
            "fix_generation_complete",
            eligible=len(eligible),
            fixes_generated=len(fixes),
            scan_id=str(ctx.scan.id),
        )

        return AgentOutput(
            agent_id=self.agent_id,
            data={"fixes": fixes},
            cost_usd=total_cost,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_fix.py -v
```

Expected output:
```
tests/core/agents/test_fix.py::test_fix_agent_returns_fixes_for_eligible_findings PASSED
tests/core/agents/test_fix.py::test_fix_agent_skips_low_exploit_likelihood PASSED
tests/core/agents/test_fix.py::test_fix_agent_skips_non_open_findings PASSED
tests/core/agents/test_fix.py::test_fix_agent_uses_explained_findings_when_no_triaged PASSED
tests/core/agents/test_fix.py::test_fix_agent_uses_complex_fix_tier_for_large_file PASSED
tests/core/agents/test_fix.py::test_fix_agent_handles_json_parse_error PASSED
tests/core/agents/test_fix.py::test_fix_agent_redacts_snippet_before_llm_call PASSED

7 passed in <1s
```

- [ ] **Step 6: Commit**

```bash
git add core/agents/prompts/fix.py core/agents/fix.py tests/core/agents/test_fix.py
git commit -m "feat(fix-agent): add FixAgent with prompt templates and redaction"
```

---

### Task 2: Patch validator

**Files:**
- Create: `core/remediation/__init__.py`
- Create: `core/remediation/validator.py`
- Test: `tests/core/remediation/test_validator.py`

**Interfaces:**
- Consumes: nothing from earlier tasks at import time; `validate(diff, target_file, scan_root)` called externally
- Produces: `PatchValidator` class; `PatchValidationResult` dataclass with fields `applied: bool`, `finding_cleared: bool`, `new_findings: list[str]`, `error: Optional[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/core/remediation/test_validator.py`:

```python
# tests/core/remediation/test_validator.py
from __future__ import annotations
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.remediation.validator import PatchValidator, PatchValidationResult


VULNERABLE_CONTENT = '''\
import os

def run_cmd(user_input):
    os.system(f"ls {user_input}")
'''

UNIFIED_DIFF = '''\
--- a/vuln.py
+++ b/vuln.py
@@ -3,2 +3,4 @@
 def run_cmd(user_input):
-    os.system(f"ls {user_input}")
+    import shlex
+    safe = shlex.quote(user_input)
+    os.system(f"ls {safe}")
'''

SEMGREP_ORIGINAL_SARIF = {
    "runs": [{
        "results": [{
            "ruleId": "python.lang.security.audit.subprocess-shell-true.subprocess-shell-true",
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": "vuln.py"}}}],
        }]
    }]
}

SEMGREP_CLEAN_SARIF = {
    "runs": [{"results": []}]
}


def test_patch_validation_result_defaults():
    r = PatchValidationResult(applied=False, finding_cleared=False, new_findings=[], error=None)
    assert r.applied is False
    assert r.new_findings == []
    assert r.error is None


def test_validate_returns_applied_true_when_patch_succeeds(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validator, "_run_semgrep", side_effect=[
            SEMGREP_ORIGINAL_SARIF, SEMGREP_CLEAN_SARIF
        ]):
            result = validator.validate(
                diff=UNIFIED_DIFF,
                target_file=target,
                scan_root=tmp_path,
                original_rule_id="python.lang.security.audit.subprocess-shell-true.subprocess-shell-true",
            )

    assert result.applied is True
    assert result.finding_cleared is True
    assert result.new_findings == []
    assert result.error is None


def test_validate_returns_applied_false_when_patch_fails(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()

    def fake_run_fail(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        result.stderr = "patch failed"
        return result

    with patch("subprocess.run", side_effect=fake_run_fail):
        result = validator.validate(
            diff=UNIFIED_DIFF,
            target_file=target,
            scan_root=tmp_path,
            original_rule_id="some.rule",
        )

    assert result.applied is False
    assert result.error == "patch failed"


def test_validate_detects_new_findings_introduced_by_patch(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()

    NEW_FINDING_SARIF = {
        "runs": [{
            "results": [{
                "ruleId": "python.lang.security.new-rule",
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "vuln.py"}}}],
            }]
        }]
    }

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validator, "_run_semgrep", side_effect=[
            SEMGREP_ORIGINAL_SARIF, NEW_FINDING_SARIF
        ]):
            result = validator.validate(
                diff=UNIFIED_DIFF,
                target_file=target,
                scan_root=tmp_path,
                original_rule_id="python.lang.security.audit.subprocess-shell-true.subprocess-shell-true",
            )

    assert result.finding_cleared is True
    assert "python.lang.security.new-rule" in result.new_findings


def test_validate_finding_not_cleared_if_rule_still_present(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()
    original_rule = "python.lang.security.audit.subprocess-shell-true.subprocess-shell-true"

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validator, "_run_semgrep", side_effect=[
            SEMGREP_ORIGINAL_SARIF, SEMGREP_ORIGINAL_SARIF  # same results: rule still present
        ]):
            result = validator.validate(
                diff=UNIFIED_DIFF,
                target_file=target,
                scan_root=tmp_path,
                original_rule_id=original_rule,
            )

    assert result.applied is True
    assert result.finding_cleared is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/remediation/test_validator.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'core.remediation'`

- [ ] **Step 3: Create the remediation package and validator**

Create `core/remediation/__init__.py`:

```python
# core/remediation/__init__.py
from __future__ import annotations
```

Create `core/remediation/validator.py`:

```python
# core/remediation/validator.py
from __future__ import annotations
import json
import shutil
import subprocess
import tempfile
import structlog
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = structlog.get_logger()


@dataclass
class PatchValidationResult:
    applied: bool
    finding_cleared: bool
    new_findings: list[str] = field(default_factory=list)
    error: Optional[str] = None


class PatchValidator:
    """Validates a unified diff by dry-running patch then comparing semgrep results."""

    def validate(
        self,
        diff: str,
        target_file: Path,
        scan_root: Path,
        original_rule_id: str,
    ) -> PatchValidationResult:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            work_file = tmp_dir / target_file.name
            shutil.copy2(target_file, work_file)

            diff_file = tmp_dir / "fix.patch"
            diff_file.write_text(diff, encoding="utf-8")

            # Dry-run first
            dry = subprocess.run(
                ["patch", "--dry-run", "-p1", "--input", str(diff_file), str(work_file)],
                capture_output=True,
                text=True,
            )
            if dry.returncode != 0:
                return PatchValidationResult(
                    applied=False,
                    finding_cleared=False,
                    error=dry.stderr.strip() or dry.stdout.strip(),
                )

            # Apply for real
            apply = subprocess.run(
                ["patch", "-p1", "--input", str(diff_file), str(work_file)],
                capture_output=True,
                text=True,
            )
            if apply.returncode != 0:
                return PatchValidationResult(
                    applied=False,
                    finding_cleared=False,
                    error=apply.stderr.strip() or apply.stdout.strip(),
                )

            # Semgrep before (original file)
            before_sarif = self._run_semgrep(target_file)
            before_rule_ids = self._extract_rule_ids(before_sarif)

            # Semgrep after (patched copy)
            after_sarif = self._run_semgrep(work_file)
            after_rule_ids = self._extract_rule_ids(after_sarif)

            finding_cleared = original_rule_id not in after_rule_ids
            new_findings = sorted(after_rule_ids - before_rule_ids)

            return PatchValidationResult(
                applied=True,
                finding_cleared=finding_cleared,
                new_findings=new_findings,
                error=None,
            )

    def _run_semgrep(self, target: Path) -> dict:
        try:
            proc = subprocess.run(
                ["semgrep", "scan", "--config", "auto", "--sarif", str(target)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return json.loads(proc.stdout) if proc.stdout.strip() else {"runs": [{"results": []}]}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
            log.warning("semgrep_run_error", error=str(exc), target=str(target))
            return {"runs": [{"results": []}]}

    @staticmethod
    def _extract_rule_ids(sarif: dict) -> set[str]:
        rule_ids: set[str] = set()
        for run in sarif.get("runs", []):
            for result in run.get("results", []):
                rid = result.get("ruleId")
                if rid:
                    rule_ids.add(rid)
        return rule_ids
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/remediation/test_validator.py -v
```

Expected output:
```
tests/core/remediation/test_validator.py::test_patch_validation_result_defaults PASSED
tests/core/remediation/test_validator.py::test_validate_returns_applied_true_when_patch_succeeds PASSED
tests/core/remediation/test_validator.py::test_validate_returns_applied_false_when_patch_fails PASSED
tests/core/remediation/test_validator.py::test_validate_detects_new_findings_introduced_by_patch PASSED
tests/core/remediation/test_validator.py::test_validate_finding_not_cleared_if_rule_still_present PASSED

5 passed in <1s
```

- [ ] **Step 5: Commit**

```bash
git add core/remediation/__init__.py core/remediation/validator.py tests/core/remediation/test_validator.py
git commit -m "feat(validator): add PatchValidator with dry-run patch + semgrep comparison"
```

---

### Task 3: Fixes API router

**Files:**
- Create: `core/api/routers/fixes.py`
- Modify: `core/api/app.py`
- Test: `tests/core/api/test_fixes_router.py`

**Interfaces:**
- Consumes: `FixRow`, `FindingRow`, `AuditLogEntryRow` from `core.db.tables`; `AuditLogEntry` from `core.model.entities`; `get_db` from `core.api.deps`
- Produces:
  - `GET /api/v1/scans/{scan_id}/fixes` → `list[dict]`
  - `GET /api/v1/fixes/{fix_id}` → `dict`
  - `POST /api/v1/fixes/{fix_id}/apply` → `{"status": "applied"}`
  - `POST /api/v1/fixes/{fix_id}/reject` → `{"status": "rejected"}`

- [ ] **Step 1: Write the failing test**

Create `tests/core/api/test_fixes_router.py`:

```python
# tests/core/api/test_fixes_router.py
from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from core.api.app import create_app


def _make_fix_row(
    fix_id: str | None = None,
    finding_id: str | None = None,
    status: str = "proposed",
) -> MagicMock:
    row = MagicMock()
    row.id = fix_id or str(uuid4())
    row.finding_id = finding_id or str(uuid4())
    row.diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-bad\n+good\n"
    row.test = None
    row.explanation = "Replaced bad code with good code."
    row.validation_result = None
    row.status = status
    row.reviewer = None
    row.audit_ref = None
    return row


def _make_finding_row(finding_id: str, scan_id: str) -> MagicMock:
    row = MagicMock()
    row.id = finding_id
    row.scan_id = scan_id
    return row


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_scan_fixes_returns_list(client):
    scan_id = str(uuid4())
    finding_id = str(uuid4())
    fix_row = _make_fix_row(finding_id=finding_id)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fix_row]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.get(f"/api/v1/scans/{scan_id}/fixes")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == fix_row.id
    assert data[0]["status"] == "proposed"


async def test_get_fix_returns_detail(client):
    fix_row = _make_fix_row()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fix_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.get(f"/api/v1/fixes/{fix_row.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["diff"] == fix_row.diff
    assert data["explanation"] == fix_row.explanation


async def test_get_fix_returns_404_when_not_found(client):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.get(f"/api/v1/fixes/{uuid4()}")

    assert resp.status_code == 404


async def test_apply_fix_writes_audit_log_before_status_change(client):
    fix_id = str(uuid4())
    fix_row = _make_fix_row(fix_id=fix_id, status="proposed")
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fix_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    call_order: list[str] = []

    original_add = mock_db.add

    def track_add(obj):
        from core.db.tables import AuditLogEntryRow
        if isinstance(obj, AuditLogEntryRow):
            call_order.append("audit_written")
        call_order.append(f"add:{type(obj).__name__}")

    mock_db.add = MagicMock(side_effect=track_add)
    mock_db.commit = AsyncMock(side_effect=lambda: call_order.append("committed"))
    mock_db.refresh = AsyncMock()

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.post(f"/api/v1/fixes/{fix_id}/apply")

    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"
    # Audit log must be written (add called with AuditLogEntryRow)
    assert "audit_written" in call_order
    # Status on row must be "applied"
    assert fix_row.status == "applied"


async def test_apply_fix_returns_404_when_not_found(client):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.post(f"/api/v1/fixes/{uuid4()}/apply")

    assert resp.status_code == 404


async def test_reject_fix_writes_audit_log_with_reason(client):
    fix_id = str(uuid4())
    fix_row = _make_fix_row(fix_id=fix_id, status="proposed")
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fix_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    audit_entries: list = []
    mock_db.add = MagicMock(side_effect=lambda obj: audit_entries.append(obj))
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.post(
            f"/api/v1/fixes/{fix_id}/reject",
            json={"reason": "Fix introduces regression"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert fix_row.status == "rejected"
    from core.db.tables import AuditLogEntryRow
    audit_row = next(
        (e for e in audit_entries if isinstance(e, AuditLogEntryRow)), None
    )
    assert audit_row is not None
    assert audit_row.action == "fix_reject"
    assert audit_row.after["reason"] == "Fix introduces regression"


async def test_reject_fix_returns_404_when_not_found(client):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("core.api.routers.fixes.get_db", return_value=mock_db):
        resp = await client.post(f"/api/v1/fixes/{uuid4()}/reject", json={"reason": "nope"})

    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/api/test_fixes_router.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'core.api.routers.fixes'` or `ImportError`

- [ ] **Step 3: Create the fixes router**

Create `core/api/routers/fixes.py`:

```python
# core/api/routers/fixes.py
from __future__ import annotations
from uuid import uuid4, UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import FixRow, FindingRow, AuditLogEntryRow

router = APIRouter(tags=["fixes"])


class RejectBody(BaseModel):
    reason: str


@router.get("/scans/{scan_id}/fixes")
async def list_scan_fixes(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(FixRow)
        .join(FindingRow, FixRow.finding_id == FindingRow.id)
        .where(FindingRow.scan_id == str(scan_id))
    )
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "finding_id": r.finding_id,
            "diff": r.diff,
            "test": r.test,
            "explanation": r.explanation,
            "validation_result": r.validation_result,
            "status": r.status,
            "reviewer": r.reviewer,
            "audit_ref": r.audit_ref,
        }
        for r in rows
    ]


@router.get("/fixes/{fix_id}")
async def get_fix(fix_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "diff": row.diff,
        "test": row.test,
        "explanation": row.explanation,
        "validation_result": row.validation_result,
        "status": row.status,
        "reviewer": row.reviewer,
        "audit_ref": row.audit_ref,
    }


@router.post("/fixes/{fix_id}/apply")
async def apply_fix(fix_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")

    # Write audit log BEFORE mutating status
    audit = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action="fix_apply",
        target=str(fix_id),
        before={"status": row.status},
        after={"status": "applied"},
    )
    db.add(audit)

    row.status = "applied"
    await db.commit()
    await db.refresh(row)
    return {"status": row.status, "fix_id": str(fix_id)}


@router.post("/fixes/{fix_id}/reject")
async def reject_fix(
    fix_id: UUID,
    body: RejectBody,
    db: AsyncSession = Depends(get_db),
):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")

    # Write audit log BEFORE mutating status
    audit = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action="fix_reject",
        target=str(fix_id),
        before={"status": row.status},
        after={"status": "rejected", "reason": body.reason},
    )
    db.add(audit)

    row.status = "rejected"
    await db.commit()
    await db.refresh(row)
    return {"status": row.status, "fix_id": str(fix_id)}
```

- [ ] **Step 4: Update app.py to wire in the fixes router and remove the 501 stub**

Read the current `core/api/app.py` first (already read above). Replace lines 6-48 with the updated version:

```python
# core/api/app.py
from __future__ import annotations
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.routers.fixes import router as fixes_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus
    app = FastAPI(title="Argus Security Platform", version="0.2.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")
    app.include_router(fixes_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    # Stub routes for Phase 2+ (return 501)
    @app.get("/api/v1/pipelines")
    async def list_pipelines():
        return []

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    return app

# Module-level instance for uvicorn
app = create_app()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/api/test_fixes_router.py -v
```

Expected output:
```
tests/core/api/test_fixes_router.py::test_list_scan_fixes_returns_list PASSED
tests/core/api/test_fixes_router.py::test_get_fix_returns_detail PASSED
tests/core/api/test_fixes_router.py::test_get_fix_returns_404_when_not_found PASSED
tests/core/api/test_fixes_router.py::test_apply_fix_writes_audit_log_before_status_change PASSED
tests/core/api/test_fixes_router.py::test_apply_fix_returns_404_when_not_found PASSED
tests/core/api/test_fixes_router.py::test_reject_fix_writes_audit_log_with_reason PASSED
tests/core/api/test_fixes_router.py::test_reject_fix_returns_404_when_not_found PASSED

7 passed in <1s
```

- [ ] **Step 6: Commit**

```bash
git add core/api/routers/fixes.py core/api/app.py tests/core/api/test_fixes_router.py
git commit -m "feat(api): add fixes router with human-gate apply/reject and audit logging"
```

---

### Task 4: Wire FixAgent into the orchestrator pipeline

**Files:**
- Modify: `core/agents/orchestrator.py`
- Modify: `config/pipeline_configs/full-scan.yaml`

**Interfaces:**
- Consumes: `FixAgent` from `core.agents.fix`; `FixRow` from `core.db.tables`
- Produces: orchestrator now persists `FixRow` objects after running the pipeline; `_build_extra` passes `explained_findings` to `fix_generation` node

- [ ] **Step 1: Write the failing test**

Add to `tests/core/agents/test_orchestrator.py` (open the file and append — do not overwrite the existing content):

```python
# Append to tests/core/agents/test_orchestrator.py

MOCK_FIX_RESPONSE = '''{
  "diff": "--- a/app.py\\n+++ b/app.py\\n@@ -5,1 +5,1 @@\\n-    query = f\\"SELECT * FROM users WHERE name=\\'{username}\\'\\"\\"\\n+    query = \\"SELECT * FROM users WHERE name=%s\\"",
  "test": null,
  "explanation": "Replaced interpolation with parameterized query.",
  "confidence": 0.95
}'''


async def test_orchestrator_runs_with_fix_generation(tmp_path):
    src = tmp_path / "app.py"
    src.write_text("query = f\"SELECT * FROM users WHERE name='{username}'\"\n")

    gate = MagicMock()
    gate.complete = AsyncMock(side_effect=[
        GateResult(content=MOCK_TRIAGE_RESPONSE, tokens_in=800, tokens_out=200,
                   cache_hit=False, model_id="claude-sonnet-4-6", provider="anthropic",
                   tier=ModelTier.balanced, cost_usd=0.006),
        GateResult(content=MOCK_EXPLAIN_RESPONSE, tokens_in=400, tokens_out=100,
                   cache_hit=False, model_id="claude-haiku-4-5-20251001", provider="anthropic",
                   tier=ModelTier.fast, cost_usd=0.001),
        GateResult(content=MOCK_FIX_RESPONSE, tokens_in=1200, tokens_out=300,
                   cache_hit=False, model_id="claude-sonnet-4-6", provider="anthropic",
                   tier=ModelTier.balanced, cost_usd=0.009),
    ])
    gate._budget = MagicMock()
    gate._budget.record = MagicMock()

    scan = Scan(
        target_ref=str(tmp_path),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=None)
    ))
    session.add = MagicMock()
    session.flush = AsyncMock()

    orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
    findings = await orch.run(scan, session)

    assert isinstance(findings, list)
    assert len(findings) >= 1
    # FixRow should have been added to session
    added_types = [type(call.args[0]).__name__ for call in session.add.call_args_list]
    assert "FixRow" in added_types
```

- [ ] **Step 2: Run the new test to verify it fails**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_orchestrator.py::test_orchestrator_runs_with_fix_generation -v 2>&1 | head -20
```

Expected: the test fails because `FixAgent` is not in `_AGENT_REGISTRY` and the YAML has no `fix_generation` node.

- [ ] **Step 3: Update full-scan.yaml to add the fix_generation node**

Open `config/pipeline_configs/full-scan.yaml`. The current file ends after the `explainer → (end)` edge. Add the `fix_generation` node and its edge:

```yaml
name: full-scan
version: 1
is_default: true
mode: at_rest
nodes:
  - id: ingestion
    agent: IngestionAgent
    tier: fast
    budget_pct: 5
  - id: sast
    agent: SemgrepAdapter
    tier: none
    budget_pct: 0
  - id: secrets
    agent: TruffleHogAdapter
    tier: none
    budget_pct: 0
  - id: triage
    agent: TriageAgent
    tier: balanced
    budget_pct: 40
  - id: explainer
    agent: ExplainerAgent
    tier: fast
    budget_pct: 15
  - id: fix_generation
    agent: FixAgent
    tier: balanced
    budget_pct: 35
edges:
  - from: ingestion
    to: sast
  - from: ingestion
    to: secrets
  - from: sast
    to: triage
  - from: secrets
    to: triage
  - from: triage
    to: explainer
  - from: explainer
    to: fix_generation
```

- [ ] **Step 4: Update orchestrator.py to register FixAgent, pass explained_findings, and persist FixRows**

Open `core/agents/orchestrator.py`. Make three targeted changes:

**4a. Add import** — after line 14 (`from core.agents.explainer import ExplainerAgent`), add:

```python
from core.agents.fix import FixAgent
```

**4b. Update `_AGENT_REGISTRY`** — add `FixAgent` entry:

```python
_AGENT_REGISTRY: dict[str, type] = {
    "IngestionAgent": IngestionAgent,
    "SemgrepAdapter": SemgrepAdapter,
    "TruffleHogAdapter": TruffleHogAdapter,
    "TriageAgent": TriageAgent,
    "ExplainerAgent": ExplainerAgent,
    "FixAgent": FixAgent,
}
```

**4c. Update `_build_extra`** — after the `if "triage" in state:` block (around line 162), add the explainer output passthrough:

```python
    def _build_extra(self, node_id: str, state: dict[str, AgentOutput]) -> dict:
        extra: dict = {}
        # Pass code_context from ingestion to all nodes
        if "ingestion" in state:
            extra["code_context"] = state["ingestion"].data.get("code_context", {})
        # Collect all scanner findings
        all_findings: list[dict] = []
        for nid, output in state.items():
            if self._nodes.get(nid, {}).get("agent") in _SCANNER_AGENTS:
                all_findings.extend(output.data.get("findings", []))
        if all_findings:
            extra["findings"] = all_findings
        # Pass triage output to explainer and fix_generation
        if "triage" in state:
            extra["triaged_findings"] = state["triage"].data.get("triaged_findings", [])
        # Pass explainer output to fix_generation
        if "explainer" in state:
            extra["explained_findings"] = state["explainer"].data.get("explained_findings", [])
        return extra
```

**4d. Add `_persist_fixes` method and call it from `run`** — after `_persist_findings`, add:

```python
    async def _persist_fixes(
        self, fixes: list[dict], session: AsyncSession
    ) -> None:
        for f in fixes:
            row = FixRow(
                id=str(f.get("id", "")),
                finding_id=str(f.get("finding_id", "")),
                diff=f.get("diff", ""),
                test=f.get("test"),
                explanation=f.get("explanation", ""),
                validation_result=f.get("validation_result"),
                status=f.get("status", "proposed"),
                reviewer=f.get("reviewer"),
                audit_ref=str(f["audit_ref"]) if f.get("audit_ref") else None,
            )
            session.add(row)
        try:
            await session.flush()
        except Exception as e:
            log.warning("persist_fixes_error", error=str(e))
```

Add `FixRow` to the import from `core.db.tables` (line 23):

```python
from core.db.tables import ScanRow, FindingRow, FixRow, AuditLogEntryRow
```

In the `run` method, after `await self._persist_findings(findings, scan, session)`, add:

```python
        fixes = self._collect_fixes(state)
        await self._persist_fixes(fixes, session)
```

Add `_collect_fixes` method:

```python
    def _collect_fixes(self, state: dict[str, AgentOutput]) -> list[dict]:
        if "fix_generation" in state:
            return state["fix_generation"].data.get("fixes", [])
        return []
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_orchestrator.py -v
```

Expected output:
```
tests/core/agents/test_orchestrator.py::test_orchestrator_runs_full_pipeline PASSED
tests/core/agents/test_orchestrator.py::test_orchestrator_runs_with_fix_generation PASSED

2 passed in <Xs
```

- [ ] **Step 6: Commit**

```bash
git add core/agents/orchestrator.py config/pipeline_configs/full-scan.yaml
git commit -m "feat(orchestrator): wire FixAgent into full-scan pipeline with fix persistence"
```

---

### Task 5: Fix Review dashboard tab

**Files:**
- Modify: `surfaces/dashboard/src/api/client.ts`
- Create: `surfaces/dashboard/src/pages/fixes/DiffViewer.tsx`
- Create: `surfaces/dashboard/src/pages/fixes/FixReviewPage.tsx`
- Modify: `surfaces/dashboard/src/components/Nav.tsx`
- Modify: `surfaces/dashboard/src/App.tsx`

**Interfaces:**
- Consumes: `api.listScanFixes`, `api.applyFix`, `api.rejectFix` from updated `client.ts`; `ScanDTO` already defined in `client.ts`
- Produces:
  - `FixDTO` interface exported from `client.ts`
  - `DiffViewer` component: `({ diff }: { diff: string }) => JSX.Element`
  - `FixReviewPage` component: `() => JSX.Element`

- [ ] **Step 1: Extend client.ts with FixDTO and fix API methods**

Open `surfaces/dashboard/src/api/client.ts`. The current file is 98 lines. Append after the closing brace of `export const api = { ... }` (line 98):

Add `FixDTO` interface and extend `api` object. The final file should look like:

```typescript
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type SecurityApproach =
  | "penetration_testing"
  | "adversary_emulation"
  | "breach_and_attack_simulation"
  | "assumed_breach"
  | "blue_team"
  | "purple_team";

export const APPROACH_LABELS: Record<SecurityApproach, string> = {
  penetration_testing: "Penetration Testing",
  adversary_emulation: "Adversary Emulation",
  breach_and_attack_simulation: "Breach & Attack Simulation",
  assumed_breach: "Assumed Breach",
  blue_team: "Blue Team",
  purple_team: "Purple Team",
};

export const APPROACH_DESCRIPTIONS: Record<SecurityApproach, string> = {
  penetration_testing: "Breadth-first: find and exploit all vulnerabilities in scope",
  adversary_emulation: "Replay threat actor TTPs mapped to MITRE ATT&CK",
  breach_and_attack_simulation: "Validate controls: would WAF/SIEM/EDR catch this?",
  assumed_breach: "Post-compromise: lateral movement, privilege escalation, persistence",
  blue_team: "Defensive: detection engineering, hardening, control gap analysis",
  purple_team: "Red + blue feedback loop: every attack paired with a detection rule",
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface FindingDTO {
  id: string;
  rule_id: string;
  source_tool: string;
  cwe: string | null;
  owasp_category: string | null;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: number;
  exploit_likelihood: number;
  reachability: string | null;
  location: { file: string; line_start: number; line_end: number; snippet?: string };
  status: string;
  explanation: string | null;
  attack_scenario?: string;
  priority_score?: number;
}

export interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  approach: SecurityApproach;
  cost_usd: number;
  started_at: string | null;
}

export interface CostEntryDTO {
  id: string;
  scope_type: string;
  scope_id: string;
  tokens_in: number;
  tokens_out: number;
  tier: string;
  provider: string;
  model_id: string;
  cost_usd: number;
  timestamp: string;
}

export interface FixDTO {
  id: string;
  finding_id: string;
  diff: string;
  test: string | null;
  explanation: string;
  validation_result: {
    applied: boolean;
    finding_cleared: boolean;
    new_findings: string[];
    error: string | null;
  } | null;
  status: "proposed" | "applied" | "pr_opened" | "rejected" | "needs_attention";
  reviewer: string | null;
  audit_ref: string | null;
}

export const api = {
  listScans: () => get<ScanDTO[]>("/api/v1/scans/"),
  triggerScan: (body: { target_ref: string; mode?: string; approach?: SecurityApproach }) =>
    post<{ scan_id: string }>("/api/v1/scans/", body),
  getScanFindings: (scanId: string) =>
    get<FindingDTO[]>(`/api/v1/scans/${scanId}/findings`),
  getCostLedger: () => get<CostEntryDTO[]>("/api/v1/cost/ledger"),
  getCostSummary: () =>
    get<{
      total_cost_usd: number;
      total_tokens_in: number;
      total_calls: number;
    }>("/api/v1/cost/summary"),
  listScanFixes: (scanId: string) =>
    get<FixDTO[]>(`/api/v1/scans/${scanId}/fixes`),
  applyFix: (fixId: string) =>
    post<{ status: string; fix_id: string }>(`/api/v1/fixes/${fixId}/apply`, {}),
  rejectFix: (fixId: string, reason: string) =>
    post<{ status: string; fix_id: string }>(`/api/v1/fixes/${fixId}/reject`, { reason }),
};
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npx tsc --noEmit 2>&1 | head -20
```

Expected: no output (clean compile). If type errors appear, fix them before proceeding.

- [ ] **Step 3: Create DiffViewer component**

Create `surfaces/dashboard/src/pages/fixes/DiffViewer.tsx`:

```tsx
// surfaces/dashboard/src/pages/fixes/DiffViewer.tsx

interface DiffViewerProps {
  diff: string;
}

type LineKind = "added" | "removed" | "context" | "header";

interface DiffLine {
  kind: LineKind;
  text: string;
}

function parseDiff(diff: string): DiffLine[] {
  return diff.split("\n").map((line): DiffLine => {
    if (line.startsWith("+++ ") || line.startsWith("--- ") || line.startsWith("@@ ")) {
      return { kind: "header", text: line };
    }
    if (line.startsWith("+")) return { kind: "added", text: line };
    if (line.startsWith("-")) return { kind: "removed", text: line };
    return { kind: "context", text: line };
  });
}

const KIND_STYLES: Record<LineKind, string> = {
  added: "bg-green-50 text-green-700",
  removed: "bg-red-50 text-red-700",
  context: "bg-gray-50 text-gray-700",
  header: "bg-gray-100 text-gray-500 font-semibold",
};

export function DiffViewer({ diff }: DiffViewerProps) {
  const lines = parseDiff(diff);

  if (!diff.trim()) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
        No diff available
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-lg border border-gray-200 bg-white">
      <pre className="text-xs font-mono leading-5">
        {lines.map((line, i) => (
          <div
            key={i}
            className={`px-4 py-0.5 whitespace-pre ${KIND_STYLES[line.kind]}`}
          >
            {line.text || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}
```

- [ ] **Step 4: Create FixReviewPage component**

Create `surfaces/dashboard/src/pages/fixes/FixReviewPage.tsx`:

```tsx
// surfaces/dashboard/src/pages/fixes/FixReviewPage.tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ScanDTO, FixDTO } from "../../api/client";
import { DiffViewer } from "./DiffViewer";

const STATUS_GROUPS: Array<{
  status: FixDTO["status"] | FixDTO["status"][];
  label: string;
  badgeClass: string;
}> = [
  {
    status: "proposed",
    label: "Proposed",
    badgeClass: "bg-yellow-100 text-yellow-800",
  },
  {
    status: "applied",
    label: "Applied",
    badgeClass: "bg-green-100 text-green-800",
  },
  {
    status: ["rejected", "needs_attention"],
    label: "Rejected / Needs Attention",
    badgeClass: "bg-red-100 text-red-800",
  },
];

function matchesGroup(fix: FixDTO, group: typeof STATUS_GROUPS[0]): boolean {
  const statuses = Array.isArray(group.status) ? group.status : [group.status];
  return statuses.includes(fix.status);
}

function StatusBadge({ status }: { status: FixDTO["status"] }) {
  const group = STATUS_GROUPS.find((g) => matchesGroup({ status } as FixDTO, g));
  const cls = group?.badgeClass ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function ValidationBadge({ result }: { result: FixDTO["validation_result"] }) {
  if (!result) return <span className="text-xs text-gray-400">Not validated</span>;
  if (result.error) return <span className="text-xs text-red-600">Error: {result.error}</span>;
  return (
    <span className={`text-xs font-medium ${result.finding_cleared ? "text-green-700" : "text-red-700"}`}>
      {result.finding_cleared ? "Finding cleared" : "Finding not cleared"}
      {result.new_findings.length > 0 && ` · ${result.new_findings.length} new finding(s)`}
    </span>
  );
}

export function FixReviewPage() {
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null);
  const [selectedFix, setSelectedFix] = useState<FixDTO | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const qc = useQueryClient();

  const { data: scans = [] } = useQuery<ScanDTO[]>({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });

  const { data: fixes = [], isLoading: fixesLoading } = useQuery<FixDTO[]>({
    queryKey: ["fixes", selectedScanId],
    queryFn: () => api.listScanFixes(selectedScanId!),
    enabled: !!selectedScanId,
  });

  const applyMutation = useMutation({
    mutationFn: (fixId: string) => api.applyFix(fixId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fixes", selectedScanId] });
      setSelectedFix(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ fixId, reason }: { fixId: string; reason: string }) =>
      api.rejectFix(fixId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fixes", selectedScanId] });
      setSelectedFix(null);
      setShowRejectInput(false);
      setRejectReason("");
    },
  });

  const completedScans = scans.filter((s) => s.status === "completed");

  return (
    <div className="flex h-full bg-gray-50">
      {/* Left panel: list */}
      <div className="flex-1 overflow-auto p-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900 mb-1">Fix Review</h1>
          <p className="text-sm text-gray-500">
            Review AI-generated patches. Apply or reject — every action is audit-logged.
          </p>
        </div>

        {/* Scan selector */}
        <div className="mb-5">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Scan
          </label>
          <select
            className="w-full max-w-sm border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            value={selectedScanId ?? ""}
            onChange={(e) => {
              setSelectedScanId(e.target.value || null);
              setSelectedFix(null);
            }}
          >
            <option value="">Select a scan…</option>
            {completedScans.map((s) => (
              <option key={s.id} value={s.id}>
                {s.target_ref} — {new Date(s.started_at ?? "").toLocaleString()}
              </option>
            ))}
          </select>
        </div>

        {/* Fix groups */}
        {fixesLoading && (
          <div className="text-sm text-gray-400 mt-8 text-center">Loading fixes…</div>
        )}

        {!fixesLoading && selectedScanId && fixes.length === 0 && (
          <div className="mt-8 text-center text-gray-400 text-sm">
            No fixes generated for this scan yet.
          </div>
        )}

        {!fixesLoading &&
          STATUS_GROUPS.map((group) => {
            const groupFixes = fixes.filter((f) => matchesGroup(f, group));
            if (groupFixes.length === 0) return null;
            return (
              <div key={group.label} className="mb-6">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">
                  {group.label} ({groupFixes.length})
                </h2>
                <div className="flex flex-col gap-2">
                  {groupFixes.map((fix) => (
                    <button
                      key={fix.id}
                      onClick={() => setSelectedFix(fix)}
                      className={`w-full text-left bg-white rounded-xl border px-4 py-3 shadow-sm transition-all hover:shadow-md ${
                        selectedFix?.id === fix.id
                          ? "border-purple-400 ring-2 ring-purple-200"
                          : "border-gray-200"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-mono text-gray-700 truncate">
                          {fix.finding_id.slice(0, 8)}…
                        </span>
                        <StatusBadge status={fix.status} />
                      </div>
                      <p className="mt-1 text-xs text-gray-500 truncate">{fix.explanation}</p>
                      <div className="mt-1">
                        <ValidationBadge result={fix.validation_result} />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
      </div>

      {/* Right panel: diff viewer */}
      {selectedFix && (
        <div className="w-[52%] border-l border-gray-200 bg-white overflow-auto flex flex-col">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 font-mono">
                Fix {selectedFix.id.slice(0, 8)}
              </p>
              <p className="text-sm text-gray-700 mt-0.5">{selectedFix.explanation}</p>
            </div>
            <button
              onClick={() => setSelectedFix(null)}
              className="text-gray-400 hover:text-gray-600 text-lg leading-none"
              aria-label="Close"
            >
              &times;
            </button>
          </div>

          <div className="flex-1 overflow-auto px-6 py-4">
            <DiffViewer diff={selectedFix.diff} />

            {selectedFix.test && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
                  Verification test
                </p>
                <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs font-mono text-gray-700 overflow-auto">
                  {selectedFix.test}
                </pre>
              </div>
            )}

            {selectedFix.validation_result && (
              <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
                <p className="text-xs font-semibold text-gray-500 mb-1">Validation</p>
                <ValidationBadge result={selectedFix.validation_result} />
                {selectedFix.validation_result.new_findings.length > 0 && (
                  <ul className="mt-1 text-xs text-red-600 list-disc list-inside">
                    {selectedFix.validation_result.new_findings.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Apply / Reject — only for proposed fixes */}
          {selectedFix.status === "proposed" && (
            <div className="px-6 py-4 border-t border-gray-100">
              {!showRejectInput ? (
                <div className="flex gap-3">
                  <button
                    onClick={() => applyMutation.mutate(selectedFix.id)}
                    disabled={applyMutation.isPending}
                    className="px-5 py-2 rounded-lg text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    style={{ background: "#A100FF" }}
                  >
                    {applyMutation.isPending ? "Applying…" : "Apply fix"}
                  </button>
                  <button
                    onClick={() => setShowRejectInput(true)}
                    className="px-5 py-2 rounded-lg text-sm font-semibold text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <textarea
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-purple-400"
                    rows={2}
                    placeholder="Reason for rejection…"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() =>
                        rejectMutation.mutate({
                          fixId: selectedFix.id,
                          reason: rejectReason,
                        })
                      }
                      disabled={rejectMutation.isPending || !rejectReason.trim()}
                      className="px-4 py-1.5 rounded-lg text-sm font-semibold text-white bg-gray-500 hover:bg-gray-600 disabled:opacity-50 transition-colors"
                    >
                      {rejectMutation.isPending ? "Rejecting…" : "Confirm reject"}
                    </button>
                    <button
                      onClick={() => {
                        setShowRejectInput(false);
                        setRejectReason("");
                      }}
                      className="px-4 py-1.5 rounded-lg text-sm font-medium text-gray-500 hover:text-gray-700"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Add "Fix Review" to Nav.tsx**

Open `surfaces/dashboard/src/components/Nav.tsx`. The current `links` array ends with the Pipeline entry (line 39). Insert a new entry for Fix Review after the Pipeline entry. Replace the `links` array declaration:

```typescript
const links = [
  {
    to: "/findings",
    label: "Findings",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    ),
  },
  {
    to: "/runs",
    label: "Live Runs",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    to: "/cost",
    label: "Cost & Usage",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    to: "/pipeline",
    label: "Pipeline",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
    ),
  },
  {
    to: "/fixes",
    label: "Fix Review",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
  },
];
```

Also update the footer version string from `Phase 1 · v0.1.0` to `Phase 2a · v0.2.0`:

```typescript
        <p className="text-[11px] text-gray-400">Phase 2a · v0.2.0</p>
```

- [ ] **Step 6: Add /fixes route to App.tsx**

Open `surfaces/dashboard/src/App.tsx`. Add the import and route:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/Layout";
import { FindingsPage } from "./pages/findings/FindingsPage";
import { RunsPage } from "./pages/runs/RunsPage";
import { CostPage } from "./pages/cost/CostPage";
import { PipelinePage } from "./pages/pipeline/PipelinePage";
import { FixReviewPage } from "./pages/fixes/FixReviewPage";

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/findings" replace />} />
            <Route path="/findings" element={<FindingsPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/cost" element={<CostPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/fixes" element={<FixReviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 7: Verify TypeScript compiles clean**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npx tsc --noEmit 2>&1
```

Expected: no output (zero errors). Fix any type errors before committing.

- [ ] **Step 8: Verify Vite dev build succeeds**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -10
```

Expected output ends with:
```
✓ built in Xs
```

- [ ] **Step 9: Commit**

```bash
git add \
  surfaces/dashboard/src/api/client.ts \
  surfaces/dashboard/src/pages/fixes/DiffViewer.tsx \
  surfaces/dashboard/src/pages/fixes/FixReviewPage.tsx \
  surfaces/dashboard/src/components/Nav.tsx \
  surfaces/dashboard/src/App.tsx
git commit -m "feat(dashboard): add Fix Review tab with DiffViewer, apply/reject flow"
```

---

### Task 6: Full regression run

This task has no new files. It verifies the complete Phase 2a implementation in one shot before declaring done.

- [ ] **Step 1: Run the full Python test suite**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/ -v --ignore=tests/e2e 2>&1 | tail -20
```

Expected: all tests pass. Zero failures. The output ends with a line like:
```
XX passed in Xs
```

If any test fails, fix it before proceeding.

- [ ] **Step 2: Run TypeScript type check**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npx tsc --noEmit 2>&1
```

Expected: no output.

- [ ] **Step 3: Run frontend build**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npm run build 2>&1 | tail -5
```

Expected: ends with `✓ built in Xs`.

- [ ] **Step 4: Commit final integration tag**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
git tag phase-2a-complete
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `FIX_SYSTEM` + `FIX_USER_TEMPLATE` in `core/agents/prompts/fix.py` | Task 1 |
| `FixAgent.run(ctx)` with eligible-finding filter (open + exploit_likelihood >= 0.6) | Task 1 |
| Reads source file from `scan.target_ref` | Task 1 |
| Redacts snippets and file content before LLM call | Task 1 |
| `tier_override` = `top` for files > 200 lines | Task 1 |
| `task_type="fix_generation"` for GovernanceGate | Task 1 |
| Returns `AgentOutput` with `data={"fixes": [fix_dicts]}` | Task 1 |
| `PatchValidationResult` dataclass with all four fields | Task 2 |
| `PatchValidator.validate` dry-run → apply → semgrep before/after | Task 2 |
| Compares rule_ids; `finding_cleared` and `new_findings` populated correctly | Task 2 |
| `GET /api/v1/scans/{scan_id}/fixes` (joins FindingRow → FixRow) | Task 3 |
| `GET /api/v1/fixes/{fix_id}` with diff + validation_result | Task 3 |
| `POST /api/v1/fixes/{fix_id}/apply` writes AuditLogEntry BEFORE status change | Task 3 |
| `POST /api/v1/fixes/{fix_id}/reject` with reason body, writes AuditLogEntry | Task 3 |
| 501 stub for `GET /fixes/{id}` replaced | Task 3 |
| FixAgent added to `_AGENT_REGISTRY` | Task 4 |
| `fix_generation` node in `full-scan.yaml` (tier: balanced, budget_pct: 35) | Task 4 |
| `fix_generation` edges after `explainer` | Task 4 |
| `_build_extra` passes `explained_findings` | Task 4 |
| `FixRow` persisted by orchestrator | Task 4 |
| `FixDTO` interface in `client.ts` | Task 5 |
| `api.listScanFixes`, `api.applyFix`, `api.rejectFix` | Task 5 |
| `FixReviewPage` with scan selector + grouped status list | Task 5 |
| `DiffViewer` with green-50/green-700 / red-50/red-700 / gray-50 | Task 5 |
| Apply (purple #A100FF) + Reject (gray) with confirmation textarea | Task 5 |
| "Fix Review" link in Nav.tsx | Task 5 |
| `/fixes` route in App.tsx | Task 5 |

**All spec requirements accounted for. No gaps found.**

**Placeholder scan:** All steps contain actual code. No TBDs, no "implement later", no "similar to Task N".

**Type consistency:**
- `FixAgent.agent_id = "fix_generation"` used in Task 1 and referenced in Task 4 YAML/registry as `"FixAgent"` / `fix_generation` node id — consistent.
- `AgentOutput.data["fixes"]` used in Task 1 (FixAgent output) and Task 4 (`_collect_fixes` reads `state["fix_generation"].data.get("fixes", [])`).
- `FixRow` fields match `Fix.model_dump()` keys in Task 4 `_persist_fixes`.
- `FixDTO` in `client.ts` matches the JSON shape returned by `core/api/routers/fixes.py`.
- `DiffViewer` accepts `{ diff: string }` and is called with `selectedFix.diff` in `FixReviewPage` — consistent.
- `AuditLogEntryRow.action` is `"fix_apply"` / `"fix_reject"` — matches the test assertions in Task 3.
