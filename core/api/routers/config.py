# core/api/routers/config.py
from __future__ import annotations
from pathlib import Path
from uuid import uuid4
import yaml
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from core.api.deps import get_db
from core.db.tables import AuditLogEntryRow

router = APIRouter(prefix="/config", tags=["config"])

_MODEL_TIERS_PATH = Path("config/model_tiers.yaml")
_BUDGET_POLICY_PATH = Path("config/budget_policy.yaml")


class ModelTiersUpdate(BaseModel):
    providers: dict[str, str]
    tiers: dict[str, dict[str, str]]
    task_defaults: dict[str, str]

    @field_validator("tiers")
    @classmethod
    def tiers_must_be_non_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("tiers must not be empty")
        return v


class BudgetPolicyUpdate(BaseModel):
    per_scan: dict[str, float]
    monthly: dict[str, float]
    on_soft_limit: str = "warn"
    on_hard_limit: str = "stop_and_mark_skipped"

    @field_validator("per_scan", "monthly")
    @classmethod
    def limits_must_be_positive(cls, v: dict) -> dict:
        for key, val in v.items():
            if val <= 0:
                raise ValueError(f"{key} must be positive, got {val}")
        return v


def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=f"Config file {path} not found")


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))


def _audit(db: AsyncSession, action: str, target: str, before: dict, after: dict) -> None:
    db.add(AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action=action,
        target=target,
        before=before,
        after=after,
    ))


@router.get("/")
async def get_config():
    return {
        "model_tiers": _read_yaml(_MODEL_TIERS_PATH),
        "budget_policy": _read_yaml(_BUDGET_POLICY_PATH),
    }


@router.put("/model-tiers", status_code=200)
async def update_model_tiers(
    body: ModelTiersUpdate,
    db: AsyncSession = Depends(get_db),
):
    before = _read_yaml(_MODEL_TIERS_PATH)
    after = body.model_dump()
    _write_yaml(_MODEL_TIERS_PATH, after)
    _audit(db, "config.update_model_tiers", "config:model_tiers", before, after)
    await db.flush()
    return {"status": "updated", "config": after}


@router.put("/budget-policy", status_code=200)
async def update_budget_policy(
    body: BudgetPolicyUpdate,
    db: AsyncSession = Depends(get_db),
):
    before = _read_yaml(_BUDGET_POLICY_PATH)
    after = body.model_dump()
    _write_yaml(_BUDGET_POLICY_PATH, after)
    _audit(db, "config.update_budget_policy", "config:budget_policy", before, after)
    await db.flush()
    return {"status": "updated", "config": after}
