# core/agents/fix.py
from __future__ import annotations
import json
import structlog
from pathlib import Path
from uuid import uuid4

from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.fix import FIX_SYSTEM, FIX_USER_TEMPLATE
from core.model.entities import Fix, FixStatus, ModelTier
from core.model.redaction import redact

log = structlog.get_logger()


class FixAgent:
    agent_id = "fix_generation"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        all_findings: list[dict] = (
            ctx.extra.get("explained_findings")
            or ctx.extra.get("triaged_findings")
            or []
        )

        eligible = [
            f for f in all_findings
            if f.get("status") == "open" and f.get("exploit_likelihood", 0.0) >= 0.6
        ]

        if not eligible:
            return AgentOutput(
                agent_id=self.agent_id,
                data={"fixes": []},
                cost_usd=0.0,
            )

        scan_root = Path(ctx.scan.target_ref)
        fixes: list[dict] = []
        total_cost = 0.0

        for finding in eligible:
            loc = finding.get("location", {})
            file_rel = loc.get("file", "")
            file_path = scan_root / file_rel

            try:
                file_content = file_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, FileNotFoundError):
                file_content = ""

            line_count = file_content.count("\n") + 1
            tier_override = ModelTier.top if line_count > 200 else None

            safe_snippet = redact(loc.get("snippet") or "")
            safe_file_content = redact(file_content)

            user_msg = FIX_USER_TEMPLATE.format(
                rule_id=finding.get("rule_id", ""),
                cwe=finding.get("cwe") or "unknown",
                severity=finding.get("severity", ""),
                file=file_rel,
                line_start=loc.get("line_start", ""),
                line_end=loc.get("line_end", ""),
                snippet=safe_snippet,
                reachability=finding.get("reachability") or "unknown",
                attack_scenario=finding.get("attack_scenario") or "",
                explanation=finding.get("explanation") or "",
                file_content=safe_file_content,
            )

            try:
                result = await ctx.gate.complete(
                    task_type="fix_generation",
                    messages=[
                        {"role": "system", "content": FIX_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    agent_id=self.agent_id,
                    scan_id=ctx.scan.id,
                    tier_override=tier_override,
                )
                total_cost += result.cost_usd
            except Exception as exc:
                log.warning(
                    "fix_agent_gate_error",
                    finding_dedup_key=finding.get("dedup_key"),
                    error=str(exc),
                )
                continue

            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError:
                log.warning(
                    "fix_agent_json_parse_error",
                    dedup_key=finding.get("dedup_key"),
                    content_preview=result.content[:200],
                )
                continue

            fix = Fix(
                finding_id=finding["id"],
                diff=parsed.get("diff", ""),
                test=parsed.get("test") or None,
                explanation=parsed.get("explanation", ""),
                status=FixStatus.proposed,
            )
            fixes.append(fix.model_dump(mode="json"))

        log.info(
            "fix_generation_complete",
            eligible=len(eligible),
            fixes_generated=len(fixes),
            scan_id=str(ctx.scan.id),
        )

        return AgentOutput(
            agent_id=self.agent_id,
            data={"fixes": fixes},
            cost_usd=total_cost,
        )
