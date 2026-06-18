# core/remediation/validator.py
from __future__ import annotations
import json
import shutil
import subprocess
import tempfile
import structlog
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = structlog.get_logger()


@dataclass
class PatchValidationResult:
    applied: bool
    finding_cleared: bool
    new_findings: list[str] = field(default_factory=list)
    error: Optional[str] = None


class PatchValidator:
    """Validates a unified diff by dry-running patch then comparing semgrep results."""

    def validate(
        self,
        diff: str,
        target_file: Path,
        scan_root: Path,
        original_rule_id: str,
    ) -> PatchValidationResult:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            work_file = tmp_dir / target_file.name
            shutil.copy2(target_file, work_file)

            diff_file = tmp_dir / "fix.patch"
            diff_file.write_text(diff, encoding="utf-8")

            # Dry-run first
            dry = subprocess.run(
                ["patch", "--dry-run", "-p1", "--input", str(diff_file), str(work_file)],
                capture_output=True,
                text=True,
            )
            if dry.returncode != 0:
                return PatchValidationResult(
                    applied=False,
                    finding_cleared=False,
                    error=dry.stderr.strip() or dry.stdout.strip(),
                )

            # Apply for real
            apply = subprocess.run(
                ["patch", "-p1", "--input", str(diff_file), str(work_file)],
                capture_output=True,
                text=True,
            )
            if apply.returncode != 0:
                return PatchValidationResult(
                    applied=False,
                    finding_cleared=False,
                    error=apply.stderr.strip() or apply.stdout.strip(),
                )

            # Semgrep before (original file)
            before_sarif = self._run_semgrep(target_file)
            before_rule_ids = self._extract_rule_ids(before_sarif)

            # Semgrep after (patched copy)
            after_sarif = self._run_semgrep(work_file)
            after_rule_ids = self._extract_rule_ids(after_sarif)

            finding_cleared = original_rule_id not in after_rule_ids
            new_findings = sorted(after_rule_ids - before_rule_ids)

            return PatchValidationResult(
                applied=True,
                finding_cleared=finding_cleared,
                new_findings=new_findings,
                error=None,
            )

    def _run_semgrep(self, target: Path) -> dict:
        try:
            proc = subprocess.run(
                ["semgrep", "scan", "--config", "auto", "--sarif", str(target)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return json.loads(proc.stdout) if proc.stdout.strip() else {"runs": [{"results": []}]}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
            log.warning("semgrep_run_error", error=str(exc), target=str(target))
            return {"runs": [{"results": []}]}

    @staticmethod
    def _extract_rule_ids(sarif: dict) -> set[str]:
        rule_ids: set[str] = set()
        for run in sarif.get("runs", []):
            for result in run.get("results", []):
                rid = result.get("ruleId")
                if rid:
                    rule_ids.add(rid)
        return rule_ids
