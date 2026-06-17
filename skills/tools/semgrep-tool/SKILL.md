---
name: semgrep-tool
description: How to invoke Semgrep, parse its SARIF output, and map results to Findings
version: 1.0.0
family: tools
tools_allowed: []
---

# Semgrep Tool Wrapper

## Invocation
```bash
semgrep scan \
  --config auto \
  --sarif \
  --output results.sarif \
  --timeout 120 \
  --no-git-ignore \
  /path/to/repo
```

Exit codes: 0 = no findings, 1 = findings present, 2+ = error.

## SARIF output structure
- `runs[0].tool.driver.rules[]` — rule metadata (id, name, tags including CWE/OWASP)
- `runs[0].results[]` — each result has ruleId, level, locations, message

## Level → Severity mapping
- error → high (upgrade to critical if message contains "critical")
- warning → medium
- note → low
- none → info

## CWE extraction
Rules carry tags like `["CWE-89", "OWASP-A03:2021"]`.
Extract the first `CWE-*` tag as `cwe`. Extract first `OWASP-*` as `owasp_category`.

## Performance notes
`--config auto` downloads rules on first run. Cache `~/.semgrep/` across CI runs.
For large repos (>10k files), add `--max-target-bytes 1000000` to skip binary files.
