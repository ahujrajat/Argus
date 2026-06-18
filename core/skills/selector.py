# core/skills/selector.py
from __future__ import annotations
from core.skills.base import Skill, SkillLoader


class SkillSelector:
    """Selects applicable skills for a scan based on languages and frameworks."""

    def __init__(self, loader: SkillLoader | None = None) -> None:
        self._loader = loader or SkillLoader()

    def select(
        self,
        languages: list[str],
        frameworks: list[str],
        include_inactive: bool = False,
    ) -> list[Skill]:
        lang_set = {l.lower() for l in languages}
        fw_set = {f.lower() for f in frameworks}

        results: list[Skill] = []
        for skill in self._loader.load_all():
            if not include_inactive and skill.activation == "inactive":
                continue

            skill_langs = {l.lower() for l in skill.languages}
            skill_fws = {f.lower() for f in skill.frameworks}

            # A skill matches if it has no language restrictions, or any language overlaps
            lang_match = not skill_langs or bool(skill_langs & lang_set)
            # Framework match is optional — if skill specifies frameworks, at least one must match
            fw_match = not skill_fws or bool(skill_fws & fw_set)

            if lang_match and fw_match:
                results.append(skill)

        return results
