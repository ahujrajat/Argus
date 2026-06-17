from __future__ import annotations
import pytest
from uuid import uuid4
from core.governance.budget import BudgetGuard, BudgetExceeded


@pytest.fixture
def guard():
    return BudgetGuard("config/budget_policy.yaml")


async def test_under_limit_passes(guard):
    scan_id = uuid4()
    guard.check(scan_id, 1.0)   # $1 well under $5 hard limit


async def test_over_hard_limit_raises(guard):
    scan_id = uuid4()
    guard.record(scan_id, 4.99)
    with pytest.raises(BudgetExceeded):
        guard.check(scan_id, 0.02)  # would push to $5.01


async def test_soft_limit_does_not_raise(guard):
    scan_id = uuid4()
    guard.record(scan_id, 3.50)
    # 3.50 + 0.60 = 4.10, over soft (4.00) but under hard (5.00)
    guard.check(scan_id, 0.60)   # should not raise
