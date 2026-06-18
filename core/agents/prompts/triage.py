# core/agents/prompts/triage.py
from __future__ import annotations
from core.agents.prompts.approaches import get_triage_system  # re-export

TRIAGE_USER_TEMPLATE = """\
Codebase context:
- Root: {root}
- Languages: {languages}
- Frameworks: {frameworks}
- Entry points: {entry_points}
- Repo map (first 100 files):
{repo_map}

Findings to triage ({count} total, deduplicated):
{findings_json}

Return a JSON object:
{{
  "findings": [
    {{
      "dedup_key": "<exact dedup_key from input>",
      "confidence": <0.0-1.0, how certain you are this is a real vuln>,
      "exploit_likelihood": <0.0-1.0, how likely an attacker can exploit this>,
      "reachability": "<one sentence: is this reachable from an attacker entry point and how>",
      "attack_scenario": "<2-3 sentences: exact attack an adversary would perform, including payload>",
      "priority_score": <0.0-10.0, blend of severity + exploit_likelihood + reachability>,
      "status": "open" | "dismissed",
      "false_positive_reason": "<reason if dismissed, null otherwise>",
      "attack_chain": "<if this chains with another finding's dedup_key, name it; else null>"
    }}
  ]
}}
"""
