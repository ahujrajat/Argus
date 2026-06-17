# core/scanners/trufflehog.py
from __future__ import annotations
import json
import subprocess
import os
import structlog
from uuid import uuid4
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Finding, Severity, Location
from core.model.redaction import fingerprint

log = structlog.get_logger()

TRUFFLEHOG_BIN = os.environ.get("TRUFFLEHOG_BIN", "trufflehog")
TRUFFLEHOG_TIMEOUT = int(os.environ.get("TRUFFLEHOG_TIMEOUT", "60"))


class TruffleHogAdapter:
    agent_id = "secrets_trufflehog"

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        root = ctx.scan.target_ref

        cmd = [
            TRUFFLEHOG_BIN, "filesystem",
            root,
            "--json",
            "--no-update",
            "--no-filter-unverified",
        ]

        log.info("trufflehog_scan_start", root=root, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TRUFFLEHOG_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            log.error("trufflehog_timeout", root=root)
            return AgentOutput(agent_id=self.agent_id, data={"findings": []},
                               cost_usd=0.0, skipped=True, skip_reason="trufflehog_timeout")

        findings = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            raw = event.get("Raw") or event.get("RawV2") or ""
            fp = fingerprint(raw) if raw else "unknown"

            source = event.get("SourceMetadata", {}).get("Data", {})
            file_path = (
                source.get("Filesystem", {}).get("file")
                or source.get("Git", {}).get("file")
                or "unknown"
            )
            line_num = int(
                source.get("Filesystem", {}).get("line")
                or source.get("Git", {}).get("line")
                or 0
            )

            finding = Finding(
                scan_id=ctx.scan.id,
                rule_id=f"secrets.{event.get('DetectorName', 'generic').lower()}",
                source_tool="trufflehog",
                cwe="CWE-798",
                owasp_category="A07:2021",
                severity=Severity.critical,
                confidence=float(event.get("Verified", False)),
                location=Location(
                    file=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    snippet="[REDACTED]",  # never store raw secret
                ),
                dedup_key=f"trufflehog:{event.get('DetectorName', 'generic')}:{fp[:16]}",
            )
            findings.append(finding)

        log.info("trufflehog_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"findings": [f.model_dump(mode="json") for f in findings]},
            cost_usd=0.0,
        )
