# core/skills/base.py
from __future__ import annotations
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel

_BUILTIN_DIR = Path(__file__).parent / "builtin"
_GENERATED_DIR = Path(__file__).parent / "generated"


class Skill(BaseModel):
    name: str
    version: int = 1
    description: str
    languages: list[str] = []
    frameworks: list[str] = []
    activation: Literal["active", "inactive"] = "active"
    body: str = ""
    rules_dir: str | None = None


class SkillLoader:
    """Loads Skill objects from YAML files in builtin/ and generated/ directories."""

    def __init__(
        self,
        builtin_dir: Path = _BUILTIN_DIR,
        generated_dir: Path = _GENERATED_DIR,
    ) -> None:
        self._dirs = [builtin_dir, generated_dir]

    def load_all(self) -> list[Skill]:
        skills: list[Skill] = []
        for d in self._dirs:
            if not d.exists():
                continue
            for path in sorted(d.glob("*.yaml")):
                try:
                    data = yaml.safe_load(path.read_text())
                    if data:
                        skills.append(Skill.model_validate(data))
                except Exception:
                    pass
        return skills

    def load_by_name(self, name: str) -> Skill | None:
        for skill in self.load_all():
            if skill.name == name:
                return skill
        return None

    def save_generated(self, skill: Skill) -> Path:
        _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path = _GENERATED_DIR / f"{skill.name}.yaml"
        path.write_text(yaml.dump(skill.model_dump(), default_flow_style=False, allow_unicode=True))
        return path
