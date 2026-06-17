from __future__ import annotations
import json
import pytest
from pathlib import Path
from uuid import uuid4
from core.scanners.sarif import SARIFMapper
from core.model.entities import Severity


def test_map_single_finding():
    sarif = json.loads(Path("tests/fixtures/sample.sarif.json").read_text())
    mapper = SARIFMapper()
    scan_id = uuid4()
    findings = mapper.map(sarif, scan_id, "semgrep")
    assert len(findings) == 1
    f = findings[0]
    assert f.scan_id == scan_id
    assert f.source_tool == "semgrep"
    assert f.severity == Severity.high
    assert f.cwe == "CWE-89"
    assert f.owasp_category == "A03:2021"
    assert f.location.file == "app.py"
    assert f.location.line_start == 5


def test_dedup_key_is_stable():
    sarif = json.loads(Path("tests/fixtures/sample.sarif.json").read_text())
    mapper = SARIFMapper()
    scan_id = uuid4()
    f1 = mapper.map(sarif, scan_id, "semgrep")[0]
    f2 = mapper.map(sarif, scan_id, "semgrep")[0]
    assert f1.dedup_key == f2.dedup_key


def test_missing_cwe_is_none():
    sarif = {
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "test", "rules": [{"id": "test-rule", "name": "Test"}]}},
                  "results": [{"ruleId": "test-rule", "level": "warning",
                                "message": {"text": "test"},
                                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "foo.py"},
                                               "region": {"startLine": 1, "endLine": 1}}}]}]}]
    }
    mapper = SARIFMapper()
    findings = mapper.map(sarif, uuid4(), "test")
    assert findings[0].cwe is None
    assert findings[0].severity == Severity.medium
