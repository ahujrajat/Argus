# core/agents/ingestion.py
from __future__ import annotations
from core.agents.base import AgentContext, AgentOutput
from core.understanding.ingest import build_code_context


class IngestionAgent:
    agent_id = "ingestion"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        code_context = build_code_context(ctx.scan.target_ref)
        return AgentOutput(
            agent_id=self.agent_id,
            data={"code_context": code_context.model_dump()},
            cost_usd=0.0,
        )
