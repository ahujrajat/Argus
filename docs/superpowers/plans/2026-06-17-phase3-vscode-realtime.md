# Phase 3: VS Code Extension, Real-time Mode, CI Step — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the scan lifecycle gaps, ship a VS Code extension (trigger + tree + CodeLens), add real-time incremental diff mode, and deliver a CI step for severity gating.

**Architecture:** Four vertical slices: (1) backend lifecycle closes the pending-forever gap and adds cancel; (2) the VS Code extension is a standalone TypeScript project under `surfaces/vscode-extension/` that calls the Argus API; (3) real-time diff mode adds a `diff.py` util and a fast-path branch in the orchestrator; (4) a CI step is a bash+YAML artefact with no new deps.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy async 2.0 · TypeScript 5 · VS Code Extension API 1.85 · bash

## Global Constraints

- `from __future__ import annotations` in every new Python file
- Python ≥ 3.12; Pydantic v2 only
- All Python tests: pytest `asyncio_mode = "auto"`; use `dependency_overrides[get_db]` for DB mocking
- VS Code extension: TypeScript 5, `engines.vscode: "^1.85.0"`, no webpack (use esbuild), `"type": "commonjs"` in package.json
- No new Python pip dependencies unless unavoidable; `gitpython` is available if needed for diff
- Accenture theme: `#A100FF` accent

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `core/agents/orchestrator.py` | Modify | Update `ScanRow.status` to running/completed/failed; set `finished_at` |
| `core/api/routers/scans.py` | Modify | Fix `pipeline_config_id` lookup; add `DELETE /scans/{id}` cancel endpoint |
| `tests/core/agents/test_orchestrator_lifecycle.py` | Create | Tests for status transitions in orchestrator |
| `tests/core/api/test_scan_cancel.py` | Create | Tests for cancel endpoint |
| `surfaces/vscode-extension/package.json` | Create | VS Code extension manifest, esbuild scripts |
| `surfaces/vscode-extension/tsconfig.json` | Create | TypeScript config targeting CommonJS |
| `surfaces/vscode-extension/src/extension.ts` | Create | `activate`/`deactivate` entry point, command registration |
| `surfaces/vscode-extension/src/commands/triggerScan.ts` | Create | `argus.triggerScan` command impl calling POST /api/v1/scans/ |
| `surfaces/vscode-extension/src/providers/FindingsTreeProvider.ts` | Create | TreeDataProvider showing findings per scan with live polling |
| `surfaces/vscode-extension/src/providers/FindingCodeLensProvider.ts` | Create | CodeLens on each finding's source file+line |
| `core/understanding/diff.py` | Create | `compute_diff_files(repo_path, base_ref) -> list[str]` via git |
| `core/agents/orchestrator.py` | Modify | Branch on `ScanMode.real_time` to restrict scanners to diff files |
| `surfaces/ci/argus-scan.sh` | Create | Bash entrypoint: trigger scan, poll status, exit 1 on critical/high |
| `surfaces/ci/action.yml` | Create | GitHub Actions composite step wrapping the bash script |
| `surfaces/dashboard/src/pages/runs/RunsPage.tsx` | Modify | Add status badge + cancel button to scan list |
| `surfaces/dashboard/src/api/client.ts` | Modify | Add `cancelScan` method |

---

## Task 1: Scan Lifecycle — Orchestrator Status Updates

**Files:**
- Modify: `core/agents/orchestrator.py`
- Create: `tests/core/agents/test_orchestrator_lifecycle.py`

**Interfaces:**
- Consumes: `ScanRow` from `core/db/tables.py` (fields: `id`, `status`, `finished_at`)
- Consumes: `AsyncSession` from SQLAlchemy with `execute`, `flush`
- Produces: `Orchestrator.run()` now sets `ScanRow.status` to `"running"` at start, `"completed"` at end, `"failed"` on exception; sets `finished_at` on completion/failure

- [ ] **Step 1.1: Write the failing tests**

```python
# tests/core/agents/test_orchestrator_lifecycle.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from core.agents.orchestrator import Orchestrator
from core.model.entities import Scan, ScanMode, SecurityApproach, ModelTier
from core.governance.gate import GateResult
from core.db.tables import ScanRow


def _make_scan() -> Scan:
    return Scan(
        target_ref="/tmp/repo",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
        approach=SecurityApproach.penetration_testing,
    )


def _make_gate_noop() -> MagicMock:
    gate = MagicMock()
    gate.complete = AsyncMock(return_value=GateResult(
        content='{"findings": []}',
        tokens_in=10, tokens_out=5,
        cache_hit=False,
        model_id="claude-haiku-4-5",
        provider="anthropic",
        tier=ModelTier.fast,
        cost_usd=0.0,
    ))
    gate._budget = MagicMock()
    gate._budget.record = MagicMock()
    return gate


async def test_orchestrator_sets_status_running_then_completed():
    scan = _make_scan()
    gate = _make_gate_noop()

    scan_row = ScanRow(
        id=str(scan.id),
        target_ref=scan.target_ref,
        pipeline_config_id=str(scan.pipeline_config_id),
        mode=scan.mode.value,
        approach=scan.approach.value,
        status="pending",
    )

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("core.agents.ingestion.IngestionAgent.run", new_callable=AsyncMock) as mock_ingest, \
         patch("core.scanners.semgrep.SemgrepAdapter.scan", new_callable=AsyncMock) as mock_semgrep, \
         patch("core.scanners.trufflehog.TruffleHogAdapter.scan", new_callable=AsyncMock) as mock_truffle:
        from core.agents.base import AgentOutput
        mock_ingest.return_value = AgentOutput(agent_id="ingestion", data={"code_context": {}})
        mock_semgrep.return_value = AgentOutput(agent_id="sast", data={"findings": []})
        mock_truffle.return_value = AgentOutput(agent_id="secrets", data={"findings": []})

        orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
        await orch.run(scan, session)

    assert scan_row.status == "completed"
    assert scan_row.finished_at is not None


async def test_orchestrator_sets_status_failed_on_exception():
    scan = _make_scan()
    gate = _make_gate_noop()

    scan_row = ScanRow(
        id=str(scan.id),
        target_ref=scan.target_ref,
        pipeline_config_id=str(scan.pipeline_config_id),
        mode=scan.mode.value,
        approach=scan.approach.value,
        status="pending",
    )

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("core.agents.ingestion.IngestionAgent.run", new_callable=AsyncMock) as mock_ingest:
        mock_ingest.side_effect = RuntimeError("disk full")
        orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
        with pytest.raises(RuntimeError, match="disk full"):
            await orch.run(scan, session)

    assert scan_row.status == "failed"
    assert scan_row.finished_at is not None


async def test_orchestrator_sets_status_running_at_start():
    """Verify status transitions to 'running' immediately before any agent runs."""
    scan = _make_scan()
    gate = _make_gate_noop()

    scan_row = ScanRow(
        id=str(scan.id),
        target_ref=scan.target_ref,
        pipeline_config_id=str(scan.pipeline_config_id),
        mode=scan.mode.value,
        approach=scan.approach.value,
        status="pending",
    )
    observed_statuses: list[str] = []

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()

    async def capturing_flush():
        observed_statuses.append(scan_row.status)

    session.flush = capturing_flush

    with patch("core.agents.ingestion.IngestionAgent.run", new_callable=AsyncMock) as mock_ingest, \
         patch("core.scanners.semgrep.SemgrepAdapter.scan", new_callable=AsyncMock) as mock_semgrep, \
         patch("core.scanners.trufflehog.TruffleHogAdapter.scan", new_callable=AsyncMock) as mock_truffle:
        from core.agents.base import AgentOutput
        mock_ingest.return_value = AgentOutput(agent_id="ingestion", data={"code_context": {}})
        mock_semgrep.return_value = AgentOutput(agent_id="sast", data={"findings": []})
        mock_truffle.return_value = AgentOutput(agent_id="secrets", data={"findings": []})

        orch = Orchestrator(gate=gate, pipeline_config_path="config/pipeline_configs/full-scan.yaml")
        await orch.run(scan, session)

    assert "running" in observed_statuses
    assert observed_statuses[0] == "running"
```

