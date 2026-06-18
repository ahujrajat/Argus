from __future__ import annotations
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4
from core.scanners.nuclei import NucleiAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode


def _make_ctx(dast_authorized: bool = True) -> AgentContext:
    scan = Scan(target_ref="https://app.example.com", pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    gate = MagicMock()
    return AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=gate,
        extra={"dast_authorized": dast_authorized},
    )


_NUCLEI_EVENTS = [
    {
        "template-id": "CVE-2021-41773",
        "info": {
            "name": "Apache Path Traversal",
            "severity": "critical",
            "tags": ["cve", "lfi", "apache"],
            "classification": {"cve-id": ["CVE-2021-41773"]},
        },
        "host": "https://app.example.com",
        "matched-at": "https://app.example.com/cgi-bin/../etc/passwd",
        "timestamp": "2024-01-01T00:00:00.000Z",
    },
    {
        "template-id": "xss-generic",
        "info": {
            "name": "Reflected XSS",
            "severity": "high",
            "tags": ["xss"],
            "classification": {},
        },
        "host": "https://app.example.com",
        "matched-at": "https://app.example.com/search?q=<script>",
        "timestamp": "2024-01-01T00:00:00.000Z",
    },
]


def _make_output_file(tmp_path: Path, events: list[dict]) -> str:
    path = tmp_path / "nuclei.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    return str(path)


@pytest.mark.asyncio
async def test_nuclei_maps_events_to_findings(tmp_path):
    ctx = _make_ctx(dast_authorized=True)
    output_file = _make_output_file(tmp_path, _NUCLEI_EVENTS)

    proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("core.scanners.nuclei.subprocess.run", return_value=proc), \
         patch("core.scanners.nuclei.tempfile.NamedTemporaryFile") as mock_tmp:
        mock_tmp.return_value.__enter__ = MagicMock(return_value=MagicMock(name=output_file))
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        adapter = NucleiAdapter()
        adapter._parse_output = MagicMock(
            return_value=adapter._parse_output(output_file, ctx)
        )
        result = await adapter.scan(ctx)

    assert not result.skipped
    findings = result.data["findings"]
    assert len(findings) == 2


@pytest.mark.asyncio
async def test_nuclei_severity_mapping(tmp_path):
    ctx = _make_ctx(dast_authorized=True)
    output_file = _make_output_file(tmp_path, _NUCLEI_EVENTS)

    adapter = NucleiAdapter()
    findings = adapter._parse_output(output_file, ctx)

    by_id = {f.rule_id: f for f in findings}
    assert by_id["CVE-2021-41773"].severity.value == "critical"
    assert by_id["xss-generic"].severity.value == "high"


@pytest.mark.asyncio
async def test_nuclei_owasp_from_tags(tmp_path):
    ctx = _make_ctx(dast_authorized=True)
    output_file = _make_output_file(tmp_path, _NUCLEI_EVENTS)

    adapter = NucleiAdapter()
    findings = adapter._parse_output(output_file, ctx)

    by_id = {f.rule_id: f for f in findings}
    # lfi tag → A01:2021
    assert by_id["CVE-2021-41773"].owasp_category == "A01:2021"
    # xss tag → A03:2021
    assert by_id["xss-generic"].owasp_category == "A03:2021"


@pytest.mark.asyncio
async def test_nuclei_cve_stored_as_cwe_field(tmp_path):
    ctx = _make_ctx(dast_authorized=True)
    output_file = _make_output_file(tmp_path, _NUCLEI_EVENTS)

    adapter = NucleiAdapter()
    findings = adapter._parse_output(output_file, ctx)

    by_id = {f.rule_id: f for f in findings}
    assert by_id["CVE-2021-41773"].cwe == "CVE-2021-41773"
    assert by_id["xss-generic"].cwe is None


@pytest.mark.asyncio
async def test_nuclei_blocks_without_authorization():
    ctx = _make_ctx(dast_authorized=False)
    proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("core.scanners.nuclei.subprocess.run", return_value=proc):
        result = await NucleiAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "no_dast_authorization"
    assert result.data["findings"] == []


@pytest.mark.asyncio
async def test_nuclei_skips_when_not_installed():
    ctx = _make_ctx(dast_authorized=True)
    with patch("core.scanners.nuclei.subprocess.run", side_effect=FileNotFoundError):
        result = await NucleiAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "nuclei_not_installed"


@pytest.mark.asyncio
async def test_nuclei_skips_on_timeout():
    import subprocess
    ctx = _make_ctx(dast_authorized=True)
    with patch("core.scanners.nuclei.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="nuclei", timeout=300)):
        result = await NucleiAdapter().scan(ctx)

    assert result.skipped
    assert result.skip_reason == "nuclei_timeout"


@pytest.mark.asyncio
async def test_nuclei_empty_output(tmp_path):
    ctx = _make_ctx(dast_authorized=True)
    output_file = str(tmp_path / "empty.jsonl")
    Path(output_file).write_text("")

    adapter = NucleiAdapter()
    findings = adapter._parse_output(output_file, ctx)

    assert findings == []


@pytest.mark.asyncio
async def test_nuclei_skips_malformed_lines(tmp_path):
    ctx = _make_ctx(dast_authorized=True)
    output_file = str(tmp_path / "mixed.jsonl")
    Path(output_file).write_text(
        "not json\n"
        + json.dumps(_NUCLEI_EVENTS[0]) + "\n"
        + "{broken}\n"
        + json.dumps(_NUCLEI_EVENTS[1]) + "\n"
    )

    adapter = NucleiAdapter()
    findings = adapter._parse_output(output_file, ctx)

    assert len(findings) == 2
