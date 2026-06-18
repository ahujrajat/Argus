# core/agents/prompts/pattern.py
from __future__ import annotations

PATTERN_SYSTEM = """You are a security pattern analyst. You analyze triaged vulnerability findings \
from a security scan to identify cross-cutting patterns, hotspot files, and coverage gaps. \
Your goal is to give security teams actionable intelligence that goes beyond individual findings.

Always respond with valid JSON matching the schema in the user message. Never include markdown fences \
or explanatory text outside the JSON object."""


PATTERN_USER_TEMPLATE = """\
Analyze the following security scan findings and produce a pattern summary.

Scan target: {target_ref}
Languages detected: {languages}
Frameworks detected: {frameworks}
Total findings: {count}
Scanners used: {scanners}

Findings (triaged, JSON):
{findings_json}

Respond with a JSON object with exactly these keys:

{{
  "hotspots": [
    {{
      "file": "<file path>",
      "finding_count": <int>,
      "dominant_cwe": "<CWE-NNN or null>",
      "summary": "<one sentence about why this file is high risk>"
    }}
  ],
  "vulnerability_clusters": [
    {{
      "name": "<cluster name>",
      "description": "<what makes these findings related>",
      "finding_count": <int>,
      "cwe_list": ["<CWE-NNN>"],
      "affected_files": ["<file path>"]
    }}
  ],
  "gap_analysis": {{
    "observed_categories": ["<scanner names actually used>"],
    "potential_gaps": ["<one sentence per gap, e.g. 'No IaC scanner results despite Terraform files detected'>"]
  }},
  "recommendations": [
    "<actionable recommendation string>"
  ]
}}

Rules:
- Include up to 5 hotspots, sorted by finding_count descending
- Include up to 5 vulnerability clusters (group by CWE or attack pattern)
- Include up to 4 potential gaps (only real gaps — do not invent gaps for scanners already used)
- Include up to 5 recommendations, ordered by impact
- If there are no findings, return empty arrays and a gap_analysis noting all scan types are coverage gaps"""
