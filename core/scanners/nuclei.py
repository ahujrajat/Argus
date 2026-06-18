# core/scanners/nuclei.py
from __future__ import annotations
import json
import subprocess
import os
import tempfile
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Finding, Severity, Location

log = structlog.get_logger()

NUCLEI_BIN = os.environ.get("NUCLEI_BIN", "nuclei")
NUCLEI_TIMEOUT = int(os.environ.get("NUCLEI_TIMEOUT", "300"))

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.critical,
    "high": Severity.high,
    "medium": Severity.medium,
    "low": Severity.low,
    "info": Severity.info,
    "unknown": Severity.info,
}

# Map common Nuclei template tags to OWASP categories
_TAG_OWASP: dict[str, str] = {
    "sqli": "A03:2021",
    "xss": "A03:2021",
    "rce": "A03:2021",
    "injection": "A03:2021",
    "ssrf": "A10:2021",
    "lfi": "A01:2021",
    "path-traversal": "A01:2021",
    "auth-bypass": "A01:2021",
    "misconfig": "A05:2021",
    "exposure": "A02:2021",
    "xxe": "A05:2021",
    "idor": "A01:2021",
    "redirect": "A01:2021",
}


class NucleiAdapter:
    agent_id = "dast_nuclei"

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        if not ctx.extra.get("dast_authorized", False):
            log.warning(
                "dast_unauthorized_scan_blocked",
                target=ctx.scan.target_ref,
                scan_id=str(ctx.scan.id),
            )
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": []},
                cost_usd=0.0,
                skipped=True,
                skip_reason="no_dast_authorization",
            )

        target = ctx.scan.target_ref

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            output_path = tmp.name

        cmd = [
            NUCLEI_BIN,
            "-u", target,
            "-j",
            "-o", output_path,
            "-silent",
        ]

        log.info("nuclei_scan_start", target=target, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=NUCLEI_TIMEOUT,
            )
        except FileNotFoundError:
            log.warning("nuclei_not_found")
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": []},
                cost_usd=0.0,
                skipped=True,
                skip_reason="nuclei_not_installed",
            )
        except subprocess.TimeoutExpired:
            log.error("nuclei_timeout", target=target)
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": []},
                cost_usd=0.0,
                skipped=True,
                skip_reason="nuclei_timeout",
            )
        finally:
            pass

        findings = self._parse_output(output_path, ctx)
        try:
            os.unlink(output_path)
        except FileNotFoundError:
            pass

        log.info("nuclei_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"findings": [f.model_dump(mode="json") for f in findings]},
            cost_usd=0.0,
        )

    def _parse_output(self, output_path: str, ctx: AgentContext) -> list[Finding]:
        findings: list[Finding] = []

        try:
            with open(output_path) as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            return findings

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            finding = self._map_event(event, ctx)
            if finding:
                findings.append(finding)

        return findings

    def _map_event(self, event: dict, ctx: AgentContext) -> Finding | None:
        template_id = event.get("template-id", "unknown")
        info = event.get("info", {})
        severity_str = info.get("severity", "info").lower()
        severity = _SEVERITY_MAP.get(severity_str, Severity.info)

        tags: list[str] = info.get("tags", [])
        owasp = next((
            _TAG_OWASP[t] for t in tags if t.lower() in _TAG_OWASP
        ), "A06:2021")

        cve_ids: list[str] = info.get("classification", {}).get("cve-id", [])
        cve = cve_ids[0] if cve_ids else None

        matched_at = event.get("matched-at") or event.get("host", ctx.scan.target_ref)
        host = event.get("host", ctx.scan.target_ref)
        check_name = info.get("name", template_id)

        dedup_key = f"nuclei:{template_id}:{matched_at}"

        return Finding(
            scan_id=ctx.scan.id,
            rule_id=template_id,
            source_tool="nuclei",
            cwe=cve,
            owasp_category=owasp,
            severity=severity,
            confidence=0.85,
            location=Location(
                file=host,
                line_start=0,
                line_end=0,
                snippet=matched_at,
            ),
            dedup_key=dedup_key,
            explanation=check_name,
        )
