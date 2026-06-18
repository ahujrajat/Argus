from __future__ import annotations
from uuid import UUID, uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import PipelineConfigRow

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class NodeConfigDTO(BaseModel):
    id: str
    agent: str
    tier: str
    budget_pct: float = 0.0


class EdgeDTO(BaseModel):
    from_: str
    to: str
    condition: Optional[str] = None

    model_config = {"populate_by_name": True}

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        if isinstance(obj, dict) and "from" in obj and "from_" not in obj:
            obj = {**obj, "from_": obj.pop("from")}
        return super().model_validate(obj, *args, **kwargs)


class PipelineDefinitionDTO(BaseModel):
    nodes: list[NodeConfigDTO]
    edges: list[dict]

    @model_validator(mode="after")
    def budget_sum_at_most_100(self) -> "PipelineDefinitionDTO":
        total = sum(n.budget_pct for n in self.nodes)
        if total > 100:
            raise ValueError(f"node budget_pct sum {total} exceeds 100")
        return self


class PipelineListItem(BaseModel):
    id: str
    name: str
    version: int
    is_default: bool
    is_factory: bool


class PipelineDetailResponse(BaseModel):
    id: str
    name: str
    version: int
    is_default: bool
    is_factory: bool
    definition: dict


class CreatePipelineRequest(BaseModel):
    name: str
    definition: PipelineDefinitionDTO
    is_default: bool = False


class UpdatePipelineRequest(BaseModel):
    definition: PipelineDefinitionDTO
    is_default: Optional[bool] = None


class ClonePipelineRequest(BaseModel):
    name: str


def _to_list_item(row: PipelineConfigRow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "is_default": row.is_default,
        "is_factory": row.is_factory,
    }


def _to_detail(row: PipelineConfigRow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "is_default": row.is_default,
        "is_factory": row.is_factory,
        "definition": row.definition,
    }


@router.get("")
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineConfigRow))
    rows = result.scalars().all()
    return [_to_list_item(r) for r in rows]


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.id == str(pipeline_id))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    return _to_detail(row)


@router.post("", status_code=201)
async def create_pipeline(body: CreatePipelineRequest, db: AsyncSession = Depends(get_db)):
    row = PipelineConfigRow(
        id=str(uuid4()),
        name=body.name,
        version=1,
        definition=body.definition.model_dump(),
        is_default=body.is_default,
        is_factory=False,
    )
    db.add(row)
    await db.flush()
    return _to_detail(row)


@router.put("/{pipeline_id}")
async def update_pipeline(
    pipeline_id: UUID, body: UpdatePipelineRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.id == str(pipeline_id))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    if row.is_factory:
        raise HTTPException(status_code=403, detail="factory pipelines are read-only")
    row.definition = body.definition.model_dump()
    if body.is_default is not None:
        row.is_default = body.is_default
    row.version = row.version + 1
    await db.flush()
    return _to_detail(row)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.id == str(pipeline_id))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    if row.is_factory:
        raise HTTPException(status_code=403, detail="factory pipelines are read-only")
    await db.delete(row)
    await db.flush()


@router.post("/{pipeline_id}/clone", status_code=201)
async def clone_pipeline(
    pipeline_id: UUID, body: ClonePipelineRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.id == str(pipeline_id))
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    clone = PipelineConfigRow(
        id=str(uuid4()),
        name=body.name,
        version=1,
        definition=source.definition,
        is_default=False,
        is_factory=False,
    )
    db.add(clone)
    await db.flush()
    return _to_detail(clone)
