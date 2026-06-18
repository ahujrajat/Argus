# core/scanners/zap.py
from __future__ import annotations
import json
import subprocess
import os
import tempfile
import structlog
from pathlib import Path
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Finding, Severity, Location

log = structlog.get_logger()

ZAP_BIN = os.environ.get("ZAP_BIN", "zap.sh")
ZAP_TIMEOUT = int(os.environ.get("ZAP_TIMEOUT", "600"))

_RISK_MAP: dict[str, Severity] = {
    "3": Severity.high,
    "2": Severity.medium,
    "1": Severity.low,
    "0": Severity.info,
    "high": Severity.high,
    "medium": Severity.medium,
    "low": Severity.low,
    "informational": Severity.info,
}

# ZAP alert references map alert IDs to OWASP categories
_ALERT_OWASP: dict[str, str] = {
    "40012": "A03:2021",  # Cross Site Scripting (Reflected)
    "40014": "A03:2021",  # Cross Site Scripting (Persistent)
    "40016": "A03:2021",  # Cross Site Scripting (Persistent) - Prime
    "40017": "A03:2021",  # Cross Site Scripting (Persistent) - Spider
    "40018": "A03:2021",  # SQL Injection
    "40019": "A03:2021",  # SQL Injection - MySQL
    "40020": "A03:2021",  # SQL Injection - Hypersonic SQL
    "40021": "A03:2021",  # SQL Injection - Oracle
    "40022": "A03:2021",  # SQL Injection - PostgreSQL
    "40024": "A03:2021",  # SQL Injection - SQLite
    "40026": "A03:2021",  # Cross Site Scripting (DOM Based)
    "40042": "A03:2021",  # Spring4Shell
    "6": "A05:2021",      # Path Traversal
    "7": "A05:2021",      # Remote File Inclusion
    "10202": "A09:2021",  # Absence of Anti-CSRF Tokens
    "10010": "A02:2021",  # Cookie No HttpOnly Flag
    "10011": "A02:2021",  # Cookie Without Secure Flag
    "10038": "A05:2021",  # Content Security Policy (CSP) Header Not Set
    "10054": "A01:2021",  # Cookie Without SameSite Attribute
    "10056": "A05:2021",  # X-Debug-Token Information Leak
    "10096": "A02:2021",  # Timestamp Disclosure
    "90027": "A10:2021",  # SSRF
    "90028": "A01:2021",  # Insecure HTTP Method
}

_DEFAULT_OWASP = "A06:2021"


class ZAPAdapter:
    agent_id = "dast_zap"

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        if not ctx.extra.get("dast_authorized", False):
            log.warning(
                "dast_unauthorized_scan_blocked",
                agent=self.agent_id,
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

        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "zap-report.json"
            cmd = [
                ZAP_BIN,
                "-cmd",
                "-quickurl", target,
                "-quickprogress",
                "-quickout", str(report_path),
            ]

            log.info("zap_scan_start", target=target, scan_id=str(ctx.scan.id))

            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=ZAP_TIMEOUT,
                )
            except FileNotFoundError:
                log.warning("zap_not_found")
                return AgentOutput(
                    agent_id=self.agent_id,
                    data={"findings": []},
                    cost_usd=0.0,
                    skipped=True,
                    skip_reason="zap_not_installed",
                )
            except subprocess.TimeoutExpired:
                log.error("zap_timeout", target=target)
                return AgentOutput(
                    agent_id=self.agent_id,
                    data={"findings": []},
                    cost_usd=0.0,
                    skipped=True,
                    skip_reason="zap_timeout",
                )

            findings = self._parse_report(report_path, ctx)

        log.info("zap_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"findings": [f.model_dump(mode="json") for f in findings]},
            cost_usd=0.0,
        )

    def _parse_report(self, report_path: Path, ctx: AgentContext) -> list[Finding]:
        findings: list[Finding] = []

        try:
            raw = json.loads(report_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return findings

        # ZAP JSON report: {"site": [{"alerts": [...]}]} or flat list
        sites = raw.get("site", [])
        if not sites and isinstance(raw, list):
            sites = raw

        for site in (sites if isinstance(sites, list) else [sites]):
            for alert in site.get("alerts", []):
                for instance in alert.get("instances", [{"uri": site.get("@name", ctx.scan.target_ref), "method": "GET"}]):
                    finding = self._map_alert(alert, instance, ctx)
                    if finding:
                        findings.append(finding)

        return findings

    def _map_alert(self, alert: dict, instance: dict, ctx: AgentContext) -> Finding | None:
        alert_id = str(alert.get("pluginid", alert.get("alertRef", "0")))
        name = alert.get("alert", alert.get("name", "unknown"))
        risk_str = str(alert.get("riskcode", alert.get("riskdesc", "0"))).lower()

        severity = _RISK_MAP.get(risk_str, Severity.info)
        # riskdesc is like "High (3)" — extract leading word
        if " " in risk_str:
            severity = _RISK_MAP.get(risk_str.split()[0], severity)

        owasp = _ALERT_OWASP.get(alert_id, _DEFAULT_OWASP)

        uri = instance.get("uri", ctx.scan.target_ref)
        method = instance.get("method", "GET")
        evidence = instance.get("evidence", "")
        description = alert.get("desc", "")

        dedup_key = f"zap:{alert_id}:{uri}:{method}"

        return Finding(
            scan_id=ctx.scan.id,
            rule_id=f"zap-{alert_id}",
            source_tool="zap",
            cwe=f"CWE-{alert.get('cweid', 0)}" if alert.get("cweid") else None,
            owasp_category=owasp,
            severity=severity,
            confidence=0.8,
            location=Location(
                file=uri,
                line_start=0,
                line_end=0,
                snippet=evidence or description[:200],
            ),
            dedup_key=dedup_key,
            explanation=name,
        )
