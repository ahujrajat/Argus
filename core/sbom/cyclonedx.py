# core/sbom/cyclonedx.py
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serial_number() -> str:
    return f"urn:uuid:{uuid4()}"


def _cve_to_advisories(cve: str | None) -> list[dict]:
    if not cve or not cve.startswith("CVE-"):
        return []
    return [{"url": f"https://nvd.nist.gov/vuln/detail/{cve}"}]


def _severity_to_rating(severity: str) -> str:
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "info": "info",
        "informational": "info",
        "negligible": "none",
    }.get(severity.lower(), "unknown")


def _findings_to_vulnerabilities(findings: list[dict]) -> list[dict]:
    seen: set[str] = set()
    vulns: list[dict] = []

    for f in findings:
        source_tool = f.get("source_tool", "argus")
        rule_id = f.get("rule_id", "unknown")
        cwe = f.get("cwe") or ""
        cve = cwe if cwe.upper().startswith("CVE-") else None
        owasp = f.get("owasp_category") or ""
        severity = f.get("severity", "info")
        location = f.get("location") or {}
        explanation = f.get("explanation") or ""

        vuln_id = f.get("dedup_key") or f"{source_tool}:{rule_id}"
        if vuln_id in seen:
            continue
        seen.add(vuln_id)

        vuln: dict[str, Any] = {
            "bom-ref": vuln_id,
            "id": cve or f"{source_tool.upper()}-{rule_id}",
            "source": {
                "name": source_tool,
                "url": f"https://argus/rules/{rule_id}",
            },
            "ratings": [
                {
                    "source": {"name": "argus"},
                    "severity": _severity_to_rating(severity),
                    "method": "other",
                }
            ],
            "description": explanation or rule_id,
            "advisories": _cve_to_advisories(cve),
            "affects": [
                {
                    "ref": location.get("file", "unknown"),
                    "versions": [
                        {
                            "version": "unspecified",
                            "status": "affected",
                        }
                    ],
                }
            ],
        }

        if cwe and not cwe.upper().startswith("CVE-"):
            vuln["cwes"] = [int(cwe.replace("CWE-", "")) if cwe.upper().startswith("CWE-") else 0]

        if owasp:
            vuln["properties"] = [{"name": "argus:owasp_category", "value": owasp}]

        vulns.append(vuln)

    return vulns


def build_sbom(
    scan_id: str,
    target_ref: str,
    findings: list[dict],
    tool_version: str = "0.2.0",
) -> dict:
    """Return a CycloneDX 1.5 BOM document as a Python dict (JSON-serializable)."""
    components = [
        {
            "bom-ref": f"target:{hashlib.sha256(target_ref.encode()).hexdigest()[:12]}",
            "type": "application",
            "name": target_ref,
            "version": "unspecified",
        }
    ]

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": _serial_number(),
        "version": 1,
        "metadata": {
            "timestamp": _now_iso(),
            "tools": [
                {
                    "vendor": "Argus",
                    "name": "argus-security-platform",
                    "version": tool_version,
                }
            ],
            "component": {
                "type": "application",
                "name": target_ref,
                "bom-ref": f"target:{hashlib.sha256(target_ref.encode()).hexdigest()[:12]}",
            },
            "properties": [
                {"name": "argus:scan_id", "value": scan_id},
            ],
        },
        "components": components,
        "vulnerabilities": _findings_to_vulnerabilities(findings),
    }
