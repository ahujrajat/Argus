from __future__ import annotations
import pytest
from core.policy.engine import PolicyDefinition, PolicyResult, PolicyViolation, evaluate_policy


def _policy(**kwargs) -> PolicyDefinition:
    defaults = dict(id="p1", name="test-policy")
    defaults.update(kwargs)
    return PolicyDefinition(**defaults)


def _report(**kwargs) -> dict:
    defaults = dict(
        severity_breakdown={},
        owasp_top10={},
        cwe_top10={},
        risk_score=0,
        total_findings=0,
    )
    defaults.update(kwargs)
    return defaults


# --- PolicyDefinition.from_dict / to_dict roundtrip ---

def test_from_dict_roundtrip():
    d = {
        "id": "p1", "name": "strict", "description": "strict policy",
        "max_critical": 0, "max_high": 5,
        "blocked_owasp": ["A03:2021"], "blocked_cwe": ["CWE-89"],
        "block_on_any_critical": True, "active": True,
    }
    p = PolicyDefinition.from_dict(d)
    assert p.max_critical == 0
    assert p.blocked_owasp == ["A03:2021"]
    out = p.to_dict()
    assert out["max_critical"] == 0
    assert out["blocked_owasp"] == ["A03:2021"]


# --- evaluate_policy: passing cases ---

def test_empty_report_passes_any_policy():
    policy = _policy(max_critical=0, max_high=0, max_risk_score=100)
    result = evaluate_policy(policy, _report())
    assert result.passed is True
    assert result.violations == []


def test_findings_within_limits_pass():
    policy = _policy(max_high=3)
    report = _report(severity_breakdown={"high": 2}, risk_score=10)
    result = evaluate_policy(policy, report)
    assert result.passed is True


def test_findings_at_exact_limit_pass():
    policy = _policy(max_high=2)
    report = _report(severity_breakdown={"high": 2})
    result = evaluate_policy(policy, report)
    assert result.passed is True


# --- evaluate_policy: failing cases ---

def test_max_critical_exceeded():
    policy = _policy(max_critical=0)
    report = _report(severity_breakdown={"critical": 1})
    result = evaluate_policy(policy, report)
    assert result.passed is False
    assert any(v.rule == "max_critical" for v in result.violations)


def test_max_high_exceeded():
    policy = _policy(max_high=2)
    report = _report(severity_breakdown={"high": 5})
    result = evaluate_policy(policy, report)
    assert result.passed is False
    v = next(v for v in result.violations if v.rule == "max_high")
    assert v.actual == 5
    assert v.limit == 2


def test_max_risk_score_exceeded():
    policy = _policy(max_risk_score=20)
    report = _report(severity_breakdown={"critical": 2}, risk_score=20)
    # exactly at limit passes
    result = evaluate_policy(policy, report)
    assert result.passed is True

    report2 = _report(severity_breakdown={"critical": 3}, risk_score=30)
    result2 = evaluate_policy(policy, report2)
    assert result2.passed is False
    assert any(v.rule == "max_risk_score" for v in result2.violations)


def test_block_on_any_critical():
    policy = _policy(block_on_any_critical=True)
    report = _report(severity_breakdown={"critical": 1})
    result = evaluate_policy(policy, report)
    assert result.passed is False
    assert any(v.rule == "block_on_any_critical" for v in result.violations)


def test_blocked_owasp_triggers_fail():
    policy = _policy(blocked_owasp=["A03:2021"])
    report = _report(owasp_top10={"A03:2021": 2, "A01:2021": 1})
    result = evaluate_policy(policy, report)
    assert result.passed is False
    assert any("A03:2021" in v.rule for v in result.violations)


def test_blocked_owasp_not_present_passes():
    policy = _policy(blocked_owasp=["A03:2021"])
    report = _report(owasp_top10={"A01:2021": 1})
    result = evaluate_policy(policy, report)
    assert result.passed is True


def test_blocked_cwe_triggers_fail():
    policy = _policy(blocked_cwe=["CWE-89"])
    report = _report(cwe_top10={"CWE-89": 1, "CWE-79": 2})
    result = evaluate_policy(policy, report)
    assert result.passed is False
    assert any("CWE-89" in v.rule for v in result.violations)


def test_multiple_violations_all_reported():
    policy = _policy(max_critical=0, max_high=1, blocked_owasp=["A03:2021"])
    report = _report(
        severity_breakdown={"critical": 1, "high": 3},
        owasp_top10={"A03:2021": 2},
        risk_score=25,
    )
    result = evaluate_policy(policy, report)
    assert result.passed is False
    assert len(result.violations) >= 3


# --- PolicyResult.to_dict ---

def test_policy_result_to_dict():
    r = PolicyResult(
        policy_id="p1", policy_name="test",
        passed=False,
        violations=[PolicyViolation(rule="max_high", actual=5, limit=2)],
    )
    d = r.to_dict()
    assert d["passed"] is False
    assert d["violations"][0]["rule"] == "max_high"
    assert d["violations"][0]["actual"] == 5
