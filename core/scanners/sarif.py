# core/scanners/sarif.py
from __future__ import annotations
from uuid import UUID
from core.model.entities import Finding, Severity, Location


_LEVEL_MAP: dict[str, Severity] = {
    "error": Severity.high,
    "warning": Severity.medium,
    "note": Severity.low,
    "none": Severity.info,
}

_CWE_OWASP: dict[str, str] = {
    "CWE-89": "A03:2021",
    "CWE-79": "A03:2021",
    "CWE-22": "A01:2021",
    "CWE-78": "A03:2021",
    "CWE-502": "A08:2021",
    "CWE-798": "A07:2021",
    "CWE-311": "A02:2021",
    "CWE-918": "A10:2021",
    "CWE-611": "A05:2021",
    "CWE-601": "A01:2021",
}


class SARIFMapper:
    def map(self, sarif: dict, scan_id: UUID, source_tool: str) -> list[Finding]:
        findings: list[Finding] = []
        for run in sarif.get("runs", []):
            rule_meta = self._index_rules(run)
            for result in run.get("results", []):
                finding = self._map_result(result, rule_meta, scan_id, source_tool)
                if finding:
                    findings.append(finding)
        return findings

    def _index_rules(self, run: dict) -> dict[str, dict]:
        rules = {}
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            rules[rule["id"]] = rule
        return rules

    def _map_result(self, result: dict, rule_meta: dict, scan_id: UUID, source_tool: str) -> Finding | None:
        rule_id = result.get("ruleId", "unknown")
        level = result.get("level", "warning")
        severity = _LEVEL_MAP.get(level, Severity.medium)
        if severity == Severity.high and "critical" in result.get("message", {}).get("text", "").lower():
            severity = Severity.critical

        loc_data = result.get("locations", [{}])[0]
        phys = loc_data.get("physicalLocation", {})
        region = phys.get("region", {})
        file_uri = phys.get("artifactLocation", {}).get("uri", "unknown")
        line_start = region.get("startLine", 0)
        line_end = region.get("endLine", line_start)
        snippet = region.get("snippet", {}).get("text")

        rule = rule_meta.get(rule_id, {})
        tags: list[str] = rule.get("properties", {}).get("tags", [])
        cwe = next((t for t in tags if t.startswith("CWE-")), None)
        owasp = next((t for t in tags if t.startswith("OWASP-")), None)
        if owasp:
            owasp = owasp.replace("OWASP-", "")
        elif cwe and cwe in _CWE_OWASP:
            owasp = _CWE_OWASP[cwe]

        dedup_key = f"{source_tool}:{rule_id}:{file_uri}:{line_start}"

        return Finding(
            scan_id=scan_id,
            rule_id=rule_id,
            source_tool=source_tool,
            cwe=cwe,
            owasp_category=owasp,
            severity=severity,
            location=Location(file=file_uri, line_start=line_start, line_end=line_end, snippet=snippet),
            dedup_key=dedup_key,
        )
