# Argus Phase 1 — Agents & API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triage agent (adversarial mindset), Explainer agent, Orchestrator + pipeline runner, and the full FastAPI app with SSE endpoint.

**Architecture:** Agents operate with an adversarial framing — they reason about each finding through the lens of "how would an attacker exploit this?" The Triage agent scores exploit feasibility, chains findings into attack paths, and dismisses findings an attacker could not reach or exploit. The Explainer produces attack scenario narratives, not just CVE descriptions. The Orchestrator is data-driven from `PipelineConfig`. The FastAPI app exposes the full OpenAPI schema with SSE for live scan traces.

**Tech Stack:** Python 3.12, FastAPI, sse-starlette, Pydantic v2, GovernanceGate (finRouter sidecar).

## Global Constraints

- All constraints from foundation and scanning plans apply
- Triage and Explainer prompts must frame every analysis from an **attacker's perspective**: what can an attacker do with this, not just what rule was triggered
- Prompts must never include raw secret values — pass `[REDACTED]` with fingerprint only
- GovernanceGate is the only path to LLM calls — never call httpx/finRouter directly from agents

---

### Task 13: Triage agent

**Files:**
- Create: `core/agents/triage.py`
- Create: `core/agents/prompts/triage.py`
- Create: `tests/core/agents/test_triage.py`

**Interfaces:**
- Consumes: `AgentContext` with `ctx.extra["findings"]` (list of Finding dicts) and `ctx.extra["code_context"]`
- Produces: `AgentOutput` where `data["triaged_findings"]` is `list[dict]` — each Finding dict enriched with `confidence`, `exploit_likelihood`, `reachability`, `attack_scenario`, `priority_score`, and `status` (`open` or `dismissed`)

- [ ] **Step 1: Write failing test**

```python
# tests/core/agents/test_triage.py
from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from core.agents.triage import TriageAgent
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode, Finding, Severity, Location
from core.governance.gate import GateResult, GovernanceGate
from core.model.entities import ModelTier


def _make_finding(scan_id, severity=Severity.high, rule_id="python.injection.sql"):
    return Finding(
        scan_id=scan_id,
        rule_id=rule_id,
        source_tool="semgrep",
        severity=severity,
        cwe="CWE-89",
        owasp_category="A03:2021",
        location=Location(file="app.py", line_start=5, line_end=6,
                          snippet="query = f\"SELECT * FROM users WHERE username = '{username}'\""),
        dedup_key=f"semgrep:{rule_id}:app.py:5",
    )


@pytest.fixture
def mock_gate():
    gate = MagicMock(spec=GovernanceGate)
    gate.complete = AsyncMock(return_value=GateResult(
        content='''{
            "findings": [{
                "dedup_key": "semgrep:python.injection.sql:app.py:5",
                "confidence": 0.92,
                "exploit_likelihood": 0.85,
                "reachability": "reachable — username flows from HTTP request parameter",
                "attack_scenario": "An attacker sends a crafted username like \\' OR 1=1 -- to dump the users table or bypass authentication.",
                "priority_score": 9.2,
                "status": "open",
                "false_positive_reason": null
            }]
        }''',
        tokens_in=800, tokens_out=200, cache_hit=False,
        model_id="claude-sonnet-4-6", provider="anthropic",
        tier=ModelTier.balanced, cost_usd=0.006,
    ))
    return gate


@pytest.fixture
def ctx(mock_gate):
    scan_id = uuid4()
    scan = Scan(target_ref="tests/fixtures/vulnerable_python",
                pipeline_config_id=uuid4(), mode=ScanMode.at_rest, id=scan_id)
    finding = _make_finding(scan_id)
    from core.understanding.context import CodeContext
    cc = CodeContext(root="tests/fixtures/vulnerable_python", languages={"python": 1},
                     frameworks=[], file_count=1, repo_map="app.py", entry_points=["app.py"])
    return AgentContext(
        scan=scan, skills=[], budget_slice_usd=2.0, gate=mock_gate,
        extra={"findings": [finding.model_dump(mode="json")], "code_context": cc.model_dump()},
    )


async def test_triage_enriches_findings(ctx):
    agent = TriageAgent()
    result = await agent.run(ctx)
    triaged = result.data["triaged_findings"]
    assert len(triaged) == 1
    f = triaged[0]
    assert f["confidence"] == pytest.approx(0.92)
    assert f["exploit_likelihood"] == pytest.approx(0.85)
    assert "attacker" in f["attack_scenario"].lower() or "1=1" in f["attack_scenario"]
    assert f["priority_score"] >= 9.0
    assert f["status"] == "open"


async def test_triage_deduplicates(ctx):
    # duplicate finding should only appear once
    findings = ctx.extra["findings"] * 2  # same dedup_key twice
    ctx.extra["findings"] = findings
    agent = TriageAgent()
    result = await agent.run(ctx)
    keys = [f["dedup_key"] for f in result.data["triaged_findings"]]
    assert len(keys) == len(set(keys))
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/agents/test_triage.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement core/agents/prompts/triage.py**

```python
# core/agents/prompts/triage.py
from __future__ import annotations

