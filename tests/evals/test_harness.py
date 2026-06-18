# tests/evals/test_harness.py
from __future__ import annotations
import json
import pytest
from pathlib import Path

from evals.harness import EvalResult, evaluate, _finding_matches_ground_truth


def _finding(rule_id: str, file: str, line: int, cwe: str = "", status: str = "open") -> dict:
    return {
        "rule_id": rule_id,
        "source_tool": "semgrep",
        "cwe": cwe,
        "location": {"file": file, "line_start": line, "line_end": line},
        "status": status,
        "severity": "high",
    }


def _gt(rule_pattern: str, file: str, line: int, cwe: str = "CWE-0") -> dict:
    return {"rule_pattern": rule_pattern, "file": file, "line_start": line, "cwe": cwe}


# ── EvalResult property tests ────────────────────────────────────────────────

class TestEvalResult:
    def test_perfect_precision_recall(self):
        r = EvalResult(true_positives=3, false_positives=0, false_negatives=0)
        assert r.precision == 1.0
        assert r.recall == 1.0
        assert r.fp_rate == 0.0
        assert r.f1 == 1.0

    def test_all_false_positives(self):
        r = EvalResult(true_positives=0, false_positives=5, false_negatives=0)
        assert r.precision == 0.0
        assert r.fp_rate == 1.0
        assert r.f1 == 0.0

    def test_all_false_negatives(self):
        r = EvalResult(true_positives=0, false_positives=0, false_negatives=4)
        assert r.recall == 0.0
        assert r.f1 == 0.0

    def test_zero_division_guards(self):
        r = EvalResult(true_positives=0, false_positives=0, false_negatives=0)
        assert r.precision == 0.0
        assert r.recall == 0.0
        assert r.fp_rate == 0.0
        assert r.f1 == 0.0

    def test_mixed(self):
        r = EvalResult(true_positives=2, false_positives=1, false_negatives=1)
        assert r.precision == pytest.approx(2 / 3)
        assert r.recall == pytest.approx(2 / 3)
        assert r.fp_rate == pytest.approx(1 / 3)


# ── _finding_matches_ground_truth tests ─────────────────────────────────────

class TestFindingMatchesGroundTruth:
    def test_exact_match(self):
        finding = _finding("semgrep.python.sql-injection", "app.py", 5, "CWE-89")
        gt = _gt("sql", "app.py", 5, "CWE-89")
        assert _finding_matches_ground_truth(finding, gt)

    def test_line_tolerance_within_3(self):
        finding = _finding("semgrep.python.sql-injection", "app.py", 7)
        gt = _gt("sql", "app.py", 5)
        assert _finding_matches_ground_truth(finding, gt)

    def test_line_tolerance_exceeds_3(self):
        finding = _finding("semgrep.python.sql-injection", "app.py", 9)
        gt = _gt("sql", "app.py", 5)
        assert not _finding_matches_ground_truth(finding, gt)

    def test_wrong_rule(self):
        finding = _finding("semgrep.python.xss", "app.py", 5)
        gt = _gt("sql", "app.py", 5)
        assert not _finding_matches_ground_truth(finding, gt)

    def test_wrong_file(self):
        finding = _finding("semgrep.python.sql-injection", "other.py", 5)
        gt = _gt("sql", "app.py", 5)
        assert not _finding_matches_ground_truth(finding, gt)

    def test_case_insensitive_rule_match(self):
        finding = _finding("SEMGREP.PYTHON.SQL-INJECTION", "app.py", 5)
        gt = _gt("sql", "app.py", 5)
        assert _finding_matches_ground_truth(finding, gt)


# ── evaluate() integration tests ────────────────────────────────────────────

class TestEvaluate:
    def test_all_tp(self, tmp_path):
        gt_data = {
            "known_findings": [
                _gt("sql", "app.py", 5, "CWE-89"),
                _gt("xss", "app.py", 10, "CWE-79"),
            ]
        }
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt_data))

        findings = [
            _finding("semgrep.sql.injection", "app.py", 5, "CWE-89"),
            _finding("semgrep.xss.reflected", "app.py", 10, "CWE-79"),
        ]
        result = evaluate(findings, str(gt_path))
        assert result.true_positives == 2
        assert result.false_positives == 0
        assert result.false_negatives == 0

    def test_all_fp(self, tmp_path):
        gt_data = {"known_findings": []}
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt_data))

        findings = [
            _finding("semgrep.sql.injection", "app.py", 5),
            _finding("semgrep.xss.reflected", "app.py", 10),
        ]
        result = evaluate(findings, str(gt_path))
        assert result.true_positives == 0
        assert result.false_positives == 2
        assert result.false_negatives == 0

    def test_fn_for_unmatched_gt(self, tmp_path):
        gt_data = {
            "known_findings": [
                _gt("sql", "app.py", 5),
                _gt("xss", "app.py", 10),
            ]
        }
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt_data))

        # Only one finding matches
        findings = [_finding("semgrep.sql.injection", "app.py", 5)]
        result = evaluate(findings, str(gt_path))
        assert result.true_positives == 1
        assert result.false_negatives == 1
        assert result.false_positives == 0

    def test_dismissed_findings_excluded(self, tmp_path):
        gt_data = {
            "known_findings": [
                _gt("sql", "app.py", 5),
            ]
        }
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt_data))

        findings = [
            _finding("semgrep.sql.injection", "app.py", 5, status="dismissed"),
        ]
        result = evaluate(findings, str(gt_path))
        assert result.true_positives == 0
        assert result.false_negatives == 1

    def test_real_ground_truth_fixture_loads(self):
        gt_path = "evals/fixtures/ground_truth.json"
        findings: list[dict] = []
        result = evaluate(findings, gt_path)
        assert result.false_negatives == 4
        assert result.true_positives == 0
        assert result.false_positives == 0
