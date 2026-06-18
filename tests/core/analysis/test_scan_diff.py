# tests/core/analysis/test_scan_diff.py
from __future__ import annotations
import pytest
from core.analysis.scan_diff import diff_scans, ScanDiffResult


def _f(dedup_key: str, severity: str = "high") -> dict:
    return {
        "rule_id": "sql-injection",
        "source_tool": "semgrep",
        "severity": severity,
        "dedup_key": dedup_key,
        "location": {"file": "app.py", "line_start": 1},
    }


class TestScanDiffResult:
    def test_counts(self):
        r = ScanDiffResult(
            new_findings=[_f("n1")],
            persisted_findings=[_f("p1"), _f("p2")],
            resolved_findings=[_f("r1")],
        )
        assert r.new_count == 1
        assert r.persisted_count == 2
        assert r.resolved_count == 1

    def test_summary(self):
        r = ScanDiffResult(
            new_findings=[_f("n1")],
            persisted_findings=[_f("p1")],
            resolved_findings=[_f("r1"), _f("r2")],
        )
        s = r.summary()
        assert s == {"new": 1, "persisted": 1, "resolved": 2}


class TestDiffScans:
    def test_all_new(self):
        result = diff_scans(baseline=[], current=[_f("a"), _f("b")])
        assert result.new_count == 2
        assert result.persisted_count == 0
        assert result.resolved_count == 0

    def test_all_resolved(self):
        result = diff_scans(baseline=[_f("a"), _f("b")], current=[])
        assert result.new_count == 0
        assert result.persisted_count == 0
        assert result.resolved_count == 2

    def test_all_persisted(self):
        baseline = [_f("a"), _f("b")]
        current = [_f("a"), _f("b")]
        result = diff_scans(baseline=baseline, current=current)
        assert result.new_count == 0
        assert result.persisted_count == 2
        assert result.resolved_count == 0

    def test_mixed(self):
        baseline = [_f("old1"), _f("common")]
        current = [_f("common"), _f("new1")]
        result = diff_scans(baseline=baseline, current=current)
        assert result.new_count == 1
        assert result.persisted_count == 1
        assert result.resolved_count == 1
        assert result.new_findings[0]["dedup_key"] == "new1"
        assert result.resolved_findings[0]["dedup_key"] == "old1"
        assert result.persisted_findings[0]["dedup_key"] == "common"

    def test_findings_without_dedup_key_ignored(self):
        baseline = [{"rule_id": "x", "source_tool": "s", "severity": "high"}]
        current = [{"rule_id": "y", "source_tool": "s", "severity": "low"}]
        result = diff_scans(baseline=baseline, current=current)
        assert result.new_count == 0
        assert result.resolved_count == 0

    def test_empty_both(self):
        result = diff_scans(baseline=[], current=[])
        assert result.new_count == 0
        assert result.persisted_count == 0
        assert result.resolved_count == 0
