from __future__ import annotations


def matches_query(finding: dict, q: str) -> bool:
    """
    Case-insensitive substring search across key finding fields:
    rule_id, source_tool, cwe, owasp_category, explanation, dedup_key,
    and location.file if location is a dict.
    """
    q_lower = q.lower()
    fields = [
        finding.get("rule_id", ""),
        finding.get("source_tool", ""),
        finding.get("cwe", ""),
        finding.get("owasp_category", ""),
        finding.get("explanation", ""),
        finding.get("dedup_key", ""),
        (finding.get("location") or {}).get("file", "") if isinstance(finding.get("location"), dict) else "",
    ]
    return any(q_lower in (f or "").lower() for f in fields)
