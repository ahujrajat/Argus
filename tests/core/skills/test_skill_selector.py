from __future__ import annotations
import pytest
from pathlib import Path
import tempfile
import textwrap
from core.skills.base import Skill, SkillLoader
from core.skills.selector import SkillSelector


def _write_skill(d: Path, name: str, languages: list, frameworks: list, activation: str = "active") -> None:
    skill = Skill(
        name=name,
        description=f"Test skill {name}",
        languages=languages,
        frameworks=frameworks,
        activation=activation,
        body="test body",
    )
    import yaml
    (d / f"{name}.yaml").write_text(yaml.dump(skill.model_dump()))


@pytest.fixture
def skill_dir(tmp_path):
    _write_skill(tmp_path, "python-skill", ["python"], [])
    _write_skill(tmp_path, "django-skill", ["python"], ["django"])
    _write_skill(tmp_path, "universal-skill", [], [])
    _write_skill(tmp_path, "inactive-skill", ["python"], [], activation="inactive")
    return tmp_path


def test_selector_matches_by_language(skill_dir):
    loader = SkillLoader(builtin_dir=skill_dir, generated_dir=skill_dir / "gen")
    selector = SkillSelector(loader=loader)

    results = selector.select(languages=["python"], frameworks=[])
    names = {s.name for s in results}
    assert "python-skill" in names
    assert "universal-skill" in names
    # django-skill requires django framework — excluded when no frameworks specified
    assert "django-skill" not in names
    assert "inactive-skill" not in names


def test_selector_filters_by_framework(skill_dir):
    loader = SkillLoader(builtin_dir=skill_dir, generated_dir=skill_dir / "gen")
    selector = SkillSelector(loader=loader)

    results = selector.select(languages=["python"], frameworks=["flask"])
    names = {s.name for s in results}
    # django-skill requires django, flask doesn't match → excluded
    assert "django-skill" not in names
    assert "python-skill" in names
    assert "universal-skill" in names


def test_selector_excludes_inactive_by_default(skill_dir):
    loader = SkillLoader(builtin_dir=skill_dir, generated_dir=skill_dir / "gen")
    selector = SkillSelector(loader=loader)

    active_results = selector.select(["python"], [])
    inactive_results = selector.select(["python"], [], include_inactive=True)
    active_names = {s.name for s in active_results}
    inactive_names = {s.name for s in inactive_results}
    assert "inactive-skill" not in active_names
    assert "inactive-skill" in inactive_names


def test_selector_universal_skill_matches_any_language(skill_dir):
    loader = SkillLoader(builtin_dir=skill_dir, generated_dir=skill_dir / "gen")
    selector = SkillSelector(loader=loader)

    for lang in ["javascript", "go", "java", "rust"]:
        results = selector.select(languages=[lang], frameworks=[])
        names = {s.name for s in results}
        assert "universal-skill" in names, f"universal skill should match {lang}"


def test_loader_loads_builtin_skills():
    loader = SkillLoader()
    skills = loader.load_all()
    names = {s.name for s in skills}
    assert "python-secure-coding" in names
    assert "secrets-detection" in names
    assert "iac-hardening" in names


def test_loader_returns_valid_skill_objects():
    loader = SkillLoader()
    for skill in loader.load_all():
        assert isinstance(skill, Skill)
        assert skill.name
        assert skill.description
        assert skill.activation in ("active", "inactive")
