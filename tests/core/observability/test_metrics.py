# tests/core/observability/test_metrics.py
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    # Prometheus text format always includes a HELP comment for registered metrics
    body = resp.text
    assert "# HELP" in body or "# TYPE" in body


@pytest.mark.asyncio
async def test_metrics_includes_argus_counters():
    from core.api.app import create_app
    from core.observability.metrics import scans_started_total, findings_total

    # Increment counters so they appear in output
    scans_started_total.labels(pipeline="full-scan", mode="at_rest").inc()
    findings_total.labels(severity="high", source_tool="semgrep", owasp_category="A03:2021").inc()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics")

    assert "argus_scans_started_total" in resp.text
    assert "argus_findings_total" in resp.text


def test_metrics_severity_counters_have_correct_labels():
    from core.observability.metrics import findings_total
    # Verify the counter accepts the expected label set without error
    findings_total.labels(severity="critical", source_tool="grype", owasp_category="A06:2021").inc(0)
    findings_total.labels(severity="low", source_tool="checkov", owasp_category="A05:2021").inc(0)


def test_cost_counter_increments():
    from core.observability.metrics import llm_cost_usd_total, llm_tokens_total
    llm_cost_usd_total.labels(model_id="claude-sonnet-4-6", tier="balanced").inc(0.013)
    llm_tokens_total.labels(model_id="claude-sonnet-4-6", direction="in").inc(4200)
    llm_tokens_total.labels(model_id="claude-sonnet-4-6", direction="out").inc(512)
