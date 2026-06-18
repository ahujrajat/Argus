# Argus FAQ

## General

**Q: What is Argus and how does it differ from running Semgrep or Snyk directly?**

Argus is an orchestration layer, not a replacement for individual tools. It runs Semgrep, TruffleHog, Grype, Checkov, Nuclei, and ZAP as deterministic zero-token adapters, then uses AI agents only for the tasks deterministic tools cannot do well: dedup, severity scoring, false-positive filtering, explanation, fix generation, and cross-finding pattern analysis. The result is actionable, prioritized findings with AI-written diffs — not a raw JSON dump.

**Q: Which LLM providers does Argus support?**

Argus is provider-agnostic through the finRouter Gateway sidecar. Out of the box: Anthropic (Claude), OpenAI (GPT-4o, o1), Google (Gemini 2.x), Mistral, and Groq. Provider selection is controlled by `config/model_tiers.yaml` — no code change required to switch providers.

**Q: Does Argus send my source code to LLM providers?**

Argus routes all model calls through the finRouter Gateway which includes zero-retention headers (`anthropic-beta: prompt-caching-2024-07-31` and `x-zero-retention: true` where supported). Source code is processed within your operator boundary. You control which provider keys are in scope.

**Q: Can I run Argus without any LLM provider keys?**

Yes, partially. Scanner adapters (Semgrep, Grype, Checkov, Nuclei, ZAP) run with zero tokens. The triage, explainer, fix, and pattern agents will return `skipped` results if the finRouter Gateway is unreachable. The scan completes with raw findings only.

---

## Setup & Infrastructure

**Q: What databases does Argus require?**

PostgreSQL 16 (primary store) and optionally MinIO / S3-compatible object storage for SARIF artifact archiving. Both ship in `docker-compose.yml`. For development, only PostgreSQL is required.

**Q: How do I run the migrations?**

```bash
alembic upgrade head
```

If you add new models, generate a migration with:
```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

**Q: Why does `docker compose up -d` start a `finrouter-gateway` service?**

All model calls in Argus route through the finRouter Gateway — a Fastify sidecar that wraps provider SDKs, enforces org-level budget hierarchies, encrypts API keys (AES-256-GCM), and injects zero-retention headers. The Python core never calls Anthropic/OpenAI/Google directly.

**Q: Can I use Argus without Docker?**

Yes. Start PostgreSQL and optionally MinIO any way you like, set `DATABASE_URL` in `.env`, and run the FastAPI app directly with `uvicorn`. The finRouter Gateway is a Node.js service in `surfaces/finrouter-gateway/` — run it with `npm start` if you need model calls.

---

## Scanners

**Q: What happens if a scanner binary (e.g., `grype`) is not installed?**

The adapter catches `FileNotFoundError` and returns an `AgentOutput` with `skipped=True, skip_reason="grype_not_installed"`. The scan continues with the remaining agents. No error is surfaced to the user unless all scanner agents are skipped.

**Q: How does Argus handle DAST scanner authorization?**

Before any DAST agent (Nuclei, ZAP) executes, the orchestrator queries `TargetAuthorizationRow` for the scan's `target_ref`. If no valid, non-expired record exists, the adapter returns `skip_reason="no_dast_authorization"`. Create an authorization via `POST /api/v1/authorizations` with an expiry date, scope rules, and owner confirmation.

**Q: Can I add my own scanner?**

Yes. Implement the adapter pattern:
```python
class MyToolAdapter:
    agent_id = "my_tool"
    async def scan(self, ctx: AgentContext) -> AgentOutput: ...
