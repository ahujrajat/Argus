# tests/core/scanners/test_zap.py
from __future__ import annotations
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4

from core.scanners.zap import ZAPAdapter
from core.agents.base import AgentContext
from core.model.entities import Severity


def _make_ctx(authorized: bool = True) -> AgentContext:
    from core.model.entities import Scan, ScanMode, ScanStatus
    from core.governance.gate import GovernanceGate
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    scan = Scan(
        id=uuid4(),
        pipeline_config_id=uuid4(),
        target_ref="http://localhost:8080",
        mode=ScanMode.at_rest,
        status=ScanStatus.running,
        created_at=datetime.now(timezone.utc),
    )
    gate = MagicMock(spec=GovernanceGate)
    return AgentContext(scan=scan, skills=[], budget_slice_usd=1.0, gate=gate, extra={"dast_authorized": authorized})


ZAP_REPORT = {
    "site": [
        {
            "@name": "http://localhost:8080",
            "alerts": [
                {
                    "pluginid": "40018",
                    "alert": "SQL Injection",
                    "riskcode": "3",
                    "cweid": "89",
                    "desc": "SQL injection vulnerability detected",
                    "instances": [
                        {"uri": "http://localhost:8080/search?q=foo", "method": "GET", "evidence": "error in SQL"},
                    ],
                },
                {
                    "pluginid": "10010",
                    "alert": "Cookie No HttpOnly Flag",
                    "riskcode": "1",
                    "cweid": "1004",
                    "desc": "Cookie missing HttpOnly",
                    "instances": [
                        {"uri": "http://localhost:8080/", "method": "GET", "evidence": "Set-Cookie: session=abc"},
                    ],
                },
            ],
        }
    ]
}


@pytest.mark.asyncio
async def test_zap_skips_without_authorization():
    ctx = _make_ctx(authorized=False)
    adapter = ZAPAdapter()
    output = await adapter.scan(ctx)
    assert output.skipped is True
    assert output.skip_reason == "no_dast_authorization"
    assert output.data["findings"] == []


@pytest.mark.asyncio
async def test_zap_skips_when_not_installed():
    ctx = _make_ctx(authorized=True)
    adapter = ZAPAdapter()
    with patch("subprocess.run", side_effect=FileNotFoundError):
        output = await adapter.scan(ctx)
    assert output.skipped is True
    assert output.skip_reason == "zap_not_installed"


@pytest.mark.asyncio
async def test_zap_skips_on_timeout():
    import subprocess
    ctx = _make_ctx(authorized=True)
    adapter = ZAPAdapter()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="zap.sh", timeout=600)):
        output = await adapter.scan(ctx)
    assert output.skipped is True
    assert output.skip_reason == "zap_timeout"


@pytest.mark.asyncio
async def test_zap_parses_report(tmp_path):
    report_path = tmp_path / "zap-report.json"
    report_path.write_text(json.dumps(ZAP_REPORT))

    ctx = _make_ctx(authorized=True)
    adapter = ZAPAdapter()

    with patch("subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("tempfile.TemporaryDirectory") as mock_tmp:
        mock_tmp.return_value.__enter__ = lambda s: str(tmp_path)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        output = await adapter.scan(ctx)

    assert not output.skipped
    findings = output.data["findings"]
    assert len(findings) == 2

    sqli = next(f for f in findings if "SQL Injection" in f["explanation"])
    assert sqli["severity"] == "high"
    assert sqli["owasp_category"] == "A03:2021"
    assert sqli["source_tool"] == "zap"
    assert "CWE-89" in sqli["cwe"]

    cookie = next(f for f in findings if "Cookie" in f["explanation"])
    assert cookie["severity"] == "low"
    assert cookie["owasp_category"] == "A02:2021"


def test_zap_parse_empty_report():
    adapter = ZAPAdapter()
    from core.model.entities import Scan, ScanMode, ScanStatus
    from datetime import datetime, timezone
    scan = Scan(
        id=uuid4(), pipeline_config_id=uuid4(), target_ref="http://test",
        mode=ScanMode.at_rest, status=ScanStatus.running, created_at=datetime.now(timezone.utc),
    )
    from core.governance.gate import GovernanceGate
    gate = MagicMock(spec=GovernanceGate)
    ctx = AgentContext(scan=scan, skills=[], budget_slice_usd=1.0, gate=gate, extra={})

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("{}")
        empty_path = Path(f.name)

    findings = adapter._parse_report(empty_path, ctx)
    assert findings == []
    empty_path.unlink(missing_ok=True)


def test_zap_parse_missing_report():
    adapter = ZAPAdapter()
    from core.model.entities import Scan, ScanMode, ScanStatus
    from datetime import datetime, timezone
    scan = Scan(
        id=uuid4(), pipeline_config_id=uuid4(), target_ref="http://test",
        mode=ScanMode.at_rest, status=ScanStatus.running, created_at=datetime.now(timezone.utc),
    )
    from core.governance.gate import GovernanceGate
    gate = MagicMock(spec=GovernanceGate)
    ctx = AgentContext(scan=scan, skills=[], budget_slice_usd=1.0, gate=gate, extra={})

    findings = adapter._parse_report(Path("/nonexistent/zap-report.json"), ctx)
    assert findings == []
