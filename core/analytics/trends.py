# core/analytics/trends.py
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

Granularity = Literal["day", "week"]


def bucket_key(dt: datetime, granularity: Granularity) -> str:
    """Return YYYY-MM-DD for day, YYYY-Www for week."""
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    else:
        return dt.strftime("%Y-W%W")


def compute_finding_trend(
    findings: list[dict],
    granularity: Granularity = "day",
    days_back: int = 30,
) -> list[dict]:
    """
    Aggregate findings by bucket.
    Returns list of {"bucket": str, "total": int, "critical": int, "high": int, "medium": int, "low": int}
    sorted by bucket ascending. Buckets with zero findings are included (filled in).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)

    # Build ordered list of all expected buckets
    buckets: dict[str, dict] = {}
    current = cutoff
    while current <= now:
        key = bucket_key(current, granularity)
        if key not in buckets:
            buckets[key] = {"bucket": key, "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        current += timedelta(days=1)

    for f in findings:
        created_at: datetime = f["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at < cutoff:
            continue
        key = bucket_key(created_at, granularity)
        if key not in buckets:
            buckets[key] = {"bucket": key, "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        sev = (f.get("severity") or "").lower()
        buckets[key]["total"] += 1
        if sev in ("critical", "high", "medium", "low"):
            buckets[key][sev] += 1

    return sorted(buckets.values(), key=lambda x: x["bucket"])


def compute_mttr(findings: list[dict]) -> dict:
    """
    Compute mean time to remediate in hours.
    Returns {"mttr_hours": float | None, "sample_size": int}
    Only includes findings where resolved_at is not None.
    """
    durations: list[float] = []
    for f in findings:
        resolved_at = f.get("resolved_at")
        if resolved_at is None:
            continue
        created_at: datetime = f["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=timezone.utc)
        delta = resolved_at - created_at
        durations.append(delta.total_seconds() / 3600.0)

    if not durations:
        return {"mttr_hours": None, "sample_size": 0}

    return {
        "mttr_hours": round(sum(durations) / len(durations), 2),
        "sample_size": len(durations),
    }


def top_rules(findings: list[dict], top_n: int = 10) -> list[dict]:
    """
    Returns top_n most frequent rule_ids.
    Each item: {"rule_id": str, "count": int}
    """
    counts: Counter = Counter()
    for f in findings:
        rule_id = f.get("rule_id")
        if rule_id:
            counts[rule_id] += 1
    return [{"rule_id": rid, "count": cnt} for rid, cnt in counts.most_common(top_n)]
