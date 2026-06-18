# core/governance/gate.py
from __future__ import annotations
import os
from uuid import UUID
import httpx
import structlog
from pydantic import BaseModel
from core.governance.router import ModelRouter
from core.governance.budget import BudgetGuard, BudgetExceeded
from core.model.entities import ModelTier

log = structlog.get_logger()


class GateResult(BaseModel):
    content: str
    tokens_in: int
    tokens_out: int
    cache_hit: bool
    model_id: str
    provider: str
    tier: ModelTier
    cost_usd: float


class GovernanceGate:
    def __init__(
        self,
        router_config: str = "config/model_tiers.yaml",
        budget_config: str = "config/budget_policy.yaml",
        gateway_url: str | None = None,
    ) -> None:
        self._router = ModelRouter(router_config)
        self._budget = BudgetGuard(budget_config)
        self._gateway_url = gateway_url or os.environ.get(
            "FINROUTER_GATEWAY_URL", "http://localhost:3001"
        )

    async def complete(
        self,
        task_type: str,
        messages: list[dict],
        agent_id: str,
        scan_id: UUID,
        tier_override: ModelTier | None = None,
        provider_override: str | None = None,
        zero_retention: bool = True,
    ) -> GateResult:
        provider, model_id = self._router.resolve(task_type, tier_override, provider_override)
        tier = ModelTier(self._router._task_defaults.get(task_type, "balanced")) if not tier_override else tier_override

        # Pre-flight budget check with a conservative estimate (minimum $0.02)
        estimated_cost = max(len(str(messages)) / 1000 * 0.003, 0.02)
        self._budget.check(scan_id, estimated_cost)

        payload = {
            "model": model_id,
            "messages": messages,
            "provider": provider,
            "zero_retention": zero_retention,
        }

        log.info("llm_call_start", agent=agent_id, model=model_id, provider=provider, scan_id=str(scan_id))

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._gateway_url}/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        usage = data["usage"]
        result = GateResult(
            content=data["content"],
            tokens_in=usage["tokens_in"],
            tokens_out=usage["tokens_out"],
            cache_hit=usage.get("cache_hit", False),
            model_id=usage["model_id"],
            provider=usage["provider"],
            tier=tier,
            cost_usd=usage["cost_usd"],
        )

        self._budget.record(scan_id, result.cost_usd)

        log.info(
            "llm_call_complete",
            agent=agent_id,
            model=model_id,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            scan_id=str(scan_id),
        )

        return result
