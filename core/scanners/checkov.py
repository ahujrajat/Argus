# core/scanners/checkov.py
from __future__ import annotations
import json
import subprocess
import os
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Finding, Severity, Location

log = structlog.get_logger()

CHECKOV_BIN = os.environ.get("CHECKOV_BIN", "checkov")
CHECKOV_TIMEOUT = int(os.environ.get("CHECKOV_TIMEOUT", "120"))

_SEVERITY_MAP: dict[str, Severity] = {
    "CRITICAL": Severity.critical,
    "HIGH": Severity.high,
    "MEDIUM": Severity.medium,
    "LOW": Severity.low,
    "INFO": Severity.info,
}


class CheckovAdapter:
    agent_id = "iac_checkov"

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        root = ctx.scan.target_ref

        cmd = [
            CHECKOV_BIN,
            "--directory", root,
            "--output", "json",
            "--quiet",
            "--compact",
        ]

        log.info("checkov_scan_start", root=root, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=CHECKOV_TIMEOUT,
            )
        except FileNotFoundError:
            log.warning("checkov_not_found")
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": []},
                cost_usd=0.0,
                skipped=True,
                skip_reason="checkov_not_installed",
            )
        except subprocess.TimeoutExpired:
            log.error("checkov_timeout", root=root)
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": []},
                cost_usd=0.0,
                skipped=True,
                skip_reason="checkov_timeout",
            )

        # checkov exits 1 when checks fail — that's expected
        if proc.returncode not in (0, 1):
            log.warning("checkov_nonzero_exit", returncode=proc.returncode, stderr=proc.stderr[:500])

        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            log.error("checkov_parse_error", stdout=proc.stdout[:200])
            return AgentOutput(
                agent_id=self.agent_id,
                data={"findings": []},
                cost_usd=0.0,
                skipped=True,
                skip_reason="checkov_parse_error",
            )

        findings = self._parse_report(report, ctx)
        log.info("checkov_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"findings": [f.model_dump(mode="json") for f in findings]},
            cost_usd=0.0,
        )

    def _parse_report(self, report: dict | list, ctx: AgentContext) -> list[Finding]:
        findings: list[Finding] = []
        # checkov returns a list when multiple frameworks are detected
        runs: list[dict] = report if isinstance(report, list) else [report]

        for run in runs:
            failed = run.get("results", {}).get("failed_checks", [])
            for check in failed:
                finding = self._map_check(check, ctx)
                if finding:
                    findings.append(finding)

        return findings

    def _map_check(self, check: dict, ctx: AgentContext) -> Finding | None:
        check_id = check.get("check_id", "unknown")

        # check.check can be a dict (newer checkov) or a string (older versions)
        check_meta = check.get("check", {})
        if isinstance(check_meta, dict):
            check_name = check_meta.get("name", check_id)
        else:
            check_name = str(check_meta) if check_meta else check_id

        file_path = check.get("file_path", "unknown")
        line_range = check.get("file_line_range") or [0, 0]
        line_start = int(line_range[0]) if line_range else 0
        line_end = int(line_range[1]) if len(line_range) > 1 else line_start

        severity_str = (check.get("severity") or "MEDIUM").upper()
        severity = _SEVERITY_MAP.get(severity_str, Severity.medium)

        dedup_key = f"checkov:{check_id}:{file_path}:{line_start}"

        return Finding(
            scan_id=ctx.scan.id,
            rule_id=check_id,
            source_tool="checkov",
            cwe=None,
            owasp_category="A05:2021",
            severity=severity,
            confidence=0.9,
            location=Location(
                file=file_path,
                line_start=line_start,
                line_end=line_end,
            ),
            dedup_key=dedup_key,
            explanation=check_name,
        )
