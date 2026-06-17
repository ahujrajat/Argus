# core/scanners/base.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from core.agents.base import AgentContext, AgentOutput


@runtime_checkable
class BaseAdapter(Protocol):
    agent_id: str

    async def scan(self, ctx: AgentContext) -> AgentOutput: ...
