from __future__ import annotations
import pytest
from core.governance.router import ModelRouter
from core.model.entities import ModelTier


@pytest.fixture
def router():
    return ModelRouter("config/model_tiers.yaml")


def test_fast_tier_resolves_anthropic(router):
    provider, model = router.resolve("explanation", None)
    assert provider == "anthropic"
    assert "haiku" in model.lower()


def test_tier_override(router):
    provider, model = router.resolve("explanation", ModelTier.top)
    assert "opus" in model.lower()


def test_balanced_is_default_for_triage(router):
    provider, model = router.resolve("triage", None)
    assert "sonnet" in model.lower()


def test_escalate_balanced_to_top(router):
    result = router.escalate(ModelTier.balanced, "confidence_lt:0.3")
    assert result == ModelTier.top


def test_escalate_fast_stays_fast_no_rule(router):
    result = router.escalate(ModelTier.fast, "confidence_lt:0.3")
    assert result == ModelTier.fast
