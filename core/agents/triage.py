# core/agents/triage.py
from __future__ import annotations
import json
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.agents.prompts.triage import TRIAGE_USER_TEMPLATE, get_triage_system
from core.model.entities import Finding
from core.model.redaction import redact

log = structlog.get_logger()


class TriageAgent:
    agent_id = "triage"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        raw_findings: list[dict] = ctx.extra.get("findings", [])
        if not raw_findings:
            return AgentOutput(agent_id=self.agent_id, data={"triaged_findings": []})

        # Deduplicate by dedup_key before sending to LLM
        seen: set[str] = set()
        unique: list[dict] = []
        for f in raw_findings:
            key = f.get("dedup_key", "")
            if key not in seen:
                seen.add(key)
                unique.append(f)

        cc = ctx.extra.get("code_context", {})

        # Redact snippets before including in prompt
        safe_findings = []
        for f in unique:
            safe_f = dict(f)
            if safe_f.get("location", {}).get("snippet"):
                safe_f["location"] = dict(safe_f["location"])
                safe_f["location"]["snippet"] = redact(safe_f["location"]["snippet"])
            safe_findings.append(safe_f)

        user_msg = TRIAGE_USER_TEMPLATE.format(
            root=cc.get("root", ""),
            languages=", ".join(cc.get("languages", {}).keys()),
            frameworks=", ".join(cc.get("frameworks", [])) or "none detected",
            entry_points=", ".join(cc.get("entry_points", [])) or "none detected",
            repo_map="\n".join(cc.get("repo_map", "").splitlines()[:100]),
            count=len(unique),
            findings_json=json.dumps(safe_findings, indent=2, default=str),
        )

        result = await ctx.gate.complete(
            task_type="triage",
            messages=[
                {"role": "system", "content": get_triage_system(ctx.approach)},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )

        try:
            parsed = json.loads(result.content)
            triaged = parsed.get("findings", [])
        except json.JSONDecodeError:
            log.warning("triage_json_parse_error", content_preview=result.content[:200])
            # Fall back: return all findings with defaults
            triaged = [
                {**f, "confidence": 0.5, "exploit_likelihood": 0.5,
                 "reachability": "unknown", "attack_scenario": "triage parse failed",
                 "priority_score": 5.0, "status": "open", "false_positive_reason": None,
                 "attack_chain": None}
                for f in unique
            ]

        # Merge triage enrichments back onto original finding dicts
        enrichment_map = {t["dedup_key"]: t for t in triaged}
        output_findings = []
        for f in unique:
            enriched = dict(f)
            enrich = enrichment_map.get(f.get("dedup_key", ""), {})
            enriched.update({
                "confidence": enrich.get("confidence", 0.5),
                "exploit_likelihood": enrich.get("exploit_likelihood", 0.5),
                "reachability": enrich.get("reachability", "unknown"),
                "attack_scenario": enrich.get("attack_scenario", ""),
                "priority_score": enrich.get("priority_score", 5.0),
                "status": enrich.get("status", "open"),
                "false_positive_reason": enrich.get("false_positive_reason"),
                "attack_chain": enrich.get("attack_chain"),
            })
            output_findings.append(enriched)

        # Sort by priority_score descending
        output_findings.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        log.info("triage_complete", total=len(unique), open_count=sum(1 for f in output_findings if f["status"] == "open"),
                 dismissed_count=sum(1 for f in output_findings if f["status"] == "dismissed"),
                 scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"triaged_findings": output_findings},
            cost_usd=result.cost_usd,
        )
