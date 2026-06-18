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
from core.agents.fix import FixAgent
from core.agents.pattern import PatternAgent
from core.scanners.nuclei import NucleiAdapter
from core.scanners.zap import ZAPAdapter
from core.scanners.semgrep import SemgrepAdapter
from core.scanners.trufflehog import TruffleHogAdapter
from core.scanners.grype import GrypeAdapter
from core.scanners.checkov import CheckovAdapter
from core.governance.gate import GovernanceGate
from core.governance.events import event_bus
from core.governance.ledger import CostLedger
from core.model.entities import (
    Scan, ScanStatus, CostLedgerEntry, ModelTier, AuditLogEntry, ScanMode,
)
from core.understanding.diff import compute_diff_files
from core.db.tables import ScanRow, FindingRow, FixRow, AuditLogEntryRow

log = structlog.get_logger()

_AGENT_REGISTRY: dict[str, type] = {
    "IngestionAgent": IngestionAgent,
    "SemgrepAdapter": SemgrepAdapter,
    "TruffleHogAdapter": TruffleHogAdapter,
    "GrypeAdapter": GrypeAdapter,
    "CheckovAdapter": CheckovAdapter,
    "TriageAgent": TriageAgent,
    "ExplainerAgent": ExplainerAgent,
    "FixAgent": FixAgent,
    "PatternAgent": PatternAgent,
    "NucleiAdapter": NucleiAdapter,
    "ZAPAdapter": ZAPAdapter,
}

_SCANNER_AGENTS = {"SemgrepAdapter", "TruffleHogAdapter", "GrypeAdapter", "CheckovAdapter", "NucleiAdapter", "ZAPAdapter"}
_DAST_AGENTS = {"NucleiAdapter", "ZAPAdapter"}


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

        # Compute diff files for real-time mode; scanners receive them via extra
        diff_files: list[str] = []
        if scan.mode == ScanMode.real_time and scan.target_ref.startswith("/"):
            diff_files = compute_diff_files(scan.target_ref)
            log.info("real_time_diff", file_count=len(diff_files), scan_id=str(scan.id))

        execution_order = self._topological_sort()

        # Pre-flight DAST authorization check
        dast_authorized = False
        dast_nodes = [nid for nid, n in self._nodes.items() if n.get("agent") in _DAST_AGENTS]
        if dast_nodes:
            from core.db.tables import TargetAuthorizationRow as _TAR
            auth_res = await session.execute(
                _select(_TAR).where(_TAR.target == scan.target_ref)
            )
            auth_row = auth_res.scalar_one_or_none()
            if auth_row:
                expired = (
                    auth_row.expires_at is not None
                    and auth_row.expires_at < datetime.now(timezone.utc)
                )
                dast_authorized = not expired
                if dast_authorized:
                    log.info("dast_authorized", target=scan.target_ref, auth_id=auth_row.id)
                else:
                    log.warning("dast_authorization_expired", target=scan.target_ref)
            else:
                log.warning("dast_no_authorization", target=scan.target_ref)

        try:
            for node_id in execution_order:
                node = self._nodes[node_id]
                agent_cls = _AGENT_REGISTRY.get(node["agent"])
                if not agent_cls:
                    log.warning("unknown_agent", agent=node["agent"])
                    continue

                tier = ModelTier(node.get("tier", "balanced")) if node.get("tier") != "none" else ModelTier.none

                # Build context with outputs from predecessor nodes
                extra = self._build_extra(node_id, state)
                if diff_files:
                    extra["diff_files"] = diff_files
                if node.get("agent") in _DAST_AGENTS:
                    extra["dast_authorized"] = dast_authorized

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
        # Pass triage output to explainer and fix_generation
        if "triage" in state:
            extra["triaged_findings"] = state["triage"].data.get("triaged_findings", [])
        # Pass explainer output to fix_generation
        if "explainer" in state:
            extra["explained_findings"] = state["explainer"].data.get("explained_findings", [])
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

    def _collect_fixes(self, state: dict[str, AgentOutput]) -> list[dict]:
        if "fix_generation" in state:
            return state["fix_generation"].data.get("fixes", [])
        return []

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
