from __future__ import annotations
from pathlib import Path
from uuid import UUID
import yaml
import structlog

log = structlog.get_logger()


class BudgetExceeded(Exception):
    def __init__(self, scan_id: UUID, used: float, limit: float) -> None:
        super().__init__(f"Scan {scan_id} exceeded hard limit ${limit:.2f} (used ${used:.2f})")
        self.scan_id = scan_id
        self.used = used
        self.limit = limit


class BudgetGuard:
    def __init__(self, config_path: str = "config/budget_policy.yaml") -> None:
        raw = yaml.safe_load(Path(config_path).read_text())
        per_scan = raw["per_scan"]
        self._soft = float(per_scan["soft_limit_usd"])
        self._hard = float(per_scan["hard_limit_usd"])
        self._spend: dict[UUID, float] = {}

    def record(self, scan_id: UUID, cost_usd: float) -> None:
        self._spend[scan_id] = self._spend.get(scan_id, 0.0) + cost_usd

    def check(self, scan_id: UUID, prospective_cost: float) -> None:
        used = self._spend.get(scan_id, 0.0)
        projected = used + prospective_cost
        if projected > self._hard:
            raise BudgetExceeded(scan_id, projected, self._hard)
        if projected > self._soft:
            log.warning(
                "budget_soft_limit_approaching",
                scan_id=str(scan_id),
                used_usd=projected,
                soft_limit_usd=self._soft,
            )

    def used(self, scan_id: UUID) -> float:
        return self._spend.get(scan_id, 0.0)
