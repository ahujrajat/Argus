# core/scanners/grype.py
from __future__ import annotations
import json
import subprocess
import os
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Finding, Severity, Location

log = structlog.get_logger()

GRYPE_BIN = os.environ.get("GRYPE_BIN", "grype")
GRYPE_TIMEOUT = int(os.environ.get("GRYPE_TIMEOUT", "180"))

_SEVERITY_MAP: dict[str, Severity] = {
    "Critical": Severity.critical,
    "High": Severity.high,
    "Medium": Severity.medium,
    "Low": Severity.low,
    "Negligible": Severity.info,
    "Unknown": Severity.info,
}


class GrypeAdapter:
    agent_id = "sca_grype"

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        root = ctx.scan.target_ref

        cmd = [GRYPE_BIN, root, "--output", "json"]

        log.info("grype_scan_start", root=root, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=GRYPE_TIMEOUT,
            )
        except FileNotFoundError:
            log.warning("grype_not_found")
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": [], "sbom": {}},
                cost_usd=0.0,
                skipped=True,
                skip_reason="grype_not_installed",
            )
        except subprocess.TimeoutExpired:
            log.error("grype_timeout", root=root)
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": [], "sbom": {}},
                cost_usd=0.0,
                skipped=True,
                skip_reason="grype_timeout",
            )

        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            log.error("grype_parse_error", returncode=proc.returncode, stderr=proc.stderr[:200])
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": [], "sbom": {}},
                cost_usd=0.0,
                skipped=True,
                skip_reason="grype_parse_error",
            )

        findings = self._parse_matches(report, ctx)
        log.info("grype_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={
                "findings": [f.model_dump(mode="json") for f in findings],
                "sbom": report.get("source", {}),
            },
            cost_usd=0.0,
        )

    def _parse_matches(self, report: dict, ctx: AgentContext) -> list[Finding]:
        findings: list[Finding] = []

        for match in report.get("matches", []):
            vuln = match.get("vulnerability", {})
            artifact = match.get("artifact", {})

            cve_id = vuln.get("id", "unknown")
            severity_str = vuln.get("severity", "Unknown")
            severity = _SEVERITY_MAP.get(severity_str, Severity.info)

            pkg_name = artifact.get("name", "unknown")
            pkg_version = artifact.get("version", "unknown")
            pkg_language = artifact.get("language", "unknown")

            locations = artifact.get("locations", [])
            file_path = locations[0].get("realPath", ctx.scan.target_ref) if locations else ctx.scan.target_ref

            cvss_list = vuln.get("cvss", [])
            cvss3 = next((c for c in cvss_list if c.get("version", "").startswith("3")), None)
            base_score: float = 0.0
            if cvss3 and "metrics" in cvss3:
                base_score = float(cvss3["metrics"].get("baseScore", 0.0))
            confidence = min(base_score / 10.0, 1.0) if base_score else 0.5

            finding = Finding(
                scan_id=ctx.scan.id,
                rule_id=cve_id,
                source_tool="grype",
                cwe=None,
                owasp_category="A06:2021",
                severity=severity,
                confidence=confidence,
                location=Location(
                    file=file_path,
                    line_start=0,
                    line_end=0,
                    snippet=f"{pkg_name}@{pkg_version} ({pkg_language})",
                ),
                dedup_key=f"grype:{cve_id}:{pkg_name}:{pkg_version}",
                explanation=vuln.get("description"),
            )
            findings.append(finding)

        return findings
