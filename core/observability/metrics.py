# core/observability/metrics.py
from __future__ import annotations
from prometheus_client import (
    Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST,
    REGISTRY,
)

# ── Scan metrics ─────────────────────────────────────────────────────────────

scans_started_total = Counter(
    "argus_scans_started_total",
    "Total scans triggered",
    ["pipeline", "mode"],
)

scans_completed_total = Counter(
    "argus_scans_completed_total",
    "Total scans completed",
    ["pipeline", "mode", "status"],
)

scan_duration_seconds = Histogram(
    "argus_scan_duration_seconds",
    "Scan wall-clock duration in seconds",
    ["pipeline"],
    buckets=[5, 15, 30, 60, 120, 300, 600],
)

# ── Finding metrics ───────────────────────────────────────────────────────────

findings_total = Counter(
    "argus_findings_total",
    "Total findings emitted across all scans",
    ["severity", "source_tool", "owasp_category"],
)

findings_dismissed_total = Counter(
    "argus_findings_dismissed_total",
    "Total findings dismissed (false positive / won't fix)",
    ["severity"],
)

# ── Cost metrics ──────────────────────────────────────────────────────────────

llm_cost_usd_total = Counter(
    "argus_llm_cost_usd_total",
    "Cumulative LLM spend in USD",
    ["model_id", "tier"],
)

llm_tokens_total = Counter(
    "argus_llm_tokens_total",
    "Cumulative LLM tokens consumed",
    ["model_id", "direction"],  # direction: in | out
)

budget_exceeded_total = Counter(
    "argus_budget_exceeded_total",
    "Scans stopped by budget guard",
    ["limit_type"],  # per_scan | monthly
)

# ── Agent / pipeline metrics ──────────────────────────────────────────────────

agent_calls_total = Counter(
    "argus_agent_calls_total",
    "Total agent invocations",
    ["agent_id"],
)

agent_skipped_total = Counter(
    "argus_agent_skipped_total",
    "Total agent skips (not installed, unauthorized, budget)",
    ["agent_id", "reason"],
)

agent_duration_seconds = Histogram(
    "argus_agent_duration_seconds",
    "Per-agent wall-clock duration",
    ["agent_id"],
    buckets=[0.1, 0.5, 1, 5, 15, 30, 60, 120],
)

# ── Webhook metrics ───────────────────────────────────────────────────────────

webhooks_received_total = Counter(
    "argus_webhooks_received_total",
    "Webhook events received",
    ["provider", "event_type"],
)

# ── Export helpers ────────────────────────────────────────────────────────────

def metrics_text() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