- [ ] **Step 1.2: Run the tests to verify they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_orchestrator_lifecycle.py -v
```

Expected output:
```
FAILED tests/core/agents/test_orchestrator_lifecycle.py::test_orchestrator_sets_status_running_then_completed
FAILED tests/core/agents/test_orchestrator_lifecycle.py::test_orchestrator_sets_status_failed_on_exception
FAILED tests/core/agents/test_orchestrator_lifecycle.py::test_orchestrator_sets_status_running_at_start
```

- [ ] **Step 1.3: Update `Orchestrator.run()` to manage scan status**

In `core/agents/orchestrator.py`, replace the existing `run` method with this updated version. The change adds a DB fetch of `ScanRow` at the start, sets status to `"running"`, and wraps the pipeline body in try/except/finally to set `"completed"` or `"failed"` with `finished_at`:

```python
    async def run(self, scan: Scan, session: AsyncSession) -> list[dict]:
        from sqlalchemy import select as _select

        # --- lifecycle: mark running ---
        result = await session.execute(_select(ScanRow).where(ScanRow.id == str(scan.id)))
        scan_row = result.scalar_one_or_none()
        if scan_row is not None:
            scan_row.status = "running"
            await session.flush()

        event_bus.emit(scan.id, {"event": "scan_started", "scan_id": str(scan.id)})
        state: dict[str, AgentOutput] = {}
        total_cost = 0.0

        execution_order = self._topological_sort()

        try:
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
                    approach=scan.approach,
                    extra=extra,
                )

                event_bus.emit(scan.id, {
                    "event": "agent_started",
                    "agent": node_id,
                    "agent_class": node["agent"],
                })

                try:
                    agent = agent_cls()
                    # Scanner adapters use .scan(), agents use .run()
                    if hasattr(agent, "scan") and not hasattr(agent, "run"):
                        output = await agent.scan(ctx)
                    elif hasattr(agent, "run"):
                        output = await agent.run(ctx)
                    else:
                        raise AttributeError(f"Agent {node['agent']} has neither run() nor scan() method")
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

            fixes = self._collect_fixes(state)
            await self._persist_fixes(fixes, session)

            # --- lifecycle: mark completed ---
            if scan_row is not None:
                scan_row.status = "completed"
                scan_row.finished_at = datetime.now(timezone.utc)
                await session.flush()

            event_bus.emit(scan.id, {
                "event": "scan_completed",
                "total_cost_usd": total_cost,
                "finding_count": len(findings),
            })

            return findings

        except Exception:
            # --- lifecycle: mark failed ---
            if scan_row is not None:
                scan_row.status = "failed"
                scan_row.finished_at = datetime.now(timezone.utc)
                await session.flush()
            event_bus.emit(scan.id, {"event": "scan_failed", "scan_id": str(scan.id)})
            raise
