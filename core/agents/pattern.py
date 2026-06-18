# core/agents/pattern.py
from __future__ import annotations
import json
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.pattern import PATTERN_SYSTEM, PATTERN_USER_TEMPLATE

log = structlog.get_logger()


class PatternAgent:
    agent_id = "pattern_analysis"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        findings: list[dict] = (
            ctx.extra.get("triaged_findings")
            or ctx.extra.get("findings")
            or []
        )

        cc = ctx.extra.get("code_context", {})
        languages = ", ".join(cc.get("languages", {}).keys()) or "unknown"
        frameworks = ", ".join(cc.get("frameworks", [])) or "none detected"

        # Identify which scanners contributed findings
        scanners = sorted({f.get("source_tool", "unknown") for f in findings})

        user_msg = PATTERN_USER_TEMPLATE.format(
            target_ref=ctx.scan.target_ref,
            languages=languages,
            frameworks=frameworks,
            count=len(findings),
            scanners=", ".join(scanners) or "none",
            findings_json=json.dumps(findings, indent=2, default=str),
        )

        result = await ctx.gate.complete(
            task_type="pattern_analysis",
            messages=[
                {"role": "system", "content": PATTERN_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )

        try:
            parsed = json.loads(result.content)
        except json.JSONDecodeError:
            log.warning(
                "pattern_json_parse_error",
                content_preview=result.content[:200],
                scan_id=str(ctx.scan.id),
            )
            parsed = {
                "hotspots": [],
                "vulnerability_clusters": [],
                "gap_analysis": {"observed_categories": scanners, "potential_gaps": []},
                "recommendations": [],
            }

        log.info(
            "pattern_analysis_complete",
            hotspot_count=len(parsed.get("hotspots", [])),
            cluster_count=len(parsed.get("vulnerability_clusters", [])),
            scan_id=str(ctx.scan.id),
        )

        return AgentOutput(
            agent_id=self.agent_id,
            data={"pattern_summary": parsed},
            cost_usd=result.cost_usd,
        )
