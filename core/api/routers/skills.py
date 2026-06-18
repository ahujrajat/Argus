# core/api/routers/skills.py
from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from core.api.deps import get_db
from core.db.tables import AuditLogEntryRow
from core.skills.base import SkillLoader
from core.skills.selector import SkillSelector

router = APIRouter(prefix="/skills", tags=["skills"])

_loader = SkillLoader()


class CreateSkillRequest(BaseModel):
    name: str
    description: str
    languages: list[str] = []
    frameworks: list[str] = []
    examples: list[dict] = []


def _audit(db: AsyncSession, action: str, name: str, before: str, after: str) -> None:
    entry = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action=action,
        target=f"skill:{name}",
        before={"activation": before},
        after={"activation": after},
    )
    db.add(entry)


@router.get("/")
async def list_skills(language: str | None = None, framework: str | None = None):
    if language or framework:
        selector = SkillSelector(loader=_loader)
        skills = selector.select(
            languages=[language] if language else [],
            frameworks=[framework] if framework else [],
            include_inactive=True,
        )
    else:
        skills = _loader.load_all()

    return [s.model_dump() for s in skills]


@router.post("/{name}/activate", status_code=200)
async def activate_skill(name: str, db: AsyncSession = Depends(get_db)):
    skill = _loader.load_by_name(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    prev = skill.activation
    skill.activation = "active"
    _loader.save_generated(skill)
    _audit(db, "skill.activate", name, prev, "active")
    await db.flush()
    return {"name": name, "activation": "active"}


@router.post("/{name}/disable", status_code=200)
async def disable_skill(name: str, db: AsyncSession = Depends(get_db)):
    skill = _loader.load_by_name(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    prev = skill.activation
    skill.activation = "inactive"
    _loader.save_generated(skill)
    _audit(db, "skill.disable", name, prev, "inactive")
    await db.flush()
    return {"name": name, "activation": "inactive"}


@router.post("/create", status_code=201)
async def create_skill(body: CreateSkillRequest):
    from core.skills.creator import SkillCreatorAgent
    from core.agents.base import AgentContext
    from core.model.entities import Scan, ScanMode
    from core.governance.gate import GovernanceGate

    gate = GovernanceGate()
    scan = Scan(
        target_ref="skill-creator",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    ctx = AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=2.0,
        gate=gate,
        extra={
            "skill_creation_params": {
                "name": body.name,
                "description": body.description,
                "languages": body.languages,
                "frameworks": body.frameworks,
                "examples": body.examples,
            }
        },
    )

    creator = SkillCreatorAgent(loader=_loader)
    try:
        skill, path = await creator.create(
            name=body.name,
            description=body.description,
            languages=body.languages,
            frameworks=body.frameworks,
            examples=body.examples,
            ctx=ctx,
        )
        return {"skill": skill.model_dump(), "path": str(path)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