```

- [ ] **Step 1.4: Also fix `trigger_scan` in `core/api/routers/scans.py` to look up the real `pipeline_config_id`**

Replace lines 42–56 of `core/api/routers/scans.py`. The key changes: (a) look up `PipelineConfigRow` by `name` from DB; (b) use its real `id` as `pipeline_config_id` on both `ScanRow` and `Scan`; (c) raise 404 if not found:

```python
@router.post("/", status_code=202)
async def trigger_scan(
    body: TriggerScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from uuid import uuid4
    from core.model.entities import Scan
    from core.db.tables import ScanRow as SR, PipelineConfigRow
    from datetime import datetime, timezone

    # Look up the real pipeline config row
    pc_result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.name == body.pipeline_config_name)
    )
    pc_row = pc_result.scalar_one_or_none()
    if pc_row is None:
        raise HTTPException(status_code=404, detail=f"Pipeline config '{body.pipeline_config_name}' not found")

    scan_id = uuid4()
    row = SR(
        id=str(scan_id),
        target_ref=body.target_ref,
        pipeline_config_id=str(pc_row.id),
        mode=body.mode.value,
        approach=body.approach.value,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()

    from uuid import UUID
    scan = Scan(
        id=scan_id,
        target_ref=body.target_ref,
        pipeline_config_id=UUID(str(pc_row.id)),
        mode=body.mode,
        approach=body.approach,
    )

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
```

- [ ] **Step 1.5: Run the lifecycle tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_orchestrator_lifecycle.py -v
```

Expected output:
```
PASSED tests/core/agents/test_orchestrator_lifecycle.py::test_orchestrator_sets_status_running_then_completed
PASSED tests/core/agents/test_orchestrator_lifecycle.py::test_orchestrator_sets_status_failed_on_exception
PASSED tests/core/agents/test_orchestrator_lifecycle.py::test_orchestrator_sets_status_running_at_start
3 passed in ...
```

- [ ] **Step 1.6: Run existing orchestrator tests to ensure no regressions**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/test_orchestrator.py -v
```

Expected output:
```
PASSED tests/core/agents/test_orchestrator.py::test_orchestrator_runs_full_pipeline
PASSED tests/core/agents/test_orchestrator.py::test_orchestrator_persist_fixes_writes_fix_rows
PASSED tests/core/agents/test_orchestrator.py::test_orchestrator_collect_fixes_reads_fix_generation_state
PASSED tests/core/agents/test_orchestrator.py::test_orchestrator_fix_agent_registered
4 passed in ...
```

- [ ] **Step 1.7: Commit**

```bash
git add core/agents/orchestrator.py core/api/routers/scans.py tests/core/agents/test_orchestrator_lifecycle.py
git commit -m "fix: orchestrator updates scan status (running/completed/failed) and resolves pipeline_config_id from DB"
```

---

## Task 2: Scan Cancel Endpoint

**Files:**
- Modify: `core/api/routers/scans.py`
- Create: `tests/core/api/test_scan_cancel.py`

**Interfaces:**
- Consumes: `ScanRow` fields `status`, `finished_at`
- Produces: `DELETE /api/v1/scans/{scan_id}` → `{"scan_id": str, "status": "cancelled"}` or 404

- [ ] **Step 2.1: Write the failing tests**

```python
# tests/core/api/test_scan_cancel.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from core.db.tables import ScanRow


@pytest.fixture
async def client_with_db():
    from core.api.app import create_app
    from core.api.deps import get_db

    app = create_app()

    async def override_get_db():
        yield mock_session

    mock_session = AsyncMock()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session

    app.dependency_overrides.clear()


async def test_cancel_scan_sets_status_cancelled(client_with_db):
    client, session = client_with_db
    scan_id = str(uuid4())

    scan_row = ScanRow(
        id=scan_id,
        target_ref="github.com/org/repo",
        pipeline_config_id=str(uuid4()),
        mode="at_rest",
        approach="penetration_testing",
        status="running",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    resp = await client.delete(f"/api/v1/scans/{scan_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] == scan_id
    assert body["status"] == "cancelled"
    assert scan_row.status == "cancelled"
    assert scan_row.finished_at is not None


async def test_cancel_scan_returns_404_when_not_found(client_with_db):
    client, session = client_with_db
    scan_id = str(uuid4())

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    resp = await client.delete(f"/api/v1/scans/{scan_id}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Scan not found"


async def test_cancel_already_completed_scan_returns_409(client_with_db):
    client, session = client_with_db
    scan_id = str(uuid4())

    scan_row = ScanRow(
        id=scan_id,
        target_ref="github.com/org/repo",
        pipeline_config_id=str(uuid4()),
        mode="at_rest",
        approach="penetration_testing",
        status="completed",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scan_row
    session.execute = AsyncMock(return_value=mock_result)

    resp = await client.delete(f"/api/v1/scans/{scan_id}")

    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/api/test_scan_cancel.py -v
```

Expected:
```
FAILED tests/core/api/test_scan_cancel.py::test_cancel_scan_sets_status_cancelled - 405 Method Not Allowed
FAILED ...
3 failed in ...
```

- [ ] **Step 2.3: Add the cancel endpoint to `core/api/routers/scans.py`**

Append this new endpoint after the `get_scan` function:

```python
@router.delete("/{scan_id}", status_code=200)
async def cancel_scan(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone

    result = await db.execute(select(ScanRow).where(ScanRow.id == str(scan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")
    if row.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Scan is already {row.status} and cannot be cancelled",
        )
    row.status = "cancelled"
    row.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return {"scan_id": str(scan_id), "status": "cancelled"}
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/api/test_scan_cancel.py -v
```

Expected:
```
PASSED tests/core/api/test_scan_cancel.py::test_cancel_scan_sets_status_cancelled
PASSED tests/core/api/test_scan_cancel.py::test_cancel_scan_returns_404_when_not_found
PASSED tests/core/api/test_scan_cancel.py::test_cancel_already_completed_scan_returns_409
3 passed in ...
```

- [ ] **Step 2.5: Commit**

```bash
git add core/api/routers/scans.py tests/core/api/test_scan_cancel.py
git commit -m "feat: add DELETE /scans/{id} cancel endpoint with 409 guard for terminal states"
```

---

## Task 3: VS Code Extension Scaffold

**Files:**
- Create: `surfaces/vscode-extension/package.json`
- Create: `surfaces/vscode-extension/tsconfig.json`
- Create: `surfaces/vscode-extension/src/extension.ts`
- Create: `surfaces/vscode-extension/.vscodeignore`

**Interfaces:**
- Produces: `activate(context: vscode.ExtensionContext): void` exported from `extension.ts`
- Produces: `deactivate(): void` exported from `extension.ts`
- Produces: extension command `argus.triggerScan` registered (no-op at this stage)

- [ ] **Step 3.1: Create the directory structure**

```bash
mkdir -p /Users/rajat.a.ahuja/Dev/Argus/surfaces/vscode-extension/src
```

- [ ] **Step 3.2: Create `package.json`**

```json
{
  "name": "argus-vscode",
  "displayName": "Argus Security Scanner",
  "description": "AI-powered security scanning inside VS Code",
  "version": "0.1.0",
  "publisher": "accenture-security",
  "type": "commonjs",
  "engines": {
    "vscode": "^1.85.0"
  },
  "categories": ["Other"],
  "activationEvents": ["onStartupFinished"],
  "main": "./out/extension.js",
  "contributes": {
    "commands": [
      {
        "command": "argus.triggerScan",
        "title": "Argus: Trigger Security Scan",
        "icon": "$(shield)"
      }
    ],
    "configuration": {
      "title": "Argus",
      "properties": {
        "argus.apiBase": {
          "type": "string",
          "default": "http://localhost:8000",
          "description": "Base URL of the Argus API server"
        }
      }
    },
    "views": {
      "explorer": [
        {
          "id": "argus.findingsView",
          "name": "Argus Findings"
        }
      ]
    }
  },
  "scripts": {
    "build": "esbuild src/extension.ts --bundle --outfile=out/extension.js --platform=node --target=node18 --external:vscode --format=cjs",
    "watch": "esbuild src/extension.ts --bundle --outfile=out/extension.js --platform=node --target=node18 --external:vscode --format=cjs --watch",
    "package": "npx vsce package"
  },
  "devDependencies": {
    "@types/node": "^18.0.0",
    "@types/vscode": "^1.85.0",
    "esbuild": "^0.20.0",
    "typescript": "^5.3.0"
  }
}
```

Save to: `surfaces/vscode-extension/package.json`

- [ ] **Step 3.3: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2022",
    "lib": ["ES2022"],
    "outDir": "out",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "sourceMap": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "out"]
}
```

Save to: `surfaces/vscode-extension/tsconfig.json`

- [ ] **Step 3.4: Create `src/extension.ts`**

```typescript
// surfaces/vscode-extension/src/extension.ts
import * as vscode from "vscode";

let _disposables: vscode.Disposable[] = [];

export function activate(context: vscode.ExtensionContext): void {
  // Placeholder command — replaced in Task 4
  const triggerCmd = vscode.commands.registerCommand("argus.triggerScan", () => {
    vscode.window.showInformationMessage("Argus: triggerScan not yet implemented");
  });

  _disposables.push(triggerCmd);
  context.subscriptions.push(..._disposables);
}

export function deactivate(): void {
  for (const d of _disposables) {
    d.dispose();
  }
  _disposables = [];
}
```

- [ ] **Step 3.5: Create `.vscodeignore`**

```
.vscode/**
src/**
tsconfig.json
node_modules/**
```

Save to: `surfaces/vscode-extension/.vscodeignore`

- [ ] **Step 3.6: Install dev dependencies and verify build succeeds**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/vscode-extension
npm install
npm run build
```

Expected output:
```
  out/extension.js  ...kb

Done in ...ms
```

File `out/extension.js` must exist.

- [ ] **Step 3.7: Commit**

```bash
git add surfaces/vscode-extension/
git commit -m "feat(vscode): scaffold extension with package.json, tsconfig, and activate/deactivate entry point"
```

---

## Task 4: Extension `argus.triggerScan` Command

**Files:**
- Create: `surfaces/vscode-extension/src/commands/triggerScan.ts`
- Modify: `surfaces/vscode-extension/src/extension.ts`

**Interfaces:**
- Consumes: `vscode.workspace.getConfiguration("argus").get<string>("argus.apiBase")` for API URL
- Produces: `registerTriggerScanCommand(context: vscode.ExtensionContext): vscode.Disposable`

- [ ] **Step 4.1: Create `src/commands/triggerScan.ts`**

```typescript
// surfaces/vscode-extension/src/commands/triggerScan.ts
import * as vscode from "vscode";

interface TriggerScanResponse {
  scan_id: string;
  status: string;
}

export function registerTriggerScanCommand(
  context: vscode.ExtensionContext
): vscode.Disposable {
  return vscode.commands.registerCommand("argus.triggerScan", async () => {
    const config = vscode.workspace.getConfiguration("argus");
    const apiBase = config.get<string>("apiBase") ?? "http://localhost:8000";

    // Prompt for target ref — default to current workspace folder
    const defaultTarget =
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";

    const targetRef = await vscode.window.showInputBox({
      title: "Argus: Trigger Security Scan",
      prompt: "Target repository path or git ref",
      value: defaultTarget,
      ignoreFocusOut: true,
    });
    if (targetRef === undefined) {
      // user pressed Escape
      return;
    }

    const modeOptions: vscode.QuickPickItem[] = [
      { label: "at_rest", description: "Full scan of all files" },
      { label: "real_time", description: "Diff-only scan of changed files" },
    ];
    const modePick = await vscode.window.showQuickPick(modeOptions, {
      title: "Argus: Select Scan Mode",
      placeHolder: "Select scan mode",
    });
    if (!modePick) {
      return;
    }

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Argus: Starting scan…",
        cancellable: false,
      },
      async () => {
        let response: TriggerScanResponse;
        try {
          const res = await fetch(`${apiBase}/api/v1/scans/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              target_ref: targetRef,
              mode: modePick.label,
              approach: "penetration_testing",
              pipeline_config_name: "full-scan",
            }),
          });
          if (!res.ok) {
            const text = await res.text();
            throw new Error(`${res.status}: ${text}`);
          }
          response = (await res.json()) as TriggerScanResponse;
        } catch (err) {
          vscode.window.showErrorMessage(
            `Argus: Failed to start scan — ${(err as Error).message}`
          );
          return;
        }

        vscode.window.showInformationMessage(
          `Argus: Scan started (ID: ${response.scan_id})`,
          "View Findings"
        );
      }
    );
  });
}
```

- [ ] **Step 4.2: Update `src/extension.ts` to use the real command**

Replace the entire contents of `surfaces/vscode-extension/src/extension.ts`:

```typescript
// surfaces/vscode-extension/src/extension.ts
import * as vscode from "vscode";
import { registerTriggerScanCommand } from "./commands/triggerScan";

let _disposables: vscode.Disposable[] = [];

export function activate(context: vscode.ExtensionContext): void {
  _disposables.push(registerTriggerScanCommand(context));
  context.subscriptions.push(..._disposables);
}

export function deactivate(): void {
  for (const d of _disposables) {
    d.dispose();
  }
  _disposables = [];
}
```

- [ ] **Step 4.3: Verify the extension builds**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/vscode-extension
npm run build
```

Expected output:
```
  out/extension.js  ...kb

Done in ...ms
```

No TypeScript errors.

- [ ] **Step 4.4: Commit**

```bash
git add surfaces/vscode-extension/src/commands/triggerScan.ts surfaces/vscode-extension/src/extension.ts
git commit -m "feat(vscode): implement argus.triggerScan command with API base config, target prompt, and mode picker"
```

---

## Task 5: Extension `FindingsTreeProvider`

**Files:**
- Create: `surfaces/vscode-extension/src/providers/FindingsTreeProvider.ts`
- Modify: `surfaces/vscode-extension/src/extension.ts`

**Interfaces:**
- Consumes: `GET {apiBase}/api/v1/scans/` → `ScanDTO[]`; `GET {apiBase}/api/v1/scans/{id}/findings` → `FindingDTO[]`
- Produces: `FindingsTreeProvider` implementing `vscode.TreeDataProvider<FindingTreeItem>`; polling every 5 seconds when a scan is selected; `refresh()` method for manual refresh

- [ ] **Step 5.1: Create `src/providers/FindingsTreeProvider.ts`**

```typescript
// surfaces/vscode-extension/src/providers/FindingsTreeProvider.ts
import * as vscode from "vscode";

interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  cost_usd: number;
}

interface FindingDTO {
  id: string;
  rule_id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  location: { file: string; line_start: number; line_end: number };
  explanation: string | null;
  cwe: string | null;
}

type FindingTreeItem = ScanItem | FindingItem;

class ScanItem extends vscode.TreeItem {
  constructor(public readonly scan: ScanDTO) {
    super(
      `${scan.target_ref} [${scan.status}]`,
      vscode.TreeItemCollapsibleState.Collapsed
    );
    this.contextValue = "argus.scan";
    this.id = `scan:${scan.id}`;
    this.iconPath = new vscode.ThemeIcon(
      scan.status === "completed"
        ? "pass"
        : scan.status === "failed"
        ? "error"
        : scan.status === "running"
        ? "sync~spin"
        : "circle-outline"
    );
    this.description = `$${scan.cost_usd.toFixed(3)}`;
  }
}

class FindingItem extends vscode.TreeItem {
  constructor(
    public readonly finding: FindingDTO,
    public readonly scanId: string
  ) {
    super(finding.rule_id, vscode.TreeItemCollapsibleState.None);
    this.contextValue = "argus.finding";
    this.id = `finding:${finding.id}`;
    this.description = `${finding.location.file}:${finding.location.line_start}`;
    this.tooltip = finding.explanation ?? finding.rule_id;
    this.iconPath = new vscode.ThemeIcon(
      finding.severity === "critical" || finding.severity === "high"
        ? "warning"
        : "info"
    );
    this.command = {
      command: "vscode.open",
      title: "Open file",
      arguments: [
        vscode.Uri.file(finding.location.file),
        {
          selection: new vscode.Range(
            new vscode.Position(Math.max(0, finding.location.line_start - 1), 0),
            new vscode.Position(Math.max(0, finding.location.line_start - 1), 0)
          ),
        },
      ],
    };
  }
}

export class FindingsTreeProvider
  implements vscode.TreeDataProvider<FindingTreeItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    FindingTreeItem | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _scans: ScanDTO[] = [];
  private _findings: Map<string, FindingDTO[]> = new Map();
  private _pollingTimer: ReturnType<typeof setInterval> | undefined;
  private _selectedScanId: string | undefined;

  constructor(private readonly getApiBase: () => string) {}

  startPolling(): void {
    this._pollingTimer = setInterval(() => void this.refresh(), 5000);
  }

  stopPolling(): void {
    if (this._pollingTimer !== undefined) {
      clearInterval(this._pollingTimer);
      this._pollingTimer = undefined;
    }
  }

  selectScan(scanId: string): void {
    this._selectedScanId = scanId;
    void this.refresh();
  }

  async refresh(): Promise<void> {
    const apiBase = this.getApiBase();
    try {
      const res = await fetch(`${apiBase}/api/v1/scans/`);
      if (res.ok) {
        this._scans = (await res.json()) as ScanDTO[];
      }
    } catch {
      // network errors are non-fatal; keep showing stale data
    }

    if (this._selectedScanId) {
      try {
        const res = await fetch(
          `${apiBase}/api/v1/scans/${this._selectedScanId}/findings`
        );
        if (res.ok) {
          const findings = (await res.json()) as FindingDTO[];
          this._findings.set(this._selectedScanId, findings);
        }
      } catch {
        // non-fatal
      }
    }

    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: FindingTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: FindingTreeItem): Promise<FindingTreeItem[]> {
    if (!element) {
      // Root: show all scans
      if (this._scans.length === 0) {
        await this.refresh();
      }
      return this._scans.map((s) => new ScanItem(s));
    }

    if (element instanceof ScanItem) {
      const scanId = element.scan.id;
      if (!this._findings.has(scanId)) {
        const apiBase = this.getApiBase();
        try {
          const res = await fetch(
            `${apiBase}/api/v1/scans/${scanId}/findings`
          );
          if (res.ok) {
            const findings = (await res.json()) as FindingDTO[];
            this._findings.set(scanId, findings);
          }
        } catch {
          return [];
        }
      }
      return (this._findings.get(scanId) ?? []).map(
        (f) => new FindingItem(f, scanId)
      );
    }

    return [];
  }

  dispose(): void {
    this.stopPolling();
    this._onDidChangeTreeData.dispose();
  }
}
```

- [ ] **Step 5.2: Register the tree provider in `extension.ts`**

Replace the entire contents of `surfaces/vscode-extension/src/extension.ts`:

```typescript
// surfaces/vscode-extension/src/extension.ts
import * as vscode from "vscode";
import { registerTriggerScanCommand } from "./commands/triggerScan";
import { FindingsTreeProvider } from "./providers/FindingsTreeProvider";

let _disposables: vscode.Disposable[] = [];

export function activate(context: vscode.ExtensionContext): void {
  function getApiBase(): string {
    return (
      vscode.workspace
        .getConfiguration("argus")
        .get<string>("apiBase") ?? "http://localhost:8000"
    );
  }

  const treeProvider = new FindingsTreeProvider(getApiBase);
  treeProvider.startPolling();

  const treeView = vscode.window.createTreeView("argus.findingsView", {
    treeDataProvider: treeProvider,
    showCollapseAll: true,
  });

  const refreshCmd = vscode.commands.registerCommand(
    "argus.refreshFindings",
    () => void treeProvider.refresh()
  );

  _disposables.push(
    registerTriggerScanCommand(context),
    treeView,
    treeProvider,
    refreshCmd
  );

  context.subscriptions.push(..._disposables);
}

export function deactivate(): void {
  for (const d of _disposables) {
    d.dispose();
  }
  _disposables = [];
}
```

- [ ] **Step 5.3: Verify the extension builds**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/vscode-extension
npm run build
```

Expected: no TypeScript errors, `out/extension.js` updated.

- [ ] **Step 5.4: Commit**

```bash
git add surfaces/vscode-extension/src/providers/FindingsTreeProvider.ts surfaces/vscode-extension/src/extension.ts
git commit -m "feat(vscode): add FindingsTreeProvider with 5s live polling and per-scan findings tree"
```

---

## Task 6: Extension `FindingCodeLensProvider`

**Files:**
- Create: `surfaces/vscode-extension/src/providers/FindingCodeLensProvider.ts`
- Modify: `surfaces/vscode-extension/src/extension.ts`

**Interfaces:**
- Consumes: `FindingDTO` (same shape as Task 5 — `{ location: { file, line_start }, rule_id, severity }`)
- Produces: `FindingCodeLensProvider` implementing `vscode.CodeLensProvider`; shows a lens on each line that has a finding; lens command opens a detail message

- [ ] **Step 6.1: Create `src/providers/FindingCodeLensProvider.ts`**

```typescript
// surfaces/vscode-extension/src/providers/FindingCodeLensProvider.ts
import * as vscode from "vscode";

interface FindingDTO {
  id: string;
  rule_id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  location: { file: string; line_start: number; line_end: number };
  explanation: string | null;
  cwe: string | null;
}

const SEVERITY_EMOJI: Record<string, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🔵",
  info: "⚪",
};

export class FindingCodeLensProvider implements vscode.CodeLensProvider {
  private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

  // findings keyed by absolute file path
  private _findingsByFile: Map<string, FindingDTO[]> = new Map();

  updateFindings(findings: FindingDTO[]): void {
    this._findingsByFile.clear();
    for (const f of findings) {
      const key = f.location.file;
      const bucket = this._findingsByFile.get(key) ?? [];
      bucket.push(f);
      this._findingsByFile.set(key, bucket);
    }
    this._onDidChangeCodeLenses.fire();
  }

  provideCodeLenses(
    document: vscode.TextDocument
  ): vscode.CodeLens[] {
    const docPath = document.uri.fsPath;
    const findings = this._findingsByFile.get(docPath) ?? [];

    return findings.map((f) => {
      const line = Math.max(0, f.location.line_start - 1);
      const range = new vscode.Range(
        new vscode.Position(line, 0),
        new vscode.Position(line, 0)
      );
      const emoji = SEVERITY_EMOJI[f.severity] ?? "⚪";
      const label = `${emoji} Argus [${f.severity.toUpperCase()}]: ${f.rule_id}${f.cwe ? ` (${f.cwe})` : ""}`;
      return new vscode.CodeLens(range, {
        title: label,
        command: "argus.showFindingDetail",
        arguments: [f],
      });
    });
  }

  dispose(): void {
    this._onDidChangeCodeLenses.dispose();
  }
}
```

- [ ] **Step 6.2: Update `extension.ts` to register the CodeLens provider and `showFindingDetail` command**

Replace the entire contents of `surfaces/vscode-extension/src/extension.ts`:

```typescript
// surfaces/vscode-extension/src/extension.ts
import * as vscode from "vscode";
import { registerTriggerScanCommand } from "./commands/triggerScan";
import { FindingsTreeProvider } from "./providers/FindingsTreeProvider";
import { FindingCodeLensProvider } from "./providers/FindingCodeLensProvider";

interface FindingDTO {
  id: string;
  rule_id: string;
  severity: string;
  location: { file: string; line_start: number; line_end: number };
  explanation: string | null;
  cwe: string | null;
}

let _disposables: vscode.Disposable[] = [];

export function activate(context: vscode.ExtensionContext): void {
  function getApiBase(): string {
    return (
      vscode.workspace
        .getConfiguration("argus")
        .get<string>("apiBase") ?? "http://localhost:8000"
    );
  }

  // Tree provider
  const treeProvider = new FindingsTreeProvider(getApiBase);
  treeProvider.startPolling();

  // CodeLens provider
  const codeLensProvider = new FindingCodeLensProvider();
  const codeLensDisposable = vscode.languages.registerCodeLensProvider(
    { scheme: "file" },
    codeLensProvider
  );

  const treeView = vscode.window.createTreeView("argus.findingsView", {
    treeDataProvider: treeProvider,
    showCollapseAll: true,
  });

  const refreshCmd = vscode.commands.registerCommand(
    "argus.refreshFindings",
    async () => {
      await treeProvider.refresh();
      // Also refresh CodeLens for the active editor
      if (vscode.window.activeTextEditor) {
        const apiBase = getApiBase();
        const scansRes = await fetch(`${apiBase}/api/v1/scans/`);
        if (scansRes.ok) {
          const scans = (await scansRes.json()) as Array<{
            id: string;
            status: string;
          }>;
          const completed = scans.filter((s) => s.status === "completed");
          const allFindings: FindingDTO[] = [];
          for (const s of completed.slice(0, 1)) {
            const fRes = await fetch(
              `${apiBase}/api/v1/scans/${s.id}/findings`
            );
            if (fRes.ok) {
              const f = (await fRes.json()) as FindingDTO[];
              allFindings.push(...f);
            }
          }
          codeLensProvider.updateFindings(allFindings);
        }
      }
    }
  );

  const showDetailCmd = vscode.commands.registerCommand(
    "argus.showFindingDetail",
    (finding: FindingDTO) => {
      const msg = [
        `Rule: ${finding.rule_id}`,
        `Severity: ${finding.severity.toUpperCase()}`,
        finding.cwe ? `CWE: ${finding.cwe}` : null,
        finding.explanation ? `\n${finding.explanation}` : null,
      ]
        .filter(Boolean)
        .join("\n");
      vscode.window.showInformationMessage(msg, { modal: false });
    }
  );

  _disposables.push(
    registerTriggerScanCommand(context),
    treeView,
    treeProvider,
    codeLensProvider,
    codeLensDisposable,
    refreshCmd,
    showDetailCmd
  );

  context.subscriptions.push(..._disposables);
}

export function deactivate(): void {
  for (const d of _disposables) {
    d.dispose();
  }
  _disposables = [];
}
```

- [ ] **Step 6.3: Verify the extension builds**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/vscode-extension
npm run build
```

Expected: no TypeScript errors, `out/extension.js` updated.

- [ ] **Step 6.4: Commit**

```bash
git add surfaces/vscode-extension/src/providers/FindingCodeLensProvider.ts surfaces/vscode-extension/src/extension.ts
git commit -m "feat(vscode): add FindingCodeLensProvider showing severity badge on each finding's source line"
```

---

## Task 7: Real-time Diff Mode

**Files:**
- Create: `core/understanding/diff.py`
- Modify: `core/agents/orchestrator.py`
- Create: `tests/core/understanding/test_diff.py`

**Interfaces:**
- Produces: `compute_diff_files(repo_path: str, base_ref: str = "HEAD~1") -> list[str]` — returns list of absolute file paths changed vs `base_ref`
- Produces: `Orchestrator.run()` passes `diff_files` key in `AgentContext.extra` when `scan.mode == ScanMode.real_time`; scanner agents receive `diff_files` and only scan those files

- [ ] **Step 7.1: Create `core/understanding/__init__.py`** (if it doesn't exist)

```bash
touch /Users/rajat.a.ahuja/Dev/Argus/core/understanding/__init__.py
```

- [ ] **Step 7.2: Write failing tests for `diff.py`**

```python
# tests/core/understanding/test_diff.py
from __future__ import annotations
import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from core.understanding.diff import compute_diff_files


@pytest.fixture
def git_repo_with_changes(tmp_path: Path) -> Path:
    """Create a temporary git repo with one committed file and one modified file."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    # First commit: one file
    initial = tmp_path / "app.py"
    initial.write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    # Second commit: modify file + add new file
    initial.write_text("x = 2\n")
    new_file = tmp_path / "utils.py"
    new_file.write_text("def foo(): pass\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "second"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    return tmp_path


def test_compute_diff_files_returns_changed_files(git_repo_with_changes: Path):
    files = compute_diff_files(str(git_repo_with_changes), base_ref="HEAD~1")
    assert isinstance(files, list)
    # Both modified app.py and new utils.py should appear
    basenames = [os.path.basename(f) for f in files]
    assert "app.py" in basenames
    assert "utils.py" in basenames


def test_compute_diff_files_returns_absolute_paths(git_repo_with_changes: Path):
    files = compute_diff_files(str(git_repo_with_changes), base_ref="HEAD~1")
    for f in files:
        assert os.path.isabs(f), f"Expected absolute path, got: {f}"


def test_compute_diff_files_only_python_files(git_repo_with_changes: Path):
    """Adds a markdown file; it should still appear in diff but only .py extensions when filtered."""
    md = git_repo_with_changes / "README.md"
    md.write_text("# readme\n")
    subprocess.run(["git", "add", "."], cwd=git_repo_with_changes, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add readme"],
        cwd=git_repo_with_changes, check=True, capture_output=True,
    )
    files = compute_diff_files(str(git_repo_with_changes), base_ref="HEAD~1")
    # README.md is a changed file and should be included
    basenames = [os.path.basename(f) for f in files]
    assert "README.md" in basenames


def test_compute_diff_files_empty_on_no_changes(tmp_path: Path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    f = tmp_path / "x.py"
    f.write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "only"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    # HEAD~1 does not exist — should return empty list rather than raise
    files = compute_diff_files(str(tmp_path), base_ref="HEAD~1")
    assert files == []
```

- [ ] **Step 7.3: Run tests to verify they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/understanding/test_diff.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.understanding.diff'`

- [ ] **Step 7.4: Implement `core/understanding/diff.py`**

```python
# core/understanding/diff.py
from __future__ import annotations
import subprocess
from pathlib import Path


def compute_diff_files(repo_path: str, base_ref: str = "HEAD~1") -> list[str]:
    """Return absolute paths of files changed between *base_ref* and HEAD.

    Returns an empty list if *base_ref* does not exist (e.g. single-commit repo)
    or if *repo_path* is not a git repository.
    """
    root = Path(repo_path).resolve()
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # base_ref does not exist, not a git repo, or other git error
        return []

    paths: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            abs_path = str(root / line)
            paths.append(abs_path)
    return paths
```

- [ ] **Step 7.5: Create `tests/core/understanding/__init__.py`**

```bash
mkdir -p /Users/rajat.a.ahuja/Dev/Argus/tests/core/understanding
touch /Users/rajat.a.ahuja/Dev/Argus/tests/core/understanding/__init__.py
```

- [ ] **Step 7.6: Run tests to verify they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/understanding/test_diff.py -v
```

Expected:
```
PASSED tests/core/understanding/test_diff.py::test_compute_diff_files_returns_changed_files
PASSED tests/core/understanding/test_diff.py::test_compute_diff_files_returns_absolute_paths
PASSED tests/core/understanding/test_diff.py::test_compute_diff_files_only_python_files
PASSED tests/core/understanding/test_diff.py::test_compute_diff_files_empty_on_no_changes
4 passed in ...
```

- [ ] **Step 7.7: Wire diff mode into the orchestrator**

In `core/agents/orchestrator.py`, add the following import at the top of the file (after existing imports):

```python
from core.model.entities import ScanMode
```

Then, in the `run` method, add diff file computation immediately after the `execution_order = self._topological_sort()` line and before the agent loop:

```python
        # --- real_time mode: compute changed files and restrict scanners ---
        diff_files: list[str] | None = None
        if scan.mode == ScanMode.real_time:
            from core.understanding.diff import compute_diff_files
            diff_files = compute_diff_files(scan.target_ref)
            log.info("real_time_diff", file_count=len(diff_files), scan_id=str(scan.id))
```

Then, in `_build_extra`, add `diff_files` to the extra dict when present. Replace the `_build_extra` method with:

```python
    def _build_extra(self, node_id: str, state: dict[str, AgentOutput], diff_files: list[str] | None = None) -> dict:
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
        # real_time diff mode: pass restricted file list to scanner agents
        if diff_files is not None:
            extra["diff_files"] = diff_files
        return extra
```

And update the call site inside `run` to pass `diff_files`:

```python
            extra = self._build_extra(node_id, state, diff_files=diff_files)
```

- [ ] **Step 7.8: Run orchestrator lifecycle tests to confirm no regressions**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/core/agents/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 7.9: Commit**

```bash
git add core/understanding/__init__.py core/understanding/diff.py core/agents/orchestrator.py tests/core/understanding/__init__.py tests/core/understanding/test_diff.py
git commit -m "feat: add real-time diff mode — compute_diff_files util and orchestrator fast-path passing diff_files to scanners"
```

---

## Task 8: CI Step

**Files:**
- Create: `surfaces/ci/argus-scan.sh`
- Create: `surfaces/ci/action.yml`

**Interfaces:**
- `argus-scan.sh` env vars: `ARGUS_API_BASE` (default `http://localhost:8000`), `ARGUS_TARGET_REF` (required), `ARGUS_PIPELINE` (default `full-scan`), `ARGUS_MODE` (default `at_rest`), `ARGUS_FAIL_ON` (default `critical,high`), `ARGUS_TIMEOUT` (default `300`)
- Exit codes: `0` on success (no matching findings), `1` on critical/high findings or scan failure, `2` on timeout

- [ ] **Step 8.1: Create `surfaces/ci/` directory**

```bash
mkdir -p /Users/rajat.a.ahuja/Dev/Argus/surfaces/ci
```

- [ ] **Step 8.2: Create `surfaces/ci/argus-scan.sh`**

```bash
#!/usr/bin/env bash
# surfaces/ci/argus-scan.sh
# Trigger an Argus scan, poll for completion, exit non-zero on critical/high findings.
#
# Env vars:
#   ARGUS_API_BASE    Base URL of the Argus API  (default: http://localhost:8000)
#   ARGUS_TARGET_REF  Repository path or ref      (required)
#   ARGUS_PIPELINE    Pipeline config name        (default: full-scan)
#   ARGUS_MODE        Scan mode                   (default: at_rest)
#   ARGUS_FAIL_ON     Comma-separated severities  (default: critical,high)
#   ARGUS_TIMEOUT     Max seconds to wait         (default: 300)
#
# Exit codes:
#   0  Success — scan completed, no matching findings
#   1  Failure — scan failed, timed out, or findings matched ARGUS_FAIL_ON
#   2  Configuration error

set -euo pipefail

ARGUS_API_BASE="${ARGUS_API_BASE:-http://localhost:8000}"
ARGUS_PIPELINE="${ARGUS_PIPELINE:-full-scan}"
ARGUS_MODE="${ARGUS_MODE:-at_rest}"
ARGUS_FAIL_ON="${ARGUS_FAIL_ON:-critical,high}"
ARGUS_TIMEOUT="${ARGUS_TIMEOUT:-300}"

if [[ -z "${ARGUS_TARGET_REF:-}" ]]; then
  echo "ERROR: ARGUS_TARGET_REF is required" >&2
  exit 2
fi

if ! command -v curl &>/dev/null; then
  echo "ERROR: curl is required but not found" >&2
  exit 2
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required but not found" >&2
  exit 2
fi

echo "==> Triggering Argus scan"
echo "    Target:   ${ARGUS_TARGET_REF}"
echo "    Pipeline: ${ARGUS_PIPELINE}"
echo "    Mode:     ${ARGUS_MODE}"
echo "    Fail on:  ${ARGUS_FAIL_ON}"

TRIGGER_RESP=$(curl -sf \
  -X POST "${ARGUS_API_BASE}/api/v1/scans/" \
  -H "Content-Type: application/json" \
  -d "{
    \"target_ref\": \"${ARGUS_TARGET_REF}\",
    \"mode\": \"${ARGUS_MODE}\",
    \"approach\": \"penetration_testing\",
    \"pipeline_config_name\": \"${ARGUS_PIPELINE}\"
  }" 2>&1) || {
  echo "ERROR: Failed to trigger scan — ${TRIGGER_RESP}" >&2
  exit 1
}

SCAN_ID=$(echo "${TRIGGER_RESP}" | jq -r '.scan_id')
if [[ -z "${SCAN_ID}" || "${SCAN_ID}" == "null" ]]; then
  echo "ERROR: Could not parse scan_id from response: ${TRIGGER_RESP}" >&2
  exit 1
fi

echo "==> Scan started: ${SCAN_ID}"

# Poll for completion
DEADLINE=$(( $(date +%s) + ARGUS_TIMEOUT ))
SLEEP_INTERVAL=5

while true; do
  NOW=$(date +%s)
  if (( NOW >= DEADLINE )); then
    echo "ERROR: Timed out after ${ARGUS_TIMEOUT}s waiting for scan ${SCAN_ID}" >&2
    exit 1
  fi

  STATUS_RESP=$(curl -sf "${ARGUS_API_BASE}/api/v1/scans/${SCAN_ID}" 2>&1) || {
    echo "WARN: Failed to poll scan status — retrying" >&2
    sleep "${SLEEP_INTERVAL}"
    continue
  }

  STATUS=$(echo "${STATUS_RESP}" | jq -r '.status')
  echo "    status: ${STATUS}"

  case "${STATUS}" in
    completed)
      echo "==> Scan completed"
      break
      ;;
    failed|cancelled)
      echo "ERROR: Scan ended with status '${STATUS}'" >&2
      exit 1
      ;;
    pending|running)
      sleep "${SLEEP_INTERVAL}"
      ;;
    *)
      echo "WARN: Unknown status '${STATUS}' — retrying" >&2
      sleep "${SLEEP_INTERVAL}"
      ;;
  esac
done

# Fetch findings and check severities
echo "==> Fetching findings"
FINDINGS_RESP=$(curl -sf \
  "${ARGUS_API_BASE}/api/v1/scans/${SCAN_ID}/findings" 2>&1) || {
  echo "ERROR: Failed to fetch findings — ${FINDINGS_RESP}" >&2
  exit 1
}

TOTAL=$(echo "${FINDINGS_RESP}" | jq 'length')
echo "    Total findings: ${TOTAL}"

# Build jq filter from ARGUS_FAIL_ON comma list
JQ_SEVERITIES=$(echo "${ARGUS_FAIL_ON}" | tr ',' '\n' | jq -Rr '. | @json' | paste -sd',' -)
MATCH_COUNT=$(echo "${FINDINGS_RESP}" | jq "[.[] | select(.severity | IN(${JQ_SEVERITIES}))] | length")

if (( MATCH_COUNT > 0 )); then
  echo "FAIL: Found ${MATCH_COUNT} finding(s) with severity in [${ARGUS_FAIL_ON}]" >&2

  # Print a summary table
  echo ""
  echo "  Severity  Rule                                    File"
  echo "  --------  --------------------------------------  ----"
  echo "${FINDINGS_RESP}" | jq -r \
    ".[] | select(.severity | IN(${JQ_SEVERITIES})) | \"  \(.severity | ascii_upcase | .[0:8])  \(.rule_id | .[0:38])  \(.location.file):\(.location.line_start)\""
  echo ""
  exit 1
fi

echo "PASS: No findings matching [${ARGUS_FAIL_ON}] — scan clean"
exit 0
```

Save to: `surfaces/ci/argus-scan.sh`

- [ ] **Step 8.3: Make the script executable**

```bash
chmod +x /Users/rajat.a.ahuja/Dev/Argus/surfaces/ci/argus-scan.sh
```

- [ ] **Step 8.4: Create `surfaces/ci/action.yml`**

```yaml
# surfaces/ci/action.yml
# GitHub Actions composite step for Argus security scanning.
#
# Usage in your workflow:
#
#   - uses: ./surfaces/ci
#     with:
#       api-base: http://localhost:8000
#       target-ref: ${{ github.workspace }}
#       pipeline: full-scan
#       mode: at_rest
#       fail-on: critical,high
#       timeout: '300'

name: "Argus Security Scan"
description: "Trigger an Argus scan and fail the job on critical/high findings"

inputs:
  api-base:
    description: "Base URL of the Argus API server"
    required: false
    default: "http://localhost:8000"
  target-ref:
    description: "Repository path or git ref to scan"
    required: true
  pipeline:
    description: "Pipeline config name"
    required: false
    default: "full-scan"
  mode:
    description: "Scan mode (at_rest or real_time)"
    required: false
    default: "at_rest"
  fail-on:
    description: "Comma-separated severity levels that cause the step to fail"
    required: false
    default: "critical,high"
  timeout:
    description: "Maximum seconds to wait for scan completion"
    required: false
    default: "300"

runs:
  using: "composite"
  steps:
    - name: Run Argus scan
      shell: bash
      env:
        ARGUS_API_BASE: ${{ inputs.api-base }}
        ARGUS_TARGET_REF: ${{ inputs.target-ref }}
        ARGUS_PIPELINE: ${{ inputs.pipeline }}
        ARGUS_MODE: ${{ inputs.mode }}
        ARGUS_FAIL_ON: ${{ inputs.fail-on }}
        ARGUS_TIMEOUT: ${{ inputs.timeout }}
      run: ${{ github.action_path }}/argus-scan.sh
```

- [ ] **Step 8.5: Smoke-test the script syntax**

```bash
bash -n /Users/rajat.a.ahuja/Dev/Argus/surfaces/ci/argus-scan.sh
echo "Syntax OK"
```

Expected output:
```
Syntax OK
```

- [ ] **Step 8.6: Commit**

```bash
git add surfaces/ci/argus-scan.sh surfaces/ci/action.yml
git commit -m "feat(ci): add bash scan entrypoint and GitHub Actions composite step with severity gating"
```

---

## Task 9: Dashboard Scan List Polish

**Files:**
- Modify: `surfaces/dashboard/src/api/client.ts`
- Modify: `surfaces/dashboard/src/pages/runs/RunsPage.tsx`

**Interfaces:**
- Consumes: `DELETE /api/v1/scans/{id}` → `{ scan_id: string; status: "cancelled" }`
- Produces: `api.cancelScan(scanId: string): Promise<void>` in client.ts
- Produces: `RunsPage` scan selector shows coloured status badge + cancel button for pending/running scans

- [ ] **Step 9.1: Add `cancelScan` to `surfaces/dashboard/src/api/client.ts`**

Add the following to the `api` object in `client.ts` (after `clonePipeline`):

```typescript
  cancelScan: (scanId: string) =>
    del(`/api/v1/scans/${scanId}`),
  getScan: (scanId: string) =>
    get<ScanDTO>(`/api/v1/scans/${scanId}`),
```

Also, update the `ScanDTO` interface in `client.ts` to include `finished_at`:

```typescript
export interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  approach: SecurityApproach;
  cost_usd: number;
  started_at: string | null;
  finished_at: string | null;
}
```

- [ ] **Step 9.2: Replace `RunsPage.tsx` with the polished version including status badge and cancel button**

Replace the entire contents of `surfaces/dashboard/src/pages/runs/RunsPage.tsx`:

```tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ScanDTO } from "../../api/client";
import { useScanEvents } from "../../hooks/useScanEvents";
import { RunTrace } from "./RunTrace";
import { BudgetGauge } from "./BudgetGauge";

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  pending:   { label: "Pending",   className: "bg-gray-100 text-gray-600 border border-gray-200" },
  running:   { label: "Running",   className: "bg-blue-50 text-blue-700 border border-blue-200 animate-pulse" },
  completed: { label: "Completed", className: "bg-green-50 text-green-700 border border-green-200" },
  failed:    { label: "Failed",    className: "bg-red-50 text-red-700 border border-red-200" },
  cancelled: { label: "Cancelled", className: "bg-amber-50 text-amber-700 border border-amber-200" },
};

function StatusBadge({ status }: { status: string }) {
  const badge = STATUS_BADGE[status] ?? STATUS_BADGE.pending;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold uppercase ${badge.className}`}>
      {status === "running" && (
        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full mr-1.5 animate-pulse" />
      )}
      {badge.label}
    </span>
  );
}

export function RunsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: scans, isLoading } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
    refetchInterval: 5000,
  });
  const { events, connected } = useScanEvents(selectedId);
  const qc = useQueryClient();

  const cancelMutation = useMutation({
    mutationFn: (scanId: string) => api.cancelScan(scanId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scans"] });
    },
  });

  const totalCost = events
    .filter((e) => e.event === "llm_call")
    .reduce((s, e) => s + (e.cost_usd ?? 0), 0);

  const modelCounts: Record<string, number> = {};
  events
    .filter((e) => e.event === "llm_call")
    .forEach((e) => {
      if (e.model_id) modelCounts[e.model_id] = (modelCounts[e.model_id] ?? 0) + 1;
    });

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Live Runs</h1>
          <p className="text-sm text-gray-500 mt-0.5">Real-time pipeline execution trace</p>
        </div>
        {connected && (
          <span className="flex items-center gap-1.5 px-3 py-1 bg-green-50 border border-green-200 rounded-full text-xs font-semibold text-green-700">
            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
            Live
          </span>
        )}
      </div>

      {/* Scan list with status badges and cancel buttons */}
      <div className="bg-white rounded-xl shadow-card overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Scans</span>
          {isLoading && (
            <span className="text-xs text-gray-400">Loading…</span>
          )}
        </div>
        {scans && scans.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-gray-400">No scans yet</div>
        )}
        {scans && scans.map((scan: ScanDTO) => {
          const isActive = selectedId === scan.id;
          const canCancel = scan.status === "pending" || scan.status === "running";
          return (
            <div
              key={scan.id}
              className={`flex items-center gap-3 px-4 py-3 border-b border-gray-50 last:border-0 cursor-pointer transition-colors ${
                isActive ? "bg-accent-50 border-l-[3px] border-l-[#A100FF]" : "hover:bg-gray-50"
              }`}
              style={isActive ? { borderLeft: "3px solid #A100FF" } : undefined}
              onClick={() => setSelectedId(isActive ? null : scan.id)}
            >
              {/* Target ref */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-gray-800 truncate">{scan.target_ref}</p>
                <p className="text-xs text-gray-400 mt-0.5">{scan.mode} · ${scan.cost_usd.toFixed(3)}</p>
              </div>

              {/* Status badge */}
              <StatusBadge status={scan.status} />

              {/* Cancel button — only for pending/running */}
              {canCancel && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm(`Cancel scan of ${scan.target_ref}?`)) {
                      cancelMutation.mutate(scan.id);
                    }
                  }}
                  disabled={cancelMutation.isPending && cancelMutation.variables === scan.id}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-red-600 border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-40 transition-colors"
                  title="Cancel scan"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Cancel
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Main layout — trace + budget gauge */}
      {selectedId && (
        <div className="flex gap-4 items-start">
          <RunTrace events={events} />
          <div className="flex flex-col gap-4 w-52 flex-shrink-0">
            <BudgetGauge usedUsd={totalCost} />
            {Object.entries(modelCounts).length > 0 && (
              <div className="bg-white rounded-xl shadow-card p-4">
                <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-3">Model Calls</p>
                {Object.entries(modelCounts).map(([m, c]) => (
                  <div key={m} className="flex justify-between items-center text-xs py-1 border-b border-gray-50 last:border-0">
                    <span className="font-mono text-gray-600 truncate">{m.split("-").slice(-2).join("-")}</span>
                    <span className="font-bold text-gray-900 ml-2">{c}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 9.3: Verify the TypeScript compiles cleanly**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus/surfaces/dashboard
npx tsc --noEmit
```

Expected output: no errors.

- [ ] **Step 9.4: Run all Python tests to confirm the full suite still passes**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus
python -m pytest tests/ -v --ignore=tests/e2e -q
```

Expected output:
```
... passed, 0 failed
```

- [ ] **Step 9.5: Commit**

```bash
git add surfaces/dashboard/src/api/client.ts surfaces/dashboard/src/pages/runs/RunsPage.tsx
git commit -m "feat(dashboard): add status badges, cancel button, and 5s auto-refresh to scan list in RunsPage"
```

---

## Self-Review Notes

**Spec coverage check:**
- Gap 1 (scan lifecycle) → Task 1 ✓
- Gap 2 (random pipeline_config_id) → Task 1 step 1.4 ✓
- Gap 3 (no cancel endpoint) → Task 2 ✓
- VS Code extension scaffold → Task 3 ✓
- `argus.triggerScan` command → Task 4 ✓
- `FindingsTreeProvider` → Task 5 ✓
- `FindingCodeLensProvider` → Task 6 ✓
- Real-time diff mode → Task 7 ✓
- CI bash entrypoint + GitHub Actions step → Task 8 ✓
- Dashboard scan list polish → Task 9 ✓

**Type consistency check:**
- `FindingDTO` interface defined identically in Tasks 5 and 6 (both have `id`, `rule_id`, `severity`, `location.file`, `location.line_start`, `explanation`, `cwe`) ✓
- `ScanDTO` extended in Task 9 to add `finished_at` ✓
- `compute_diff_files(repo_path: str, base_ref: str) -> list[str]` used consistently in Tasks 7 and the orchestrator ✓
- `AgentContext.extra["diff_files"]` key matches between `_build_extra` update and the real_time branch ✓
- `cancelScan` uses `del()` which returns `Promise<void>` — `api.cancelScan` signature matches ✓
