from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from core.scanners.checkov import CheckovAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode


@pytest.fixture
def ctx():
    scan = Scan(
        target_ref="/infra",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    gate = MagicMock()
    return AgentContext(scan=scan, skills=[], budget_slice_usd=0.0, gate=gate, extra={})


_SINGLE_FRAMEWORK_REPORT = {
    "check_type": "terraform",
    "results": {
        "passed_checks": [],
        "failed_checks": [
            {
                "check_id": "CKV_AWS_6",
                "check": {"name": "Ensure S3 bucket has server-side encryption enabled"},
                "file_path": "/infra/main.tf",
                "file_line_range": [1, 15],
                "severity": "HIGH",
                "resource": "aws_s3_bucket.data",
            },
            {
                "check_id": "CKV_AWS_18",
                "check": {"name": "Ensure S3 bucket has logging enabled"},
                "file_path": "/infra/main.tf",
                "file_line_range": [16, 25],
                "severity": "MEDIUM",
                "resource": "aws_s3_bucket.data",
            },
        ],
    },
}

_MULTI_FRAMEWORK_REPORT = [
    {
        "check_type": "terraform",
        "results": {
            "failed_checks": [
                {
                    "check_id": "CKV_AWS_6",
                    "check": {"name": "S3 SSE"},
                    "file_path": "/infra/main.tf",
                    "file_line_range": [1, 10],
                    "severity": "HIGH",
                }
            ]
        },
    },
    {
        "check_type": "kubernetes",
        "results": {
            "failed_checks": [
                {
                    "check_id": "CKV_K8S_30",
                    "check": {"name": "Do not admit root containers"},
                    "file_path": "/infra/deploy.yaml",
                    "file_line_range": [5, 20],
                    "severity": "CRITICAL",
                }
            ]
        },
    },
]


@pytest.mark.asyncio
async def test_checkov_maps_failed_checks_to_findings(ctx):
    proc = MagicMock(returncode=1, stdout=json.dumps(_SINGLE_FRAMEWORK_REPORT), stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    assert not result.skipped
    findings = result.data["findings"]
    assert len(findings) == 2
    rule_ids = {f["rule_id"] for f in findings}
    assert "CKV_AWS_6" in rule_ids
    assert "CKV_AWS_18" in rule_ids


@pytest.mark.asyncio
async def test_checkov_severity_mapping(ctx):
    proc = MagicMock(returncode=1, stdout=json.dumps(_SINGLE_FRAMEWORK_REPORT), stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    by_id = {f["rule_id"]: f for f in result.data["findings"]}
    assert by_id["CKV_AWS_6"]["severity"] == "high"
    assert by_id["CKV_AWS_18"]["severity"] == "medium"


@pytest.mark.asyncio
async def test_checkov_multi_framework_report(ctx):
    proc = MagicMock(returncode=1, stdout=json.dumps(_MULTI_FRAMEWORK_REPORT), stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    findings = result.data["findings"]
    assert len(findings) == 2
    rule_ids = {f["rule_id"] for f in findings}
    assert "CKV_AWS_6" in rule_ids
    assert "CKV_K8S_30" in rule_ids


@pytest.mark.asyncio
async def test_checkov_owasp_category(ctx):
    proc = MagicMock(returncode=1, stdout=json.dumps(_SINGLE_FRAMEWORK_REPORT), stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    for f in result.data["findings"]:
        assert f["owasp_category"] == "A05:2021"
        assert f["confidence"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_checkov_skips_when_not_installed(ctx):
    with patch("core.scanners.checkov.subprocess.run", side_effect=FileNotFoundError):
        result = await CheckovAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "checkov_not_installed"


@pytest.mark.asyncio
async def test_checkov_skips_on_timeout(ctx):
    import subprocess
    with patch("core.scanners.checkov.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="checkov", timeout=120)):
        result = await CheckovAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "checkov_timeout"


@pytest.mark.asyncio
async def test_checkov_skips_on_parse_error(ctx):
    proc = MagicMock(returncode=0, stdout="not json at all", stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "checkov_parse_error"


@pytest.mark.asyncio
async def test_checkov_empty_failed_checks(ctx):
    report = {"check_type": "terraform", "results": {"failed_checks": []}}
    proc = MagicMock(returncode=0, stdout=json.dumps(report), stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    assert not result.skipped
    assert result.data["findings"] == []


@pytest.mark.asyncio
async def test_checkov_handles_missing_severity(ctx):
    report = {
        "results": {
            "failed_checks": [
                {
                    "check_id": "CKV_AWS_999",
                    "check": {"name": "Some check"},
                    "file_path": "/infra/main.tf",
                    "file_line_range": [1, 5],
                    # no severity field — should default to medium
                }
            ]
        }
    }
    proc = MagicMock(returncode=1, stdout=json.dumps(report), stderr="")
    with patch("core.scanners.checkov.subprocess.run", return_value=proc):
        result = await CheckovAdapter().scan(ctx)

    assert result.data["findings"][0]["severity"] == "medium"
