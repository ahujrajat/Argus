# core/agents/explainer.py
from __future__ import annotations
import json
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.explainer import EXPLAINER_USER_TEMPLATE, get_explainer_system
from core.model.redaction import redact

log = structlog.get_logger()


class ExplainerAgent:
    agent_id = "explainer"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        all_findings: list[dict] = ctx.extra.get("triaged_findings", [])
        open_findings = [f for f in all_findings if f.get("status") == "open"]

        if not open_findings:
            return AgentOutput(
                agent_id=self.agent_id,
                data={"explained_findings": all_findings},
                cost_usd=0.0,
            )

        # Redact snippets before sending to LLM
        safe = []
        for f in open_findings:
            sf = dict(f)
            if sf.get("location", {}).get("snippet"):
                sf["location"] = dict(sf["location"])
                sf["location"]["snippet"] = redact(sf["location"]["snippet"])
            safe.append(sf)

        user_msg = EXPLAINER_USER_TEMPLATE.format(
            count=len(safe),
            findings_json=json.dumps(safe, indent=2, default=str),
        )

        result = await ctx.gate.complete(
            task_type="explanation",
            messages=[
                {"role": "system", "content": get_explainer_system(ctx.approach)},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )

        try:
            parsed = json.loads(result.content)
            explanations = {e["dedup_key"]: e["explanation"] for e in parsed.get("explanations", [])}
        except (json.JSONDecodeError, KeyError):
            log.warning("explainer_json_parse_error", content_preview=result.content[:200])
            explanations = {}

        output = []
        for f in all_findings:
            enriched = dict(f)
            if f.get("status") == "open":
                enriched["explanation"] = explanations.get(f["dedup_key"], "")
            output.append(enriched)

        return AgentOutput(
            agent_id=self.agent_id,
            data={"explained_findings": output},
            cost_usd=result.cost_usd,
        )
