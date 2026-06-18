# core/skills/creator.py
from __future__ import annotations
import json
import structlog
from pathlib import Path
from core.agents.base import AgentContext, AgentOutput
from core.skills.base import Skill, SkillLoader

log = structlog.get_logger()

_SYSTEM = """You are a security skill author for Argus, an AI security scanning platform. \
You create Argus skill definitions that enrich security agents with domain-specific knowledge. \
A skill is a focused, reusable block of security guidance that agents load when scanning relevant targets.

Always respond with valid JSON. Never include markdown fences or explanatory text outside the JSON."""

_USER_TEMPLATE = """\
Create an Argus skill for the following security domain:

Name: {name}
Description: {description}
Target languages: {languages}
Target frameworks: {frameworks}
{examples_section}

Respond with a JSON object matching this exact schema:
{{
  "name": "{name}",
  "version": 1,
  "description": "<concise one-sentence description>",
  "languages": [{languages_list}],
  "frameworks": [{frameworks_list}],
  "activation": "active",
  "body": "<multi-line security guidance string with 8-15 bullet points covering key vulnerability patterns, anti-patterns, and triage advice specific to this domain>",
  "rules_dir": null
}}

Rules for the body:
- Each bullet point starts with a dash and covers a specific, actionable security check
- Include common attack patterns, dangerous API calls, and common developer mistakes
- Include triage guidance (how to prioritize findings in this domain)
- Be specific to the stated languages/frameworks
- Do not include generic security advice"""


class SkillCreatorAgent:
    agent_id = "skill_creator"

    def __init__(self, loader: SkillLoader | None = None) -> None:
        self._loader = loader or SkillLoader()

    async def create(
        self,
        name: str,
        description: str,
        languages: list[str],
        frameworks: list[str],
        examples: list[dict],
        ctx: AgentContext,
    ) -> tuple[Skill, Path]:
        examples_section = ""
        if examples:
            examples_section = f"\nExample findings for context:\n{json.dumps(examples[:5], indent=2, default=str)}"

        langs_str = ", ".join(languages)
        fws_str = ", ".join(frameworks)

        def _quoted_list(items: list[str]) -> str:
            return ", ".join(f'"{i}"' for i in items)

        user_msg = _USER_TEMPLATE.format(
            name=name,
            description=description,
            languages=langs_str or "any",
            frameworks=fws_str or "any",
            examples_section=examples_section,
            languages_list=_quoted_list(languages),
            frameworks_list=_quoted_list(frameworks),
        )

        result = await ctx.gate.complete(
            task_type="skill_creation",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )

        try:
            data = json.loads(result.content)
        except json.JSONDecodeError:
            log.error("skill_creator_parse_error", content_preview=result.content[:200])
            raise ValueError(f"Skill creator returned non-JSON: {result.content[:100]}")

        skill = Skill.model_validate(data)
        path = self._loader.save_generated(skill)

        log.info("skill_created", name=skill.name, path=str(path))
        return skill, path

    async def run(self, ctx: AgentContext) -> AgentOutput:
        """Adapter for orchestrator usage — reads params from ctx.extra."""
        params = ctx.extra.get("skill_creation_params", {})
        if not params:
            return AgentOutput(
                agent_id=self.agent_id,
                data={"skill": None, "error": "no skill_creation_params in context"},
                cost_usd=0.0,
                skipped=True,
                skip_reason="missing_params",
            )

        try:
            skill, path = await self.create(
                name=params["name"],
                description=params["description"],
                languages=params.get("languages", []),
                frameworks=params.get("frameworks", []),
                examples=params.get("examples", []),
                ctx=ctx,
            )
            return AgentOutput(
                agent_id=self.agent_id,
                data={"skill": skill.model_dump(), "path": str(path)},
                cost_usd=0.0,
            )
        except Exception as e:
            return AgentOutput(
                agent_id=self.agent_id,
                data={"skill": None, "error": str(e)},
                cost_usd=0.0,
                skipped=True,
                skip_reason="creation_error",
            )
