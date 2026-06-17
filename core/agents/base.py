# core/agents/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from core.model.entities import Scan

if TYPE_CHECKING:
    from core.governance.gate import GovernanceGate


@dataclass
class AgentContext:
    scan: Scan
    skills: list[str]
    budget_slice_usd: float
    gate: "GovernanceGate"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    agent_id: str
    data: dict[str, Any]
    cost_usd: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
