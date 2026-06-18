# core/scanners/semgrep.py
from __future__ import annotations
import json
import subprocess
import os
import tempfile
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.scanners.sarif import SARIFMapper
from core.understanding.context import CodeContext

log = structlog.get_logger()

SEMGREP_BIN = os.environ.get("SEMGREP_BIN", "semgrep")
SEMGREP_TIMEOUT = int(os.environ.get("SEMGREP_TIMEOUT", "120"))


class SemgrepAdapter:
    agent_id = "sast_semgrep"

    def __init__(self) -> None:
        self._mapper = SARIFMapper()

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        cc = CodeContext.model_validate(ctx.extra.get("code_context", {}))
        root = cc.root

        with tempfile.NamedTemporaryFile(suffix=".sarif.json", delete=False) as tmp:
            sarif_path = tmp.name

        cmd = [
            SEMGREP_BIN, "scan",
            "--config", "auto",
            "--sarif",
            "--output", sarif_path,
            "--timeout", str(SEMGREP_TIMEOUT),
            "--no-git-ignore",
            "--x-ignore-semgrepignore-files",
            root,
        ]

        log.info("semgrep_scan_start", root=root, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SEMGREP_TIMEOUT + 10,
            )
            if proc.returncode not in (0, 1):  # 0=clean, 1=findings found
                log.warning("semgrep_nonzero_exit", returncode=proc.returncode, stderr=proc.stderr[:500])
        except subprocess.TimeoutExpired:
            log.error("semgrep_timeout", root=root)
            return AgentOutput(agent_id=self.agent_id, data={"findings": [], "sarif_raw": {}},
                               cost_usd=0.0, skipped=True, skip_reason="semgrep_timeout")

        try:
            with open(sarif_path) as f:
                sarif = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            log.error("semgrep_sarif_parse_error", error=str(e))
            return AgentOutput(agent_id=self.agent_id, data={"findings": [], "sarif_raw": {}},
                               cost_usd=0.0, skipped=True, skip_reason="sarif_parse_error")
        finally:
            try:
                os.unlink(sarif_path)
            except FileNotFoundError:
                pass

        findings = self._mapper.map(sarif, ctx.scan.id, "semgrep")
        log.info("semgrep_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={
                "findings": [f.model_dump(mode="json") for f in findings],
                "sarif_raw": sarif,
            },
            cost_usd=0.0,
        )