TRIAGE_SYSTEM = """\
You are an adversarial security analyst. Your job is to evaluate each finding
through the eyes of a skilled attacker: assume the attacker has read access to
the source code, knows the framework, and will chain vulnerabilities to maximize
impact. You think like a penetration tester, not a compliance auditor.

For each finding you must answer these questions honestly:
1. Could an attacker actually reach and trigger this? (reachability)
2. What is the minimal attack that exploits it — exact payload, HTTP method, required auth level?
3. What is the realistic blast radius — data exfiltration, auth bypass, RCE, pivot point?
4. Does any other finding in this batch, combined with this one, enable a more severe attack chain?
5. Is this a genuine vulnerability or a false positive? If false positive, why?

Dismiss findings ONLY when you can articulate exactly why an attacker cannot exploit them
(e.g., the input is server-controlled, the sink is never reached, the framework mitigates it).
Do not dismiss because the severity looks low — low-severity findings that chain with others
stay open.

Return ONLY a JSON object with the structure shown. Do not add commentary outside the JSON.
"""

TRIAGE_USER_TEMPLATE = """\
Codebase context:
- Root: {root}
- Languages: {languages}
- Frameworks: {frameworks}
- Entry points: {entry_points}
- Repo map (first 100 files):
{repo_map}

Findings to triage ({count} total, deduplicated):
{findings_json}

Return a JSON object:
{{
  "findings": [
    {{
      "dedup_key": "<exact dedup_key from input>",
      "confidence": <0.0-1.0, how certain you are this is a real vuln>,
      "exploit_likelihood": <0.0-1.0, how likely an attacker can exploit this>,
      "reachability": "<one sentence: is this reachable from an attacker entry point and how>",
      "attack_scenario": "<2-3 sentences: exact attack an adversary would perform, including payload>",
      "priority_score": <0.0-10.0, blend of severity + exploit_likelihood + reachability>,
      "status": "open" | "dismissed",
      "false_positive_reason": "<reason if dismissed, null otherwise>",
      "attack_chain": "<if this chains with another finding's dedup_key, name it; else null>"
    }}
  ]
}}
"""
```

- [ ] **Step 4: Implement core/agents/triage.py**

```python
# core/agents/triage.py
from __future__ import annotations
import json
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.triage import TRIAGE_SYSTEM, TRIAGE_USER_TEMPLATE
from core.model.entities import Finding
from core.model.redaction import redact

log = structlog.get_logger()


