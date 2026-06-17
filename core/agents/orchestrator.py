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
