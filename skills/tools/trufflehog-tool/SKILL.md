---
name: trufflehog-tool
description: How to invoke TruffleHog, parse JSON output, and handle secrets safely
version: 1.0.0
family: tools
tools_allowed: []
---

# TruffleHog Tool Wrapper

## Invocation (filesystem)
```bash
trufflehog filesystem \
  --directory /path/to/repo \
  --json \
  --no-update
```

## Invocation (git history)
```bash
trufflehog git \
  file:///path/to/repo \
  --json \
  --no-update
```

## Output format
One JSON object per line (ndjson). Key fields:
- `DetectorName` — type of secret (e.g., "Anthropic", "GitHub")
- `Raw` / `RawV2` — the actual secret value — **REDACT IMMEDIATELY, never persist**
- `Verified` — boolean, whether TruffleHog confirmed the secret is live
- `SourceMetadata.Data.Filesystem.file` / `.line` — location

## Handling raw values
1. Extract `Raw` or `RawV2` to compute `fingerprint = sha256(raw)`
2. Discard `Raw`/`RawV2` immediately
3. Store only: fingerprint, DetectorName, file path, line number

## Severity
All secrets findings are `critical` (CWE-798, OWASP A07:2021).
`Verified=true` means the key is confirmed live — treat as incident, not just a finding.
