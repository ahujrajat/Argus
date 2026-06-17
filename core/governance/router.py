from __future__ import annotations
from pathlib import Path
import yaml
from core.model.entities import ModelTier


class ModelRouter:
    def __init__(self, config_path: str = "config/model_tiers.yaml") -> None:
        raw = yaml.safe_load(Path(config_path).read_text())
        self._default_provider: str = raw["providers"]["default"]
        self._tiers: dict[str, dict[str, str]] = raw["tiers"]
        self._task_defaults: dict[str, str] = raw.get("task_defaults", {})
        self._escalation_rules: list[dict] = raw.get("escalation_rules", [])

    def resolve(
        self,
        task_type: str,
        tier_override: ModelTier | None,
        provider_override: str | None = None,
    ) -> tuple[str, str]:
        tier_name = (
            tier_override.value
            if tier_override and tier_override != ModelTier.none
            else self._task_defaults.get(task_type, "balanced")
        )
        provider = provider_override or self._default_provider
        tier_map = self._tiers.get(tier_name, self._tiers["balanced"])
        model_id = tier_map.get(provider, next(iter(tier_map.values())))
        return provider, model_id

    def escalate(self, current_tier: ModelTier, reason: str) -> ModelTier:
        for rule in self._escalation_rules:
            if rule.get("from_tier") == current_tier.value:
                cond = rule["condition"]
                threshold = rule.get("threshold")
                if self._evaluate(cond, threshold, reason):
                    return ModelTier(rule["to_tier"])
        return current_tier

    def _evaluate(self, condition: str, threshold: float | None, reason: str) -> bool:
        if condition == "confidence_lt" and threshold is not None:
            if "confidence_lt:" in reason:
                val = float(reason.split("confidence_lt:")[1])
                return val < threshold
        if condition == "diff_files_gt" and threshold is not None:
            if "diff_files_gt:" in reason:
                val = float(reason.split("diff_files_gt:")[1])
                return val > threshold
        return False
