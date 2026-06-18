# tests/core/test_seed.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from pathlib import Path


def _make_session(existing_row=None):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_row
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    return session


async def test_seed_inserts_factory_rows_for_all_yamls():
    from pathlib import Path as _Path
    yaml_count = len(list((_Path("config") / "pipeline_configs").glob("*.yaml")))

    session = AsyncMock()
    results = []
    for _ in range(yaml_count):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        results.append(r)
    session.execute = AsyncMock(side_effect=results)
    session.add = MagicMock()

    from core.db.seed import seed_pipeline_configs
    await seed_pipeline_configs(session)

    assert session.add.call_count == yaml_count


async def test_seed_skips_existing_rows():
    # All three already exist
    session = AsyncMock()
    existing = MagicMock()
    existing.scalar_one_or_none.return_value = MagicMock()  # non-None → skip

    async def _execute(*args, **kwargs):
        return existing

    session.execute = _execute
    session.add = MagicMock()

    from core.db.seed import seed_pipeline_configs
    await seed_pipeline_configs(session)

    session.add.assert_not_called()


async def test_seed_sets_is_factory_true():
    from pathlib import Path as _Path
    yaml_count = len(list((_Path("config") / "pipeline_configs").glob("*.yaml")))

    session = AsyncMock()
    results = []
    for _ in range(yaml_count):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        results.append(r)
    session.execute = AsyncMock(side_effect=results)
    added_rows = []
    session.add = MagicMock(side_effect=added_rows.append)

    from core.db.seed import seed_pipeline_configs
    await seed_pipeline_configs(session)

    assert all(row.is_factory is True for row in added_rows)


async def test_seed_definition_matches_yaml_nodes():
    from pathlib import Path as _Path
    yaml_count = len(list((_Path("config") / "pipeline_configs").glob("*.yaml")))

    session = AsyncMock()
    results = []
    for _ in range(yaml_count):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        results.append(r)
    session.execute = AsyncMock(side_effect=results)
    added_rows = []
    session.add = MagicMock(side_effect=added_rows.append)

    from core.db.seed import seed_pipeline_configs
    await seed_pipeline_configs(session)

    # Sort by name so we can reliably find full-scan
    row_by_name = {row.name: row for row in added_rows}
    full_scan = row_by_name["full-scan"]
    node_ids = {n["id"] for n in full_scan.definition["nodes"]}
    assert "ingestion" in node_ids
    assert "sast" in node_ids
    assert "fix_generation" in node_ids
