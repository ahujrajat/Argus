# core/suppression/engine.py
from __future__ import annotations
import fnmatch
from datetime import datetime, timezone
from dataclasses import dataclass


@dataclass(frozen=True)
class SuppressionRule:
    id: str
    pattern_type: str   # fingerprint | path_glob | rule_id
    pattern: str
    expires_at: datetime | None = None

    def is_active(self) -> bool:
        if self.expires_at is None:
            return True
        return self.expires_at > datetime.now(timezone.utc)


def apply_suppressions(
    findings: list[dict],
    rules: list[SuppressionRule],
) -> tuple[list[dict], list[dict]]:
    """
    Split findings into (kept, suppressed).

    Rules:
      fingerprint — exact match on finding["dedup_key"]
      path_glob   — fnmatch on finding["location"]["file"]
      rule_id     — exact match on finding["rule_id"]
    """
    active_rules = [r for r in rules if r.is_active()]
    if not active_rules:
        return findings, []

    kept: list[dict] = []
    suppressed: list[dict] = []

    for f in findings:
        dedup = f.get("dedup_key", "")
        file_path = (f.get("location") or {}).get("file", "")
        rule_id = f.get("rule_id", "")

        matched = False
        for r in active_rules:
            if r.pattern_type == "fingerprint" and r.pattern == dedup:
                matched = True
            elif r.pattern_type == "path_glob" and fnmatch.fnmatch(file_path, r.pattern):
                matched = True
            elif r.pattern_type == "rule_id" and r.pattern == rule_id:
                matched = True
            if matched:
                break

        (suppressed if matched else kept).append(f)

    return kept, suppressed


def load_argusignore(path: str) -> list[SuppressionRule]:
    """
    Parse a .argusignore file into SuppressionRule objects.

    Format (one entry per line):
      # comment
      path:tests/**            -> path_glob suppression
      rule:semgrep.python.sqli -> rule_id suppression
      fp:<dedup_key>           -> fingerprint suppression
      tests/**                 -> path_glob (default, no prefix)
    """
    import os
    rules: list[SuppressionRule] = []
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return rules

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("path:"):
            rules.append(SuppressionRule(id=f"ignore:{i}", pattern_type="path_glob", pattern=line[5:]))
        elif line.startswith("rule:"):
            rules.append(SuppressionRule(id=f"ignore:{i}", pattern_type="rule_id", pattern=line[5:]))
        elif line.startswith("fp:"):
            rules.append(SuppressionRule(id=f"ignore:{i}", pattern_type="fingerprint", pattern=line[3:]))
        else:
            rules.append(SuppressionRule(id=f"ignore:{i}", pattern_type="path_glob", pattern=line))

    return rules
