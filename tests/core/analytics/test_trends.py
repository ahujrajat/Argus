from __future__ import annotations
from datetime import datetime, timezone, timedelta
from core.analytics.trends import bucket_key, compute_finding_trend, compute_mttr, top_rules


# --- bucket_key ---

def test_bucket_key_day():
    dt = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert bucket_key(dt, "day") == "2026-03-15"


def test_bucket_key_week():
    dt = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert bucket_key(dt, "week") == "2026-W10"


# --- compute_finding_trend ---

def _make_finding(days_ago: int, severity: str = "high") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "created_at": now - timedelta(days=days_ago),
        "severity": severity,
    }


def test_finding_trend_returns_correct_bucket_counts():
    findings = [
        _make_finding(1, "critical"),
        _make_finding(1, "high"),
        _make_finding(2, "medium"),
    ]
    result = compute_finding_trend(findings, granularity="day", days_back=7)
    # result is sorted by bucket ascending
    buckets = {r["bucket"]: r for r in result}
    now = datetime.now(timezone.utc)
    day1_key = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    day2_key = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    assert buckets[day1_key]["total"] == 2
    assert buckets[day1_key]["critical"] == 1
    assert buckets[day1_key]["high"] == 1
    assert buckets[day2_key]["total"] == 1
    assert buckets[day2_key]["medium"] == 1


def test_finding_trend_fills_empty_buckets():
    findings = [_make_finding(0, "low")]
    result = compute_finding_trend(findings, granularity="day", days_back=5)
    # Must have at least 6 buckets (days 0..5)
    assert len(result) >= 6
    # All non-today buckets have total=0
    now_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for r in result:
        if r["bucket"] != now_key:
            assert r["total"] == 0


def test_finding_trend_empty_input():
    result = compute_finding_trend([], granularity="day", days_back=3)
    assert isinstance(result, list)
    assert len(result) >= 4  # days 0..3
    for r in result:
        assert r["total"] == 0
        assert r["critical"] == 0


def test_finding_trend_sorted_ascending():
    findings = [_make_finding(i) for i in range(5)]
    result = compute_finding_trend(findings, granularity="day", days_back=10)
    buckets = [r["bucket"] for r in result]
    assert buckets == sorted(buckets)


# --- compute_mttr ---

def test_compute_mttr_correct_hours():
    now = datetime.now(timezone.utc)
    findings = [
        {"created_at": now - timedelta(hours=10), "resolved_at": now},
        {"created_at": now - timedelta(hours=20), "resolved_at": now},
    ]
    result = compute_mttr(findings)
    assert result["sample_size"] == 2
    assert result["mttr_hours"] == 15.0


def test_compute_mttr_none_when_no_resolved():
    now = datetime.now(timezone.utc)
    findings = [
        {"created_at": now - timedelta(hours=5), "resolved_at": None},
    ]
    result = compute_mttr(findings)
    assert result["mttr_hours"] is None
    assert result["sample_size"] == 0


def test_compute_mttr_empty_input():
    result = compute_mttr([])
    assert result["mttr_hours"] is None
    assert result["sample_size"] == 0


def test_compute_mttr_partial_resolved():
    now = datetime.now(timezone.utc)
    findings = [
        {"created_at": now - timedelta(hours=4), "resolved_at": now},
        {"created_at": now - timedelta(hours=8), "resolved_at": None},
    ]
    result = compute_mttr(findings)
    assert result["sample_size"] == 1
    assert result["mttr_hours"] == 4.0


# --- top_rules ---

def test_top_rules_correct_ordering():
    findings = [
        {"rule_id": "sql-injection"},
        {"rule_id": "xss"},
        {"rule_id": "sql-injection"},
        {"rule_id": "sql-injection"},
        {"rule_id": "xss"},
        {"rule_id": "path-traversal"},
    ]
    result = top_rules(findings, top_n=10)
    assert result[0]["rule_id"] == "sql-injection"
    assert result[0]["count"] == 3
    assert result[1]["rule_id"] == "xss"
    assert result[1]["count"] == 2


def test_top_rules_respects_top_n():
    findings = [{"rule_id": f"rule-{i}"} for i in range(20)]
    result = top_rules(findings, top_n=5)
    assert len(result) == 5


def test_top_rules_empty_input():
    result = top_rules([])
    assert result == []
