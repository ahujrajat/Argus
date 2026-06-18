# core/agents/prompts/fix.py
from __future__ import annotations

FIX_SYSTEM = (
    "You are a security patch engineer. "
    "Generate the minimal, correct unified diff that eliminates the described vulnerability. "
    "Do not change unrelated code. "
    "Do not add logging or comments unless they are part of the fix. "
    "Return ONLY valid JSON."
)

FIX_USER_TEMPLATE = """\
Generate a security fix for the following vulnerability.

Rule: {rule_id}
CWE: {cwe}
Severity: {severity}
File: {file}
Lines: {line_start}-{line_end}

Vulnerable snippet:
{snippet}

Reachability: {reachability}
Attack scenario: {attack_scenario}
Explanation: {explanation}

Full file content (for context):
```
{file_content}
```

Return exactly this JSON (no other text):
{{
  "diff": "<unified diff in git diff -u format, paths prefixed a/ and b/>",
  "test": "<pytest test snippet that verifies the fix, or null>",
  "explanation": "<one sentence describing what was changed and why>",
  "confidence": <float 0.0-1.0>
}}
"""
