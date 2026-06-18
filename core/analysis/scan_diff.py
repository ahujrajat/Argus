# core/analysis/scan_diff.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanDiffResult:
    new_findings: list[dict]
    persisted_findings: list[dict]
    resolved_findings: list[dict]

    @property
    def new_count(self) -> int:
        return len(self.new_findings)

    @property
    def persisted_count(self) -> int:
        return len(self.persisted_findings)

    @property
    def resolved_count(self) -> int:
        return len(self.resolved_findings)

    def summary(self) -> dict:
        return {
            "new": self.new_count,
            "persisted": self.persisted_count,
            "resolved": self.resolved_count,
        }


def diff_scans(baseline: list[dict], current: list[dict]) -> ScanDiffResult:
    """
    Compare two lists of finding dicts by dedup_key.

    baseline: findings from the earlier scan (the reference)
    current:  findings from the newer scan

    Returns:
      new_findings       — in current but not in baseline  (regressions)
      persisted_findings — in both baseline and current    (unfixed)
      resolved_findings  — in baseline but not in current  (fixed/dismissed)
    """
    baseline_keys: dict[str, dict] = {
        f["dedup_key"]: f for f in baseline if f.get("dedup_key")
    }
    current_keys: dict[str, dict] = {
        f["dedup_key"]: f for f in current if f.get("dedup_key")
    }

    new_keys = set(current_keys) - set(baseline_keys)
    persisted_keys = set(current_keys) & set(baseline_keys)
    resolved_keys = set(baseline_keys) - set(current_keys)

    return ScanDiffResult(
        new_findings=[current_keys[k] for k in sorted(new_keys)],
        persisted_findings=[current_keys[k] for k in sorted(persisted_keys)],
        resolved_findings=[baseline_keys[k] for k in sorted(resolved_keys)],
    )
