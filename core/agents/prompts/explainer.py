# core/agents/prompts/explainer.py
from __future__ import annotations
from core.agents.prompts.approaches import get_explainer_system  # re-export

EXPLAINER_USER_TEMPLATE = """\
Explain each open finding below. For each, return:
- The attack scenario (from triage, refine into one sharp sentence a developer will remember)
- Why this specific code is vulnerable (one sentence)
- The exact minimal fix (code or diff)

Findings ({count} open):
{findings_json}

Return:
{{
  "explanations": [
    {{
      "dedup_key": "<exact dedup_key>",
      "explanation": "<attack scenario. vulnerability cause. exact fix.>"
    }}
  ]
}}
"""
