# core/policy/engine.py
"""Security policy definitions and evaluation engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyDefinition:
    """
    A security policy expressed as a set of thresholds and constraints.

    All fields are optional — omitting a field means that constraint is not checked.
    """
    id: str
    name: str
    description: str = ""
    # Severity thresholds: fail if count exceeds these values
    max_critical: int | None = None
    max_high: int | None = None
    max_medium: int | None = None
    max_low: int | None = None
    # Risk score ceiling
    max_risk_score: int | None = None
    # OWASP categories that are blocked entirely (any finding triggers fail)
    blocked_owasp: list[str] = field(default_factory=list)
    # CWEs that are blocked entirely
    blocked_cwe: list[str] = field(default_factory=list)
    # If True, ANY critical finding is a hard fail regardless of max_critical
    block_on_any_critical: bool = False
    # Active flag — inactive policies are skipped during evaluation
    active: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PolicyDefinition":
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            max_critical=d.get("max_critical"),
            max_high=d.get("max_high"),
            max_medium=d.get("max_medium"),
            max_low=d.get("max_low"),
            max_risk_score=d.get("max_risk_score"),
            blocked_owasp=d.get("blocked_owasp", []),
            blocked_cwe=d.get("blocked_cwe", []),
            block_on_any_critical=d.get("block_on_any_critical", False),
            active=d.get("active", True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "max_critical": self.max_critical,
            "max_high": self.max_high,
            "max_medium": self.max_medium,
            "max_low": self.max_low,
            "max_risk_score": self.max_risk_score,
            "blocked_owasp": self.blocked_owasp,
            "blocked_cwe": self.blocked_cwe,
            "block_on_any_critical": self.block_on_any_critical,
            "active": self.active,
        }


@dataclass(frozen=True)
class PolicyViolation:
    rule: str     # human-readable rule name
    actual: Any   # what the scan showed
    limit: Any    # what the policy allows


@dataclass
class PolicyResult:
    policy_id: str
    policy_name: str
    passed: bool
    violations: list[PolicyViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "passed": self.passed,
            "violations": [
                {"rule": v.rule, "actual": v.actual, "limit": v.limit}
                for v in self.violations
            ],
        }


def evaluate_policy(policy: PolicyDefinition, report: dict[str, Any]) -> PolicyResult:
    """
    Evaluate a scan compliance report against a PolicyDefinition.

    `report` is the dict returned by GET /scans/{id}/report (see compliance_report endpoint).
    """
    violations: list[PolicyViolation] = []
    sev = report.get("severity_breakdown", {})
    owasp = report.get("owasp_top10", {})
    cwe = report.get("cwe_top10", {})
    risk_score = report.get("risk_score", 0)

    critical_count = sev.get("critical", 0)
    high_count = sev.get("high", 0)
    medium_count = sev.get("medium", 0)
    low_count = sev.get("low", 0)

    if policy.block_on_any_critical and critical_count > 0:
        violations.append(PolicyViolation(
            rule="block_on_any_critical",
            actual=critical_count,
            limit=0,
        ))

    if policy.max_critical is not None and critical_count > policy.max_critical:
        violations.append(PolicyViolation(
            rule="max_critical",
            actual=critical_count,
            limit=policy.max_critical,
        ))

    if policy.max_high is not None and high_count > policy.max_high:
        violations.append(PolicyViolation(
            rule="max_high",
            actual=high_count,
            limit=policy.max_high,
        ))

    if policy.max_medium is not None and medium_count > policy.max_medium:
        violations.append(PolicyViolation(
            rule="max_medium",
            actual=medium_count,
            limit=policy.max_medium,
        ))

    if policy.max_low is not None and low_count > policy.max_low:
        violations.append(PolicyViolation(
            rule="max_low",
            actual=low_count,
            limit=policy.max_low,
        ))

    if policy.max_risk_score is not None and risk_score > policy.max_risk_score:
        violations.append(PolicyViolation(
            rule="max_risk_score",
            actual=risk_score,
            limit=policy.max_risk_score,
        ))

    for cat in policy.blocked_owasp:
        count = owasp.get(cat, 0)
        if count > 0:
            violations.append(PolicyViolation(
                rule=f"blocked_owasp:{cat}",
                actual=count,
                limit=0,
            ))

    for cwe_id in policy.blocked_cwe:
        count = cwe.get(cwe_id, 0)
        if count > 0:
            violations.append(PolicyViolation(
                rule=f"blocked_cwe:{cwe_id}",
                actual=count,
                limit=0,
            ))

    return PolicyResult(
        policy_id=policy.id,
        policy_name=policy.name,
        passed=len(violations) == 0,
        violations=violations,
    )