```
Register it in `core/agents/orchestrator.py` `_AGENT_REGISTRY` and add it to `_SCANNER_AGENTS`. Then reference it by class name in a pipeline config YAML.

**Q: How are secrets redacted?**

The `core/model/redaction.py` module runs before any DB write, log write, model prompt, or UI serialization. Raw secret values are replaced with a fingerprint + location tuple. Only the fingerprint is stored and displayed.

---

## Pipeline Configs

**Q: Can I modify the built-in pipeline configs?**

Factory defaults (`full-scan`, `pr-check`, `real-time`, etc.) are seeded as `is_factory=True` and cannot be modified or deleted via the API. Clone one with `POST /api/v1/pipelines` and customize the clone.

**Q: How does the orchestrator determine node execution order?**

The orchestrator resolves the pipeline definition from the `PipelineConfig` row, topologically sorts nodes by dependency edges, and executes independent nodes in parallel using `asyncio.gather`. Edge conditions are evaluated against the prior node's `AgentOutput`.

**Q: What is `_AGENT_REGISTRY` and why do tests patch it?**

`_AGENT_REGISTRY` is a module-level dict built at import time in `core/agents/orchestrator.py`. It maps string agent names from pipeline YAMLs to agent classes. Because it's built at import time, `patch("core.agents.orchestrator.SomeAdapter")` after import has no effect on the registry. Tests that need to inject fakes must use `patch.dict(orch_module._AGENT_REGISTRY, {"AgentName": FakeClass})`.

---

## Skills

**Q: What is a skill?**

A YAML file that carries security guidance (rules, heuristics, remediation advice) injected into AI agent prompts at scan time. Skills are matched to a scan by language and framework. A skill with `frameworks: [django]` will only activate for scans that detected Django; a skill with `frameworks: []` activates for all scans.

**Q: How does the SkillCreatorAgent work?**

Pass `skill_creation_params` in `ctx.extra` (name, description, languages, frameworks, examples). The agent calls the LLM via GovernanceGate, parses the JSON response into a `Skill` object, validates it, and saves it to `core/skills/generated/`. Generated skills are available immediately; activate them via `POST /api/v1/skills/{name}/activate`.

**Q: Why does activating or disabling a skill require a database dependency?**

Every privileged operation writes an `AuditLogEntry`. The skills router accepts a `db: AsyncSession = Depends(get_db)` parameter to write the entry in the same request. This ensures the audit trail is transactional with the state change.

---

## Cost & Budget

**Q: How does the per-scan budget work?**

`GovernanceGate.complete()` checks cumulative scan cost against `budget_policy.yaml` on every model call. At 80% of `hard_limit_usd`, it emits a `budget_warning` SSE event and logs. At 100%, it raises `BudgetExceeded` — the orchestrator catches this, marks all remaining agents as `skipped`, and closes the scan. The total cost is still recorded.

**Q: Where do I see cost per scan?**

- `GET /api/v1/cost/ledger` — per-call entries with model, tier, tokens, and USD
- `GET /api/v1/cost/summary` — rolled-up by scan, model, and tier
- Dashboard → Cost & Usage tab

**Q: How is model tier chosen per task?**

`config/model_tiers.yaml` → `task_defaults` maps task type to a tier. The GovernanceGate picks the `(provider, model_id)` pair for that tier from the same file. Escalation rules can upgrade from `balanced` to `top` when confidence is low or the diff is large.

---

## API & Integration

**Q: How do I stream live scan progress?**

`GET /api/v1/scans/{id}/events` returns a server-sent event stream. Events include `agent_started`, `llm_call`, `agent_completed`, `budget_warning`, `gate_required`, and `scan_completed`. Connect with any SSE client:

```javascript
const es = new EventSource(`/api/v1/scans/${id}/events`);
es.onmessage = e => console.log(JSON.parse(e.data));
```

**Q: Can I trigger multiple scans at once?**

Yes. `POST /api/v1/scans/batch` accepts a list of targets and a pipeline config name. It validates that all pipeline configs exist before inserting any scan rows — the request is atomic.

```json
{
  "targets": ["/repo/service-a", "/repo/service-b"],
  "pipeline_config_name": "pr-check"
}
```

**Q: How do I apply a fix?**

`POST /api/v1/fixes/{id}/apply` is a human gate. If a VCS token is configured (GitHub or GitLab), it opens a pull request with the diff. Without a VCS token it applies the patch locally. Rejection with `POST /api/v1/fixes/{id}/reject` records the reason in the audit log.

---

## Audit & Compliance

**Q: What operations are audited?**

Every write to these endpoints records an `AuditLogEntry`:
- `POST /fixes/{id}/apply` and `reject`
- `POST /skills/{name}/activate` and `disable`
- `PUT /config/model-tiers`
- `PUT /config/budget-policy`
- `POST /authorizations` and `DELETE /authorizations/{id}`

**Q: How do I query the audit log?**

`GET /api/v1/audit/?limit=100` returns the most recent entries (max 500). Each entry includes `actor`, `action`, `target`, `before`, `after`, and `timestamp`.

**Q: Does Argus scan itself?**

Yes — the design calls for Argus to run its own scanner suite and produce a CycloneDX SBOM. The self-scan pipeline uses the `comprehensive-scan` config targeting the Argus repo root.

---

## Testing & CI

**Q: How do I run the tests without a database?**

```bash
pytest --ignore=tests/e2e -q
```

This runs all 337 unit and integration tests. E2E tests in `tests/e2e/` require a live PostgreSQL connection.

**Q: My test patches the wrong thing and the real scanner runs — what's happening?**

Scanner class names like `SemgrepAdapter` are resolved through `_AGENT_REGISTRY` at orchestrator import time. Patching the class after import (`patch("core.agents.orchestrator.SemgrepAdapter")`) does not change the registry entry. Use:
```python
from core.agents import orchestrator as orch_module
with patch.dict(orch_module._AGENT_REGISTRY, {"SemgrepAdapter": FakeSemgrep}):
    ...
