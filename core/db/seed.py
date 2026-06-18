from __future__ import annotations
from pathlib import Path
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.tables import PipelineConfigRow

_CONFIGS_DIR = Path(__file__).parent.parent.parent / "config" / "pipeline_configs"


async def seed_pipeline_configs(session: AsyncSession) -> None:
    for yaml_path in sorted(_CONFIGS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text())
        name: str = data["name"]
        result = await session.execute(
            select(PipelineConfigRow).where(PipelineConfigRow.name == name)
        )
        if result.scalar_one_or_none() is not None:
            continue
        definition = {
            "nodes": [
                {
                    "id": n["id"],
                    "agent": n["agent"],
                    "tier": n["tier"],
                    "budget_pct": n.get("budget_pct", 0),
                }
                for n in data.get("nodes", [])
            ],
            "edges": [
                {"from": e["from"], "to": e["to"], "condition": e.get("condition")}
                for e in data.get("edges", [])
            ],
        }
        row = PipelineConfigRow(
            name=name,
            version=data.get("version", 1),
            definition=definition,
            is_default=data.get("is_default", False),
            is_factory=True,
        )
        session.add(row)
