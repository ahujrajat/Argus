# Security of the Platform

## Least privilege
- Agent and skill contexts carry only the tools they need
- Scanner and analysis paths are read-only
- Write operations (fix apply, PR creation) are separate gated capabilities (Phase 2+)

## Sandboxed execution
- All scanner tools (semgrep, trufflehog) run via subprocess with timeout
- DAST (Phase 6) runs inside an isolated container with no access to platform secrets
- Model-suggested code is never executed without explicit sandboxed validation

## Secret hygiene
- Secrets found during scanning are redacted immediately on parse
- Only `fingerprint = sha256(raw)` + location is stored
- The raw value never appears in: logs, database text fields, LLM prompts, API responses, or the UI
- `core.model.redaction.redact()` and `redact_dict()` are applied to all log writes
  and all prompt assembly paths

## Zero-retention
- finRouter Gateway adds provider-specific zero-retention headers where supported
- Source code never leaves the operator's boundary (self-hosted deployment)
- Operators should review provider data handling policies for providers without zero-retention support

## DAST authorization (Phase 6)
- DAST refuses to run without an active `TargetAuthorization` record
- `TargetAuthorization` requires `owner_confirmed=True`, explicit scope rules, non-production
  environment by default, rate limits, and an expiry
- Every DAST run writes an `AuditLogEntry` with the authorization reference

## Audit log
Every privileged operation writes an `AuditLogEntry`:
- Fix application
- Skill activation / deactivation
- DAST run start/stop
- Config changes (model tiers, budget policy)

## Human-in-the-loop gates
- Fix application requires human approval (propose-and-review by default)
- Skill activation from candidate → active requires human approval
- Auto-apply mode is off by default and must be explicitly enabled per fix class

## Own SBOM
Argus scans its own dependencies and produces a CycloneDX SBOM.
The platform is expected to pass its own security checks.

## Data flow summary
```
Developer machine → Argus API (self-hosted) → finRouter Gateway (self-hosted)
  → Provider API (Anthropic/OpenAI/etc., with zero-retention)

Source code, findings, fixes: never leave operator boundary
LLM prompts: contain code snippets (redacted of secrets) + finding metadata
Provider responses: explanations and fix diffs only
```