```

**Q: How does the eval harness work?**

`python evals/harness.py --findings-file <path> --ground-truth evals/fixtures/ground_truth.json` computes precision, recall, FP rate, and F1 against labeled known findings. A ±3 line tolerance is applied for line number matching. FP rate > 40% exits non-zero — wire this to CI to catch regressions.

---

## Suppression Rules (Phase 10)

**Q: How do I suppress a known false positive?**

Three ways:

1. **API** — `POST /api/v1/suppressions` with `pattern_type: "fingerprint"` and the finding's `dedup_key` as `pattern`.
2. **.argusignore** — Add a line to `.argusignore` at the repo root:
   ```
   fp:<dedup_key>        # suppress by fingerprint
   path:tests/**         # suppress all findings in tests/
   rule:semgrep.sqli     # suppress a specific rule
   ```
3. **Finding status** — `PATCH /api/v1/findings/{id}` with `{"status": "dismissed"}` marks the finding without creating a persistent suppression rule.

**Q: What is the difference between `fingerprint`, `path_glob`, and `rule_id` suppressions?**

- `fingerprint` — exact match on `dedup_key`; most precise; re-suppresses if the finding recurs anywhere
- `path_glob` — fnmatch on file path; good for suppressing entire directories (`vendor/**`, `tests/**`)
- `rule_id` — suppresses every finding from a specific rule ID; use when a rule has too many FPs for a given project

**Q: Can suppression rules expire?**

Yes. Provide `expires_at` (ISO 8601 UTC) when creating a rule. `GET /api/v1/suppressions` filters out expired rules by default; pass `?include_expired=true` to see them.

---

## Scheduled Scans (Phase 10)

**Q: How do I schedule a recurring scan?**

```bash
POST /api/v1/schedules
{
  "name": "nightly-main",
  "cron_expr": "0 2 * * *",
  "pipeline_config_name": "full-scan",
  "target_ref": "github.com/org/repo"
}
```

Standard 5-field cron (`minute hour day-of-month month day-of-week`). The built-in validator rejects expressions that are not parseable by `croniter`.

**Q: How does the background scheduler work?**

A long-running `asyncio.Task` starts in the FastAPI lifespan and polls every 30 seconds. Any `ScheduledScanRow` whose `next_run_at ≤ now` and `enabled = true` gets a new `ScanRow` created with status `pending`, and `next_run_at` is advanced to the next cron fire time.

**Q: Can I temporarily pause a schedule without deleting it?**

Yes. `PATCH /api/v1/schedules/{id}/disable` sets `enabled = false` and clears `next_run_at`. `PATCH /api/v1/schedules/{id}/enable` re-enables it and recomputes the next fire time from now.

---

## Compliance Report (Phase 10)

**Q: How do I generate a compliance report for a scan?**

`GET /api/v1/scans/{id}/report` returns:
- `severity_breakdown` — count per severity level (critical / high / medium / low / info)
- `owasp_top10` — top-10 OWASP categories by finding count
- `cwe_top10` — top-10 CWE identifiers by finding count
- `risk_score` — weighted sum (critical×10 + high×5 + medium×2 + low×1)
- `total_findings` — raw count

**Q: How is the risk score calculated?**

```
risk_score = (critical × 10) + (high × 5) + (medium × 2) + (low × 1)
```

Info and negligible findings do not contribute. This is intentionally simple — use it as a relative trend indicator across scans, not an absolute severity measure.

---

## Policy Engine (Phase 11)

**Q: How do I define a security policy?**

`POST /api/v1/policies` with any combination of threshold fields:
```json
{
  "name": "production-gate",
  "max_critical": 0,
  "max_high": 3,
  "max_risk_score": 30,
  "blocked_owasp": ["A03:2021"],
  "block_on_any_critical": true
}
```
All fields are optional — omitting a field means that constraint is not checked.

**Q: How does policy evaluation work?**

`POST /api/v1/policies/{policy_id}/evaluate/{scan_id}` builds a compliance report for the scan on-the-fly, evaluates it against the policy, and returns a `passed` boolean plus a list of `violations`. Each violation names the rule (`max_high`, `blocked_owasp:A03:2021`, etc.), the actual value, and the limit.

**Q: How do I block a CI/CD pipeline if a scan fails a policy?**

Use `scripts/ci-gate.sh` (or `scripts/ci-gate.bat` on Windows):
```bash
./scripts/ci-gate.sh --scan-id <uuid> --policy-id <policy-uuid>
```
Exit code is 0 on pass, 1 on policy failure. Without `--policy-id`, all active policies are evaluated and any failure causes a non-zero exit.

**Q: Can I have multiple policies?**

Yes. Create as many as needed (e.g. one for PRs with `max_high=5` and one for production deployments with `max_critical=0`). Evaluate against any specific policy, or omit `--policy-id` to check all active policies at once.

**Q: How do I deactivate a policy without deleting it?**

Pass `"active": false` when creating the policy, or update the definition via `PUT /api/v1/policies/{id}` (not yet implemented — currently recreate with `active=false`). Inactive policies are excluded from the `active_only=true` list endpoint and the CI gate default evaluation.

---

## Bulk Operations (Phase 11)

**Q: How do I suppress many findings at once?**

`POST /api/v1/findings/bulk-suppress` with a list of finding IDs (max 500 per request):
```json
{
  "finding_ids": ["id1", "id2", "id3"],
  "reason": "known false positives from vendor library"
}
```
This creates a `fingerprint` suppression rule for each finding's `dedup_key` and marks the finding status as `suppressed`. Findings without a `dedup_key` are skipped (reported in `skipped_ids`).

**Q: What is the difference between bulk-suppress and bulk-dismiss?**

- `bulk-suppress` — creates permanent suppression rules by fingerprint; future scans will automatically suppress the same finding
- `bulk-dismiss` — marks findings as dismissed in the current context; no suppression rule is created; future scans will still report the finding

**Q: How do I assign findings to a team member for triage?**

`POST /api/v1/findings/bulk-assign`:
```json
{
  "finding_ids": ["id1", "id2"],
  "assignee": "alice@example.com"
}
```
The assignee is stored in the finding's `location` JSONB under the key `"assignee"`. The dashboard and API responses include this field.
