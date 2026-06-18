# tests/core/sbom/test_cyclonedx.py
from __future__ import annotations
import pytest
from uuid import uuid4
from core.sbom.cyclonedx import build_sbom, _findings_to_vulnerabilities, _severity_to_rating


def _finding(
    rule_id: str = "sql-injection",
    source_tool: str = "semgrep",
    severity: str = "high",
    cwe: str = "CWE-89",
    owasp: str = "A03:2021",
    dedup_key: str | None = None,
) -> dict:
    return {
        "rule_id": rule_id,
        "source_tool": source_tool,
        "cwe": cwe,
        "owasp_category": owasp,
        "severity": severity,
        "location": {"file": "app.py", "line_start": 5, "line_end": 5},
        "dedup_key": dedup_key or f"{source_tool}:{rule_id}",
        "explanation": f"{source_tool} found {rule_id}",
    }


class TestSeverityToRating:
    def test_known_severities(self):
        assert _severity_to_rating("critical") == "critical"
        assert _severity_to_rating("high") == "high"
        assert _severity_to_rating("medium") == "medium"
        assert _severity_to_rating("low") == "low"
        assert _severity_to_rating("info") == "info"

    def test_case_insensitive(self):
        assert _severity_to_rating("HIGH") == "high"
        assert _severity_to_rating("Critical") == "critical"

    def test_negligible_maps_to_none(self):
        assert _severity_to_rating("negligible") == "none"

    def test_unknown_fallback(self):
        assert _severity_to_rating("bananas") == "unknown"


class TestFindingsToVulnerabilities:
    def test_maps_basic_finding(self):
        findings = [_finding()]
        vulns = _findings_to_vulnerabilities(findings)
        assert len(vulns) == 1
        v = vulns[0]
        assert v["source"]["name"] == "semgrep"
        assert v["ratings"][0]["severity"] == "high"
        assert v["affects"][0]["ref"] == "app.py"

    def test_dedup_by_dedup_key(self):
        findings = [_finding(dedup_key="k1"), _finding(dedup_key="k1")]
        vulns = _findings_to_vulnerabilities(findings)
        assert len(vulns) == 1

    def test_cwe_extracted(self):
        findings = [_finding(cwe="CWE-89")]
        vulns = _findings_to_vulnerabilities(findings)
        assert vulns[0]["cwes"] == [89]

    def test_cve_generates_advisory(self):
        findings = [_finding(cwe="CVE-2023-1234", dedup_key="cve-finding")]
        vulns = _findings_to_vulnerabilities(findings)
        assert len(vulns[0]["advisories"]) == 1
        assert "CVE-2023-1234" in vulns[0]["advisories"][0]["url"]

    def test_owasp_in_properties(self):
        findings = [_finding(owasp="A03:2021")]
        vulns = _findings_to_vulnerabilities(findings)
        props = {p["name"]: p["value"] for p in vulns[0].get("properties", [])}
        assert props.get("argus:owasp_category") == "A03:2021"

    def test_empty_findings(self):
        assert _findings_to_vulnerabilities([]) == []


class TestBuildSbom:
    def test_top_level_structure(self):
        scan_id = str(uuid4())
        sbom = build_sbom(scan_id=scan_id, target_ref="/repo/app", findings=[])
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"
        assert sbom["serialNumber"].startswith("urn:uuid:")
        assert sbom["version"] == 1

    def test_metadata_contains_scan_id(self):
        scan_id = str(uuid4())
        sbom = build_sbom(scan_id=scan_id, target_ref="/repo/app", findings=[])
        props = {p["name"]: p["value"] for p in sbom["metadata"]["properties"]}
        assert props["argus:scan_id"] == scan_id

    def test_components_contains_target(self):
        sbom = build_sbom(scan_id="s1", target_ref="/repo/my-app", findings=[])
        assert any(c["name"] == "/repo/my-app" for c in sbom["components"])

    def test_vulnerabilities_populated(self):
        findings = [_finding("sql-injection"), _finding("xss", cwe="CWE-79", dedup_key="semgrep:xss")]
        sbom = build_sbom(scan_id="s1", target_ref="/repo/app", findings=findings)
        assert len(sbom["vulnerabilities"]) == 2

    def test_empty_findings_empty_vulns(self):
        sbom = build_sbom(scan_id="s1", target_ref="/repo/app", findings=[])
        assert sbom["vulnerabilities"] == []
