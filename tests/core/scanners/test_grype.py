from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from core.scanners.grype import GrypeAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode


@pytest.fixture
def ctx():
    scan = Scan(
        target_ref="/repo",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    gate = MagicMock()
    return AgentContext(scan=scan, skills=[], budget_slice_usd=0.0, gate=gate, extra={})


_GRYPE_REPORT = {
    "matches": [
        {
            "vulnerability": {
                "id": "CVE-2021-44228",
                "severity": "Critical",
                "description": "Log4Shell RCE vulnerability",
                "cvss": [{"version": "3.1", "metrics": {"baseScore": 10.0}}],
            },
            "artifact": {
                "name": "log4j-core",
                "version": "2.14.1",
                "language": "java",
                "locations": [{"realPath": "/repo/lib/log4j-core-2.14.1.jar"}],
            },
        },
        {
            "vulnerability": {
                "id": "CVE-2022-42003",
                "severity": "High",
                "description": "Jackson deserialisation issue",
                "cvss": [{"version": "3.1", "metrics": {"baseScore": 7.5}}],
            },
            "artifact": {
                "name": "jackson-databind",
                "version": "2.13.0",
                "language": "java",
                "locations": [{"realPath": "/repo/lib/jackson-databind-2.13.0.jar"}],
            },
        },
    ],
    "source": {"type": "directory", "target": {"path": "/repo"}},
}


@pytest.mark.asyncio
async def test_grype_maps_matches_to_findings(ctx):
    proc = MagicMock(returncode=0, stdout=json.dumps(_GRYPE_REPORT), stderr="")
    with patch("core.scanners.grype.subprocess.run", return_value=proc):
        result = await GrypeAdapter().scan(ctx)

    assert not result.skipped
    findings = result.data["findings"]
    assert len(findings) == 2
    rule_ids = {f["rule_id"] for f in findings}
    assert "CVE-2021-44228" in rule_ids
    assert "CVE-2022-42003" in rule_ids


@pytest.mark.asyncio
async def test_grype_severity_mapping(ctx):
    proc = MagicMock(returncode=0, stdout=json.dumps(_GRYPE_REPORT), stderr="")
    with patch("core.scanners.grype.subprocess.run", return_value=proc):
        result = await GrypeAdapter().scan(ctx)

    findings_by_id = {f["rule_id"]: f for f in result.data["findings"]}
    assert findings_by_id["CVE-2021-44228"]["severity"] == "critical"
    assert findings_by_id["CVE-2022-42003"]["severity"] == "high"


@pytest.mark.asyncio
async def test_grype_confidence_from_cvss(ctx):
    proc = MagicMock(returncode=0, stdout=json.dumps(_GRYPE_REPORT), stderr="")
    with patch("core.scanners.grype.subprocess.run", return_value=proc):
        result = await GrypeAdapter().scan(ctx)

    findings_by_id = {f["rule_id"]: f for f in result.data["findings"]}
    # CVSSv3 score 10.0 → confidence 1.0
    assert findings_by_id["CVE-2021-44228"]["confidence"] == pytest.approx(1.0)
    # CVSSv3 score 7.5 → confidence 0.75
    assert findings_by_id["CVE-2022-42003"]["confidence"] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_grype_skips_when_not_installed(ctx):
    with patch("core.scanners.grype.subprocess.run", side_effect=FileNotFoundError):
        result = await GrypeAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "grype_not_installed"
    assert result.data["findings"] == []


@pytest.mark.asyncio
async def test_grype_skips_on_timeout(ctx):
    import subprocess
    with patch("core.scanners.grype.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="grype", timeout=180)):
        result = await GrypeAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "grype_timeout"


@pytest.mark.asyncio
async def test_grype_skips_on_parse_error(ctx):
    proc = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("core.scanners.grype.subprocess.run", return_value=proc):
        result = await GrypeAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "grype_parse_error"


@pytest.mark.asyncio
async def test_grype_owasp_category(ctx):
    proc = MagicMock(returncode=0, stdout=json.dumps(_GRYPE_REPORT), stderr="")
    with patch("core.scanners.grype.subprocess.run", return_value=proc):
        result = await GrypeAdapter().scan(ctx)

    for f in result.data["findings"]:
        assert f["owasp_category"] == "A06:2021"


@pytest.mark.asyncio
async def test_grype_empty_matches(ctx):
    report = {"matches": [], "source": {}}
    proc = MagicMock(returncode=0, stdout=json.dumps(report), stderr="")
    with patch("core.scanners.grype.subprocess.run", return_value=proc):
        result = await GrypeAdapter().scan(ctx)

    assert not result.skipped
    assert result.data["findings"] == []