class TriageAgent:
    agent_id = "triage"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        raw_findings: list[dict] = ctx.extra.get("findings", [])
        if not raw_findings:
            return AgentOutput(agent_id=self.agent_id, data={"triaged_findings": []})

        # Deduplicate by dedup_key before sending to LLM
        seen: set[str] = set()
        unique: list[dict] = []
        for f in raw_findings:
            key = f.get("dedup_key", "")
            if key not in seen:
                seen.add(key)
                unique.append(f)

        cc = ctx.extra.get("code_context", {})

        # Redact snippets before including in prompt
        safe_findings = []
        for f in unique:
            safe_f = dict(f)
            if safe_f.get("location", {}).get("snippet"):
                safe_f["location"] = dict(safe_f["location"])
                safe_f["location"]["snippet"] = redact(safe_f["location"]["snippet"])
            safe_findings.append(safe_f)

        user_msg = TRIAGE_USER_TEMPLATE.format(
            root=cc.get("root", ""),
            languages=", ".join(cc.get("languages", {}).keys()),
            frameworks=", ".join(cc.get("frameworks", [])) or "none detected",
            entry_points=", ".join(cc.get("entry_points", [])) or "none detected",
            repo_map="\n".join(cc.get("repo_map", "").splitlines()[:100]),
            count=len(unique),
            findings_json=json.dumps(safe_findings, indent=2, default=str),
        )

        result = await ctx.gate.complete(
            task_type="triage",
            messages=[
                {"role": "system", "content": TRIAGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )

        try:
            parsed = json.loads(result.content)
            triaged = parsed.get("findings", [])
        except json.JSONDecodeError:
            log.warning("triage_json_parse_error", content_preview=result.content[:200])
            # Fall back: return all findings with defaults
            triaged = [
                {**f, "confidence": 0.5, "exploit_likelihood": 0.5,
                 "reachability": "unknown", "attack_scenario": "triage parse failed",
                 "priority_score": 5.0, "status": "open", "false_positive_reason": None,
                 "attack_chain": None}
                for f in unique
            ]

        # Merge triage enrichments back onto original finding dicts
        enrichment_map = {t["dedup_key"]: t for t in triaged}
        output_findings = []
        for f in unique:
            enriched = dict(f)
            enrich = enrichment_map.get(f.get("dedup_key", ""), {})
            enriched.update({
                "confidence": enrich.get("confidence", 0.5),
                "exploit_likelihood": enrich.get("exploit_likelihood", 0.5),
                "reachability": enrich.get("reachability", "unknown"),
                "attack_scenario": enrich.get("attack_scenario", ""),
                "priority_score": enrich.get("priority_score", 5.0),
                "status": enrich.get("status", "open"),
                "false_positive_reason": enrich.get("false_positive_reason"),
                "attack_chain": enrich.get("attack_chain"),
            })
            output_findings.append(enriched)

        # Sort by priority_score descending
        output_findings.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        log.info("triage_complete", total=len(unique), open_count=sum(1 for f in output_findings if f["status"] == "open"),
                 dismissed_count=sum(1 for f in output_findings if f["status"] == "dismissed"),
                 scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"triaged_findings": output_findings},
            cost_usd=result.cost_usd,
        )
```

- [ ] **Step 5: Run — expect pass**

```bash
pytest tests/core/agents/test_triage.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add core/agents/triage.py core/agents/prompts/ tests/core/agents/test_triage.py
git commit -m "feat: triage agent with adversarial scoring and attack scenario generation"
```

---

### Task 14: Explainer agent

**Files:**
- Create: `core/agents/explainer.py`
- Create: `core/agents/prompts/explainer.py`
- Create: `tests/core/agents/test_explainer.py`

**Interfaces:**
- Consumes: `AgentContext` with `ctx.extra["triaged_findings"]` (list of enriched Finding dicts)
- Produces: `AgentOutput` where `data["explained_findings"]` is `list[dict]` — each finding dict with an added `explanation` field containing a concise, developer-facing narrative that leads with the attack scenario

- [ ] **Step 1: Write failing test**

```python
# tests/core/agents/test_explainer.py
from __future__ import annotations
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from core.agents.explainer import ExplainerAgent
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode, ModelTier
from core.governance.gate import GateResult, GovernanceGate


MOCK_EXPLANATION = (
    "An attacker can send a crafted username like ' OR '1'='1 to bypass authentication "
    "or dump the entire users table. The query is built by string interpolation at app.py:5, "
    "where `username` flows directly from the HTTP request with no sanitization. "
    "Fix: use parameterized queries — conn.execute('SELECT * FROM users WHERE username = ?', (username,))."
)


@pytest.fixture
def mock_gate():
    gate = MagicMock(spec=GovernanceGate)
    gate.complete = AsyncMock(return_value=GateResult(
        content=f'{{"explanations": [{{"dedup_key": "semgrep:python.injection.sql:app.py:5", "explanation": "{MOCK_EXPLANATION}"}}]}}',
        tokens_in=400, tokens_out=150, cache_hit=False,
        model_id="claude-haiku-4-5-20251001", provider="anthropic",
        tier=ModelTier.fast, cost_usd=0.001,
    ))
    return gate


@pytest.fixture
def ctx(mock_gate):
    scan = Scan(target_ref="tests/fixtures/vulnerable_python",
                pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    triaged = [{
        "id": str(uuid4()), "scan_id": str(uuid4()),
        "rule_id": "python.injection.sql", "source_tool": "semgrep",
        "severity": "high", "cwe": "CWE-89", "owasp_category": "A03:2021",
        "dedup_key": "semgrep:python.injection.sql:app.py:5",
        "location": {"file": "app.py", "line_start": 5, "line_end": 6, "snippet": "query = f\"...\""},
        "confidence": 0.92, "exploit_likelihood": 0.85,
        "reachability": "reachable from HTTP",
        "attack_scenario": "Attacker sends crafted username to dump users table.",
        "priority_score": 9.2, "status": "open",
    }]
    return AgentContext(
        scan=scan, skills=[], budget_slice_usd=0.5, gate=mock_gate,
        extra={"triaged_findings": triaged},
    )


async def test_explainer_adds_explanation(ctx):
    agent = ExplainerAgent()
    result = await agent.run(ctx)
    explained = result.data["explained_findings"]
    assert len(explained) == 1
    assert "explanation" in explained[0]
    assert len(explained[0]["explanation"]) > 50


async def test_explainer_skips_dismissed(ctx):
    ctx.extra["triaged_findings"][0]["status"] = "dismissed"
    agent = ExplainerAgent()
    result = await agent.run(ctx)
    explained = result.data["explained_findings"]
    # dismissed findings pass through without LLM call
    assert explained[0].get("explanation") is None or explained[0].get("explanation") == ""
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/agents/test_explainer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement core/agents/prompts/explainer.py**

```python
# core/agents/prompts/explainer.py

EXPLAINER_SYSTEM = """\
You are a security advisor writing for the developer who owns the vulnerable code.
Lead every explanation with the attack: what an adversary does, what they get, and how they do it.
Then explain why the code is vulnerable in one sentence.
Then give the exact fix — a one-line or minimal diff, not general advice.
Be specific, be brief, be actionable. No padding, no CVE numbers, no OWASP chapter references.
Return only a JSON object. No prose outside the JSON.
"""

EXPLAINER_USER_TEMPLATE = """\
Explain each open finding below. For each, return:
- The attack scenario (from triage, refine into one sharp sentence a developer will remember)
- Why this specific code is vulnerable (one sentence)
- The exact minimal fix (code or diff)

Findings ({count} open):
{findings_json}

Return:
{{
  "explanations": [
    {{
      "dedup_key": "<exact dedup_key>",
      "explanation": "<attack scenario. vulnerability cause. exact fix.>"
    }}
  ]
}}
"""
```

- [ ] **Step 4: Implement core/agents/explainer.py**

```python
# core/agents/explainer.py
from __future__ import annotations
import json
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.explainer import EXPLAINER_SYSTEM, EXPLAINER_USER_TEMPLATE
from core.model.redaction import redact

log = structlog.get_logger()


class ExplainerAgent:
    agent_id = "explainer"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        all_findings: list[dict] = ctx.extra.get("triaged_findings", [])
        open_findings = [f for f in all_findings if f.get("status") == "open"]

        if not open_findings:
            return AgentOutput(
                agent_id=self.agent_id,
                data={"explained_findings": all_findings},
                cost_usd=0.0,
            )

        # Redact snippets before sending to LLM
        safe = []
        for f in open_findings:
            sf = dict(f)
            if sf.get("location", {}).get("snippet"):
                sf["location"] = dict(sf["location"])
                sf["location"]["snippet"] = redact(sf["location"]["snippet"])
            safe.append(sf)

        user_msg = EXPLAINER_USER_TEMPLATE.format(
            count=len(safe),
            findings_json=json.dumps(safe, indent=2, default=str),
        )

        result = await ctx.gate.complete(
            task_type="explanation",
            messages=[
                {"role": "system", "content": EXPLAINER_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )

        try:
            parsed = json.loads(result.content)
            explanations = {e["dedup_key"]: e["explanation"] for e in parsed.get("explanations", [])}
        except (json.JSONDecodeError, KeyError):
            log.warning("explainer_json_parse_error", content_preview=result.content[:200])
            explanations = {}

        output = []
        for f in all_findings:
            enriched = dict(f)
            if f.get("status") == "open":
                enriched["explanation"] = explanations.get(f["dedup_key"], "")
            output.append(enriched)

        return AgentOutput(
            agent_id=self.agent_id,
            data={"explained_findings": output},
            cost_usd=result.cost_usd,
        )
```

- [ ] **Step 5: Run — expect pass**

```bash
pytest tests/core/agents/test_explainer.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add core/agents/explainer.py core/agents/prompts/explainer.py \
        tests/core/agents/test_explainer.py
git commit -m "feat: explainer agent — attack-led developer explanations"
```

---

### Task 15: Orchestrator + pipeline runner

**Files:**
- Create: `core/agents/orchestrator.py`
- Create: `core/db/pipeline_seed.py`
- Create: `tests/core/agents/test_orchestrator.py`

**Interfaces:**
- Consumes: `PipelineConfig`, `GovernanceGate`, `AsyncSession`, `ScanEventBus`
- Produces: `Orchestrator.run(scan: Scan, session: AsyncSession) -> list[dict]` — returns list of enriched, explained Finding dicts; emits SSE events throughout; writes `ScanRow` status updates; writes `CostLedgerEntry` rows

- [ ] **Step 1: Write failing test**

```python
# tests/core/agents/test_orchestrator.py
from __future__ import annotations
import pytest
from uuid import uuid4
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from core.agents.orchestrator import Orchestrator
from core.model.entities import Scan, ScanMode, ModelTier
from core.governance.gate import GateResult


MOCK_TRIAGE_RESPONSE = '''{
  "findings": [{
    "dedup_key": "semgrep:python.lang.security.audit.formatted-sql-query.formatted-sql-query:app.py:5",
    "confidence": 0.9, "exploit_likelihood": 0.85,
    "reachability": "reachable from HTTP input",
    "attack_scenario": "Attacker injects SQL via username parameter.",
    "priority_score": 9.0, "status": "open",
    "false_positive_reason": null, "attack_chain": null
  }]
}'''

MOCK_EXPLAIN_RESPONSE = '''{
  "explanations": [{
    "dedup_key": "semgrep:python.lang.security.audit.formatted-sql-query.formatted-sql-query:app.py:5",
    "explanation": "Attacker injects SQL via username. String interpolation at app.py:5 is unsanitized. Fix: use parameterized queries."
  }]
}'''


@pytest.fixture
def mock_gate():
    gate = MagicMock()
    gate.complete = AsyncMock(side_effect=[
        GateResult(content=MOCK_TRIAGE_RESPONSE, tokens_in=800, tokens_out=200,
                   cache_hit=False, model_id="claude-sonnet-4-6", provider="anthropic",
                   tier=ModelTier.balanced, cost_usd=0.006),
        GateResult(content=MOCK_EXPLAIN_RESPONSE, tokens_in=400, tokens_out=100,
                   cache_hit=False, model_id="claude-haiku-4-5-20251001", provider="anthropic",
                   tier=ModelTier.fast, cost_usd=0.001),
    ])
    gate._budget = MagicMock()
    gate._budget.record = MagicMock()
    return gate


async def test_orchestrator_runs_full_pipeline(mock_gate):
    scan = Scan(
        target_ref=str(Path("tests/fixtures/vulnerable_python").resolve()),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    session.add = MagicMock()
    session.flush = AsyncMock()

    orch = Orchestrator(gate=mock_gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
    findings = await orch.run(scan, session)

    assert isinstance(findings, list)
    assert len(findings) >= 1
    first = findings[0]
    assert "attack_scenario" in first
    assert "explanation" in first
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/agents/test_orchestrator.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement core/agents/orchestrator.py**

```python
# core/agents/orchestrator.py
from __future__ import annotations
import asyncio
import yaml
import structlog
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.base import AgentContext, AgentOutput
from core.agents.ingestion import IngestionAgent
from core.agents.triage import TriageAgent
from core.agents.explainer import ExplainerAgent
from core.scanners.semgrep import SemgrepAdapter
from core.scanners.trufflehog import TruffleHogAdapter
from core.governance.gate import GovernanceGate
from core.governance.events import event_bus
from core.governance.ledger import CostLedger
from core.model.entities import (
    Scan, ScanStatus, CostLedgerEntry, ModelTier, AuditLogEntry,
)
from core.db.tables import ScanRow, FindingRow, AuditLogEntryRow

log = structlog.get_logger()

_AGENT_REGISTRY: dict[str, type] = {
    "IngestionAgent": IngestionAgent,
    "SemgrepAdapter": SemgrepAdapter,
    "TruffleHogAdapter": TruffleHogAdapter,
    "TriageAgent": TriageAgent,
    "ExplainerAgent": ExplainerAgent,
}

_SCANNER_AGENTS = {"SemgrepAdapter", "TruffleHogAdapter"}


class Orchestrator:
    def __init__(
        self,
        gate: GovernanceGate,
        pipeline_config_path: str = "config/pipeline_configs/full-scan.yaml",
    ) -> None:
        self._gate = gate
        self._ledger = CostLedger()
        raw = yaml.safe_load(Path(pipeline_config_path).read_text())
        self._pipeline = raw
        self._nodes: dict[str, dict] = {n["id"]: n for n in raw["nodes"]}
        self._edges: list[dict] = raw["edges"]

    async def run(self, scan: Scan, session: AsyncSession) -> list[dict]:
        event_bus.emit(scan.id, {"event": "scan_started", "scan_id": str(scan.id)})
        state: dict[str, AgentOutput] = {}
        total_cost = 0.0

        execution_order = self._topological_sort()

        for node_id in execution_order:
            node = self._nodes[node_id]
            agent_cls = _AGENT_REGISTRY.get(node["agent"])
            if not agent_cls:
                log.warning("unknown_agent", agent=node["agent"])
                continue

            tier = ModelTier(node.get("tier", "balanced")) if node.get("tier") != "none" else ModelTier.none
            budget_slice = scan.id  # budget managed per-scan by GovernanceGate

            # Build context with outputs from predecessor nodes
            extra = self._build_extra(node_id, state)

            ctx = AgentContext(
                scan=scan,
                skills=[],
                budget_slice_usd=0.0,
                gate=self._gate,
                extra=extra,
            )

            event_bus.emit(scan.id, {
                "event": "agent_started",
                "agent": node_id,
                "agent_class": node["agent"],
            })

            try:
                agent = agent_cls()
                output = await agent.run(ctx)
            except Exception as e:
                log.error("agent_error", agent=node_id, error=str(e), scan_id=str(scan.id))
                event_bus.emit(scan.id, {"event": "agent_error", "agent": node_id, "error": str(e)})
                output = AgentOutput(agent_id=node_id, data={}, skipped=True, skip_reason=str(e))

            state[node_id] = output
            total_cost += output.cost_usd

            if output.cost_usd > 0:
                entry = CostLedgerEntry(
                    scope_type="scan",
                    scope_id=scan.id,
                    tokens_in=0,
                    tokens_out=0,
                    tier=tier,
                    provider="anthropic",
                    model_id="",
                    cost_usd=output.cost_usd,
                )
                await self._ledger.record(entry, session)

            event_bus.emit(scan.id, {
                "event": "agent_completed",
                "agent": node_id,
                "cost_usd": output.cost_usd,
                "skipped": output.skipped,
            })

        findings = self._collect_findings(state)
        await self._persist_findings(findings, scan, session)

        event_bus.emit(scan.id, {
            "event": "scan_completed",
            "total_cost_usd": total_cost,
            "finding_count": len(findings),
        })

        return findings

    def _topological_sort(self) -> list[str]:
        deps: dict[str, set[str]] = {n: set() for n in self._nodes}
        for edge in self._edges:
            deps[edge["to"]].add(edge["from"])
        order = []
        remaining = set(self._nodes.keys())
        while remaining:
            ready = [n for n in remaining if not deps[n] - set(order)]
            if not ready:
                raise ValueError("Cycle detected in pipeline config")
            ready.sort()
            order.append(ready[0])
            remaining.remove(ready[0])
        return order

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
        # Pass triage output to explainer
        if "triage" in state:
            extra["triaged_findings"] = state["triage"].data.get("triaged_findings", [])
        return extra

    def _collect_findings(self, state: dict[str, AgentOutput]) -> list[dict]:
        if "explainer" in state:
            return state["explainer"].data.get("explained_findings", [])
        if "triage" in state:
            return state["triage"].data.get("triaged_findings", [])
        findings = []
        for nid, output in state.items():
            if self._nodes.get(nid, {}).get("agent") in _SCANNER_AGENTS:
                findings.extend(output.data.get("findings", []))
        return findings

    async def _persist_findings(
        self, findings: list[dict], scan: Scan, session: AsyncSession
    ) -> None:
        for f in findings:
            row = FindingRow(
                id=str(f.get("id", "")),
                scan_id=str(scan.id),
                rule_id=f.get("rule_id", ""),
                source_tool=f.get("source_tool", ""),
                cwe=f.get("cwe"),
                owasp_category=f.get("owasp_category"),
                severity=f.get("severity", "info"),
                exploit_likelihood=f.get("exploit_likelihood", 0.5),
                confidence=f.get("confidence", 0.5),
                reachability=f.get("reachability"),
                location=f.get("location", {}),
                dedup_key=f.get("dedup_key", ""),
                status=f.get("status", "open"),
                explanation=f.get("explanation"),
            )
            session.add(row)
        try:
            await session.flush()
        except Exception as e:
            log.warning("persist_findings_error", error=str(e))
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/core/agents/test_orchestrator.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add core/agents/orchestrator.py core/db/pipeline_seed.py \
        tests/core/agents/test_orchestrator.py
git commit -m "feat: pipeline orchestrator, topological sort, SSE event emission"
```

---

### Task 16: FastAPI app + routes + SSE

**Files:**
- Create: `core/api/app.py`
- Create: `core/api/deps.py`
- Create: `core/api/routers/scans.py`
- Create: `core/api/routers/findings.py`
- Create: `core/api/routers/cost.py`
- Create: `core/api/sse.py`
- Create: `tests/core/api/test_scans.py`
- Create: `tests/core/api/test_sse.py`

**Interfaces:**
- Consumes: `Orchestrator`, `CostLedger`, `ScanEventBus` (`event_bus`)
- Produces: Running FastAPI app, OpenAPI JSON at `/openapi.json`, SSE stream at `GET /api/v1/scans/{id}/events`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/api/test_scans.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
async def client():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_openapi_schema_exists(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    assert "/api/v1/scans" in schema["paths"]
```

```python
# tests/core/api/test_sse.py
from __future__ import annotations
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from core.governance.events import ScanEventBus


async def test_sse_receives_events():
    from core.api.app import create_app
    bus = ScanEventBus()
    app = create_app(event_bus=bus)
    scan_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def emit_events():
            await asyncio.sleep(0.05)
            bus.emit(scan_id, {"event": "agent_started", "agent": "triage"})
            bus.emit(scan_id, {"event": "scan_completed", "total_cost_usd": 0.01})

        asyncio.create_task(emit_events())

        lines = []
        async with client.stream("GET", f"/api/v1/scans/{scan_id}/events") as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    lines.append(line)
                if len(lines) >= 2:
                    break

    assert any("agent_started" in l for l in lines)
    assert any("scan_completed" in l for l in lines)
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/api/ -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement core/api/deps.py**

```python
# core/api/deps.py
from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.session import get_session as _get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session() as session:
        yield session
```

- [ ] **Step 4: Implement core/api/sse.py**

```python
# core/api/sse.py
from __future__ import annotations
import json
from uuid import UUID
from sse_starlette.sse import EventSourceResponse
from core.governance.events import ScanEventBus


def scan_event_stream(scan_id: UUID, bus: ScanEventBus):
    async def generator():
        async for event in bus.subscribe(scan_id):
            yield {"data": json.dumps(event, default=str)}

    return EventSourceResponse(generator())
```

- [ ] **Step 5: Implement core/api/routers/scans.py**

```python
# core/api/routers/scans.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.tables import ScanRow, FindingRow
from core.model.entities import ScanMode

router = APIRouter(prefix="/scans", tags=["scans"])


class TriggerScanRequest(BaseModel):
    target_ref: str
    mode: ScanMode = ScanMode.at_rest
    pipeline_config_name: str = "full-scan"


@router.get("/")
async def list_scans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).order_by(ScanRow.started_at.desc()).limit(50))
    rows = result.scalars().all()
    return [{"id": r.id, "target_ref": r.target_ref, "status": r.status,
             "mode": r.mode, "cost_usd": r.cost_usd} for r in rows]


