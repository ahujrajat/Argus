# core/api/routers/policies.py
from __future__ import annotations
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import PolicyRow, PolicyEvaluationRow, ScanRow, FindingRow
from core.policy.engine import PolicyDefinition, evaluate_policy

router = APIRouter(prefix="/policies", tags=["policies"])


class CreatePolicyRequest(BaseModel):
    name: str
    description: str = ""
    max_critical: int | None = None
    max_high: int | None = None
    max_medium: int | None = None
    max_low: int | None = None
    max_risk_score: int | None = None
    blocked_owasp: list[str] = []
    blocked_cwe: list[str] = []
    block_on_any_critical: bool = False
    active: bool = True
    created_by: str = "api"

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @field_validator("max_critical", "max_high", "max_medium", "max_low", "max_risk_score", mode="before")
    @classmethod
    def thresholds_must_be_non_negative(cls, v: Any) -> Any:
        if v is not None and v < 0:
            raise ValueError("threshold must be >= 0")
        return v


def _row_to_dict(r: PolicyRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "definition": r.definition,
        "active": r.active,
        "created_by": r.created_by,
        "created_at": r.created_at,
    }


@router.post("/", status_code=201)
async def create_policy(body: CreatePolicyRequest, db: AsyncSession = Depends(get_db)):
    policy_id = str(uuid4())
    definition = {
        "id": policy_id,
        "name": body.name,
        "description": body.description,
        "max_critical": body.max_critical,
        "max_high": body.max_high,
        "max_medium": body.max_medium,
        "max_low": body.max_low,
        "max_risk_score": body.max_risk_score,
        "blocked_owasp": body.blocked_owasp,
        "blocked_cwe": body.blocked_cwe,
        "block_on_any_critical": body.block_on_any_critical,
        "active": body.active,
    }
    row = PolicyRow(
        id=policy_id,
        name=body.name,
        description=body.description,
        definition=definition,
        active=body.active,
        created_by=body.created_by,
    )
    db.add(row)
    await db.flush()
    return _row_to_dict(row)


@router.get("/")
async def list_policies(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PolicyRow).order_by(PolicyRow.created_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if active_only:
        rows = [r for r in rows if r.active]
    return [_row_to_dict(r) for r in rows]


@router.get("/{policy_id}")
async def get_policy(policy_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PolicyRow).where(PolicyRow.id == policy_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
    return _row_to_dict(row)


@router.delete("/{policy_id}", status_code=200)
async def delete_policy(policy_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PolicyRow).where(PolicyRow.id == policy_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(row)
    await db.flush()
    return {"id": policy_id, "status": "deleted"}


@router.post("/{policy_id}/evaluate/{scan_id}", status_code=200)
async def evaluate_scan_against_policy(
    policy_id: str,
    scan_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a completed scan against a specific policy and persist the result."""
    policy_result_row = await db.execute(select(PolicyRow).where(PolicyRow.id == policy_id))
    policy_row = policy_result_row.scalar_one_or_none()
    if not policy_row:
        raise HTTPException(status_code=404, detail="Policy not found")

    scan_result = await db.execute(select(ScanRow).where(ScanRow.id == scan_id))
    scan_row = scan_result.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Build compliance report inline (same logic as the report endpoint)
    from collections import Counter
    findings_result = await db.execute(
        select(FindingRow).where(FindingRow.scan_id == scan_id)
    )
    findings = findings_result.scalars().all()

    severity_counts: Counter = Counter()
    owasp_counts: Counter = Counter()
    cwe_counts: Counter = Counter()
    weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}

    for f in findings:
        severity_counts[f.severity.lower()] += 1
        if f.owasp_category:
            owasp_counts[f.owasp_category] += 1
        if f.cwe:
            cwe_counts[f.cwe] += 1

    risk_score = sum(weights.get(s, 0) * c for s, c in severity_counts.items())

    report = {
        "severity_breakdown": dict(severity_counts),
        "owasp_top10": dict(owasp_counts.most_common(10)),
        "cwe_top10": dict(cwe_counts.most_common(10)),
        "risk_score": risk_score,
    }

    policy = PolicyDefinition.from_dict(policy_row.definition)
    result = evaluate_policy(policy, report)

    # Persist evaluation
    eval_row = PolicyEvaluationRow(
        id=str(uuid4()),
        scan_id=scan_id,
        policy_id=policy_id,
        passed=result.passed,
        violations=[
            {"rule": v.rule, "actual": v.actual, "limit": v.limit}
            for v in result.violations
        ],
    )
    db.add(eval_row)
    await db.flush()

    return {
        "evaluation_id": eval_row.id,
        "scan_id": scan_id,
        **result.to_dict(),
    }


@router.get("/evaluations/scan/{scan_id}")
async def get_scan_policy_evaluations(scan_id: str, db: AsyncSession = Depends(get_db)):
    """All policy evaluations for a given scan."""
    scan_result = await db.execute(select(ScanRow).where(ScanRow.id == scan_id))
    if not scan_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Scan not found")

    result = await db.execute(
        select(PolicyEvaluationRow)
        .where(PolicyEvaluationRow.scan_id == scan_id)
        .order_by(PolicyEvaluationRow.evaluated_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "evaluation_id": r.id,
            "scan_id": r.scan_id,
            "policy_id": r.policy_id,
            "passed": r.passed,
            "violations": r.violations,
            "evaluated_at": r.evaluated_at,
        }
        for r in rows
    ]
