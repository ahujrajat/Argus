from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.suppression.engine import SuppressionRule, apply_suppressions, load_argusignore


def _rule(pattern_type: str, pattern: str, expires_at=None) -> SuppressionRule:
    return SuppressionRule(id="r1", pattern_type=pattern_type, pattern=pattern, expires_at=expires_at)


def _finding(rule_id="sql_injection", file="src/db.py", dedup="fp:abc123") -> dict:
    return {
        "rule_id": rule_id,
        "location": {"file": file},
        "dedup_key": dedup,
    }


# --- SuppressionRule.is_active ---

def test_rule_is_active_no_expiry():
    r = _rule("rule_id", "sql_injection")
    assert r.is_active() is True


def test_rule_is_active_future_expiry():
    future = datetime.now(timezone.utc) + timedelta(days=10)
    r = _rule("rule_id", "sql_injection", expires_at=future)
    assert r.is_active() is True


def test_rule_is_expired():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    r = _rule("rule_id", "sql_injection", expires_at=past)
    assert r.is_active() is False


# --- apply_suppressions ---

def test_no_rules_keeps_all():
    findings = [_finding(), _finding(rule_id="xss")]
    kept, suppressed = apply_suppressions(findings, [])
    assert len(kept) == 2
    assert suppressed == []


def test_fingerprint_match():
    f = _finding(dedup="fp:abc123")
    rule = _rule("fingerprint", "fp:abc123")
    kept, suppressed = apply_suppressions([f], [rule])
    assert kept == []
    assert len(suppressed) == 1


def test_path_glob_match():
    f = _finding(file="tests/unit/test_foo.py")
    rule = _rule("path_glob", "tests/**")
    kept, suppressed = apply_suppressions([f], [rule])
    assert kept == []
    assert len(suppressed) == 1


def test_path_glob_no_match():
    f = _finding(file="src/main.py")
    rule = _rule("path_glob", "tests/**")
    kept, suppressed = apply_suppressions([f], [rule])
    assert len(kept) == 1
    assert suppressed == []


def test_rule_id_match():
    f = _finding(rule_id="semgrep.python.sqli")
    rule = _rule("rule_id", "semgrep.python.sqli")
    kept, suppressed = apply_suppressions([f], [rule])
    assert kept == []
    assert len(suppressed) == 1


def test_expired_rule_does_not_suppress():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    f = _finding(dedup="fp:abc123")
    rule = _rule("fingerprint", "fp:abc123", expires_at=past)
    kept, suppressed = apply_suppressions([f], [rule])
    assert len(kept) == 1
    assert suppressed == []


def test_mixed_findings_partial_suppression():
    f1 = _finding(rule_id="sqli", file="src/db.py", dedup="d1")
    f2 = _finding(rule_id="xss", file="tests/foo.py", dedup="d2")
    rules = [_rule("path_glob", "tests/**")]
    kept, suppressed = apply_suppressions([f1, f2], rules)
    assert len(kept) == 1
    assert kept[0]["rule_id"] == "sqli"
    assert len(suppressed) == 1


# --- load_argusignore ---

def test_load_argusignore_path_prefix(tmp_path: Path):
    ignore_file = tmp_path / ".argusignore"
    ignore_file.write_text("path:tests/**\n")
    rules = load_argusignore(str(ignore_file))
    assert len(rules) == 1
    assert rules[0].pattern_type == "path_glob"
    assert rules[0].pattern == "tests/**"


def test_load_argusignore_rule_prefix(tmp_path: Path):
    ignore_file = tmp_path / ".argusignore"
    ignore_file.write_text("rule:semgrep.python.sqli\n")
    rules = load_argusignore(str(ignore_file))
    assert rules[0].pattern_type == "rule_id"
    assert rules[0].pattern == "semgrep.python.sqli"


def test_load_argusignore_fp_prefix(tmp_path: Path):
    ignore_file = tmp_path / ".argusignore"
    ignore_file.write_text("fp:abc123def456\n")
    rules = load_argusignore(str(ignore_file))
    assert rules[0].pattern_type == "fingerprint"
    assert rules[0].pattern == "abc123def456"


def test_load_argusignore_bare_pattern_defaults_to_path_glob(tmp_path: Path):
    ignore_file = tmp_path / ".argusignore"
    ignore_file.write_text("vendor/**\n")
    rules = load_argusignore(str(ignore_file))
    assert rules[0].pattern_type == "path_glob"
    assert rules[0].pattern == "vendor/**"


def test_load_argusignore_skips_comments_and_blanks(tmp_path: Path):
    ignore_file = tmp_path / ".argusignore"
    ignore_file.write_text("# this is a comment\n\npath:tests/**\n")
    rules = load_argusignore(str(ignore_file))
    assert len(rules) == 1


def test_load_argusignore_missing_file():
    rules = load_argusignore("/nonexistent/.argusignore")
    assert rules == []