@router.post("/", status_code=202)
async def trigger_scan(
    body: TriggerScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from uuid import uuid4
    from core.model.entities import Scan
    from core.db.tables import ScanRow as SR
    from datetime import datetime, timezone
    import os

    scan_id = uuid4()
    row = SR(
        id=str(scan_id),
        target_ref=body.target_ref,
        pipeline_config_id=str(uuid4()),
        mode=body.mode.value,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()

    scan = Scan(id=scan_id, target_ref=body.target_ref,
                pipeline_config_id=scan_id, mode=body.mode)

    from core.governance.gate import GovernanceGate
    from core.agents.orchestrator import Orchestrator

    config_path = f"config/pipeline_configs/{body.pipeline_config_name}.yaml"
    gate = GovernanceGate()
    orch = Orchestrator(gate=gate, pipeline_config_path=config_path)

    async def _run():
        from core.db.session import get_session
        async with get_session() as s:
            await orch.run(scan, s)

    background_tasks.add_task(_run)
    return {"scan_id": str(scan_id), "status": "accepted"}


@router.get("/{scan_id}")
async def get_scan(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"id": row.id, "target_ref": row.target_ref, "status": row.status,
            "mode": row.mode, "cost_usd": row.cost_usd,
            "started_at": row.started_at, "finished_at": row.finished_at}
```

- [ ] **Step 6: Implement core/api/routers/findings.py**

```python
# core/api/routers/findings.py
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import FindingRow

router = APIRouter(prefix="/scans", tags=["findings"])


@router.get("/{scan_id}/findings")
async def list_findings(
    scan_id: UUID,
    severity: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(FindingRow).where(FindingRow.scan_id == str(scan_id))
    if severity:
        q = q.where(FindingRow.severity == severity)
    if status:
        q = q.where(FindingRow.status == status)
    q = q.order_by(FindingRow.exploit_likelihood.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "rule_id": r.rule_id, "source_tool": r.source_tool,
            "cwe": r.cwe, "owasp_category": r.owasp_category,
            "severity": r.severity, "confidence": r.confidence,
            "exploit_likelihood": r.exploit_likelihood,
            "reachability": r.reachability,
            "location": r.location, "status": r.status,
            "explanation": r.explanation,
        }
        for r in rows
    ]
```

- [ ] **Step 7: Implement core/api/routers/cost.py**

```python
# core/api/routers/cost.py
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.api.deps import get_db
from core.db.tables import CostLedgerEntryRow

router = APIRouter(prefix="/cost", tags=["cost"])


@router.get("/ledger")
async def get_ledger(
    scope_type: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    q = select(CostLedgerEntryRow).order_by(CostLedgerEntryRow.timestamp.desc()).limit(limit)
    if scope_type:
        q = q.where(CostLedgerEntryRow.scope_type == scope_type)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {"id": r.id, "scope_type": r.scope_type, "scope_id": r.scope_id,
         "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
         "tier": r.tier, "provider": r.provider, "model_id": r.model_id,
         "cost_usd": r.cost_usd, "timestamp": r.timestamp}
        for r in rows
    ]


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.sum(CostLedgerEntryRow.cost_usd).label("total_cost_usd"),
            func.sum(CostLedgerEntryRow.tokens_in).label("total_tokens_in"),
            func.sum(CostLedgerEntryRow.tokens_out).label("total_tokens_out"),
            func.count().label("total_calls"),
        )
    )
    row = result.one()
    return {
        "total_cost_usd": float(row.total_cost_usd or 0),
        "total_tokens_in": int(row.total_tokens_in or 0),
        "total_tokens_out": int(row.total_tokens_out or 0),
        "total_calls": int(row.total_calls or 0),
    }
```

- [ ] **Step 8: Implement core/api/app.py**

```python
# core/api/app.py
from __future__ import annotations
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus
    app = FastAPI(title="Argus Security Platform", version="0.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")

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

    @app.get("/api/v1/fixes/{fix_id}")
    async def get_fix(fix_id: UUID):
        from fastapi import HTTPException
        raise HTTPException(501, "Fix generation available in Phase 2")

    return app
```

- [ ] **Step 9: Run tests — expect pass**

```bash
pytest tests/core/api/ -v
```

Expected: 3 passed.

- [ ] **Step 10: Commit**

```bash
git add core/api/ tests/core/api/
git commit -m "feat: FastAPI app, scan/findings/cost routes, SSE event stream"
```

---

*Agents & API plan complete. Continue with [2026-06-17-phase1-skills-dashboard.md] for Tasks 17–21 (skills, React dashboard).*
