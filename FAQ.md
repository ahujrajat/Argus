# Argus FAQ

A practical Q&A covering Argus from the executive overview down to implementation detail. Start at the top for the non-technical picture; jump to a section below for specifics.

**Contents:** [The Big Picture](#the-big-picture) · [Choosing a Scan](#choosing-a-scan-mode-pipeline-approach) · [Setup](#setup--infrastructure) · [Scanners](#scanners) · [AI Agents](#ai-agents) · [Pipelines](#pipeline-configs) · [Skills](#skills) · [Cost & Budget](#cost--budget) · [API](#api--integration) · [Audit & Compliance](#audit--compliance) · [Testing](#testing--ci) · [Suppressions](#suppression-rules) · [Schedules](#scheduled-scans) · [Compliance Reports](#compliance-report) · [Policies](#policy-engine) · [Bulk Ops](#bulk-operations) · [RBAC](#multi-tenancy--rbac) · [Integrations](#integrations) · [Analytics](#analytics) · [Production](#production-features)

---

## The Big Picture

**Q: In one sentence, what is Argus?**

Argus is a security platform that runs all your scanners, uses AI to tell you which findings actually matter and how to fix them, and meters every AI dollar so the whole thing stays affordable and auditable.

**Q: What problem does it solve?**

Three at once: (1) **alert fatigue** — scanners produce thousands of low-signal findings, and Argus deduplicates, ranks, and filters them; (2) **tool sprawl** — six scanner types unified behind one API and one data model; (3) **unpredictable AI cost** — a hard budget gate on every model call, so "AI security" never becomes a runaway bill.

**Q: Is this for an individual developer or a large enterprise?**

Both, with the same platform. A solo developer can scan locally and apply AI fixes from VS Code. An enterprise can deploy it org-wide with multi-tenancy, RBAC, CI/CD gating, scheduled scans, compliance reporting, and integrations with Jira/PagerDuty/Slack/Prometheus. The guardrails (budget, governance, audit) are identical at both scales.

**Q: How is this different from just running Semgrep or buying Snyk?**

Argus is an orchestration and intelligence layer, not a replacement for any single tool. It *runs* Semgrep, TruffleHog, Grype, Checkov, Nuclei, and ZAP as deterministic zero-token adapters, then adds what those tools don't do: cross-tool dedup, AI triage and false-positive filtering, plain-language explanations, diff-ready fixes, cross-finding pattern analysis, cost governance, and a full audit trail. The output is a short list of prioritized, explained, fixable issues — not a raw JSON dump.

**Q: What does a scan actually produce?**

Ranked findings (each with severity, CWE/OWASP mapping, exploit likelihood, and a plain-language explanation), AI-drafted fixes with tests for confirmed issues, a CycloneDX SBOM, an OWASP/CWE compliance report, and a complete cost + audit record of everything the scan did.

---

## Choosing a Scan: Mode, Pipeline, Approach

**Q: What are the three "dials" on a scan?**

Every `POST /api/v1/scans` accepts three independent parameters that combine freely:

1. **`mode`** — *when & how much*: `at_rest` (full audit), `batch` (many targets), `real_time` (only changed files).
2. **`pipeline_config_name`** — *which tools run*: a named recipe like `full-scan`, `pr-check`, `sca-scan`, etc.
3. **`approach`** — *through which lens*: the analytical mindset the AI adopts (six options below).

**Q: What's the difference between the scan modes?**

| Mode | Behavior | Use it for |
|---|---|---|
| `at_rest` | Full audit of a target (default) | Baselining, scheduled audits |
| `batch` | Several targets scanned together | Org-wide / monorepo sweeps |
| `real_time` | Computes a git diff and scans only changed files | The developer inner loop / PR feedback |

`real_time` is what keeps PR feedback fast — it never re-scans the whole repo, only what you touched.

**Q: What are the six security approaches, and why would I change them?**

The `approach` re-frames how AI **triages and explains the same findings**, so one scan can serve very different audiences:

| Approach | The AI's mindset |
|---|---|
| `penetration_testing` *(default)* | Attacker's view: reachability, minimal payload, blast radius, exploit chains. |
| `adversary_emulation` | Maps findings to MITRE ATT&CK techniques and the threat groups that use them. |
| `breach_and_attack_simulation` | Would WAF / SIEM / EDR / IDS catch it? Flags control gaps. |
| `assumed_breach` | Post-compromise only: privilege escalation, lateral movement, persistence. |
| `blue_team` | Detection opportunities, log sources, SIEM signatures, hardening — no exploit payloads. |
| `purple_team` | Both sides: the attack technique *and* the detection that should fire. |

Example: a security operations team running `blue_team` gets the log entry and detection rule for each finding; a red team running `assumed_breach` sees only the findings useful to an attacker who is already inside.

**Q: Do I have to set all three every time?**

No. Sensible defaults apply: `mode=at_rest`, `pipeline_config_name=full-scan`, `approach=penetration_testing`. Override only the dial you care about.

---

## Setup & Infrastructure

**Q: What databases does Argus require?**

PostgreSQL 16 (primary store) and optionally MinIO / S3-compatible object storage for SARIF artifact archiving. Both ship in `docker-compose.yml`. For development, only PostgreSQL is required.

**Q: How do I run the migrations?**

```bash
alembic upgrade head
```
If you add new models, generate a migration with `alembic revision --autogenerate -m "describe change"` then `alembic upgrade head`.

**Q: Why does `docker compose up -d` start a `finrouter-gateway` service?**

All model calls route through the finRouter Gateway — a Fastify sidecar that wraps provider SDKs, enforces org-level budget hierarchies, encrypts API keys (AES-256-GCM), and injects zero-retention headers. The Python core never calls Anthropic/OpenAI/Google directly.

**Q: Can I use Argus without Docker?**

Yes. Start PostgreSQL (and optionally MinIO) however you like, set `DATABASE_URL` in `.env`, and run the FastAPI app with `uvicorn`. The finRouter Gateway is a Node.js service in `surfaces/finrouter-gateway/` — run it with `npm start` if you need model calls.

**Q: Which LLM providers are supported?**

Argus is provider-agnostic through the finRouter Gateway. Out of the box: Anthropic (Claude), OpenAI, Google (Gemini), Mistral, and Groq. Provider and model selection is controlled by `config/model_tiers.yaml` — no code change to switch.

**Q: Does Argus send my source code to LLM providers?**

Model calls route through the finRouter Gateway with zero-retention headers where the provider supports them. Source is processed within your operator boundary, and you control which provider keys are in scope. Scanners run entirely locally with no model calls at all.

**Q: Can I run Argus without any LLM provider keys?**

Yes, partially. All scanner adapters run with zero tokens. The triage, explainer, fix, and pattern agents return `skipped` results if the gateway is unreachable, and the scan completes with raw (deduplicated) findings only.

---

## Scanners

**Q: What happens if a scanner binary (e.g., `grype`) is not installed?**

The adapter catches `FileNotFoundError` and returns an `AgentOutput` with `skipped=True, skip_reason="grype_not_installed"`. The scan continues with the remaining agents; no error surfaces unless every scanner is skipped.

**Q: How does Argus handle DAST scanner authorization?**

Before any DAST agent (Nuclei, ZAP) runs, the orchestrator queries `TargetAuthorizationRow` for the scan's `target_ref`. With no valid, non-expired record, the adapter returns `skip_reason="no_dast_authorization"`. Create one via `POST /api/v1/authorizations` with an expiry, scope rules, and owner confirmation.

**Q: Can I add my own scanner?**

Yes:
```python
class MyToolAdapter:
    agent_id = "my_tool"
    async def scan(self, ctx: AgentContext) -> AgentOutput: ...
```
Register it in `core/agents/orchestrator.py` `_AGENT_REGISTRY`, add it to `_SCANNER_AGENTS`, then reference it by class name in a pipeline config YAML.

**Q: How are secrets redacted?**

`core/model/redaction.py` runs before any DB write, log write, model prompt, or UI serialization. Raw secret values are replaced with a fingerprint + location tuple; only the fingerprint is stored and displayed.

---

## AI Agents

**Q: Which agents run, and in what order?**

A typical full scan: `IngestionAgent` (detect languages/frameworks) → scanner adapters (deterministic) → `TriageAgent` (confirm, score, filter) → `ExplainerAgent` (plain-language risk) → `FixAgent` (diff + test). `PatternAgent` connects findings into systemic risks; `SkillCreatorAgent` authors new skills on request. The exact topology comes from the pipeline config, not hardcoding.

**Q: Why do triage and explanations change when I change the `approach`?**

The `TriageAgent` and `ExplainerAgent` load an approach-specific system prompt (see `core/agents/prompts/approaches.py`). The findings are the same; the lens — attacker, defender, threat-intel, control-validation — changes.

**Q: Do AI agents ever run before deduplication?**

No. Deterministic scanning and dedup happen first so you never pay an LLM to analyze a duplicate finding. This is the "deterministic-first" principle.

---

## Pipeline Configs

**Q: Can I modify the built-in pipeline configs?**

Factory defaults (`full-scan`, `pr-check`, `real-time`, etc.) are seeded as `is_factory=True` and cannot be modified or deleted via the API. Clone one with `POST /api/v1/pipelines` and customize the clone.

**Q: How does the orchestrator determine node execution order?**

It resolves the pipeline definition from the `PipelineConfig` row, topologically sorts nodes by dependency edges, and executes independent nodes in parallel via `asyncio.gather`. Edge conditions are evaluated against the prior node's `AgentOutput`.

**Q: What is `_AGENT_REGISTRY` and why do tests patch it?**

It's a module-level dict built at import time in `core/agents/orchestrator.py` mapping agent names (from pipeline YAMLs) to classes. Because it's built at import time, `patch("core.agents.orchestrator.SomeAdapter")` after import has no effect. Tests must use `patch.dict(orch_module._AGENT_REGISTRY, {"AgentName": FakeClass})`.

---

## Skills

**Q: What is a skill?**

A YAML file carrying security guidance (rules, heuristics, remediation advice) injected into AI agent prompts at scan time. Skills are matched to a scan by language and framework: a skill with `frameworks: [django]` activates only for scans where Django was detected; `frameworks: []` activates for all.

**Q: How does the system "adapt" to my codebase?**

The `IngestionAgent` detects languages and frameworks → the `SkillSelector` selects every active skill whose filters match → that guidance is injected into the triage, explainer, and fix prompts. The result is advice specific to *your* stack, with irrelevant guidance never loaded.

**Q: How does the SkillCreatorAgent work?**

Pass `skill_creation_params` in `ctx.extra` (name, description, languages, frameworks, examples). The agent calls the LLM via the GovernanceGate, parses the JSON into a `Skill`, validates it, and saves it to `core/skills/generated/`. Generated skills are usable immediately; activate via `POST /api/v1/skills/{name}/activate`.

**Q: Why does activating or disabling a skill require a database dependency?**

Every privileged operation writes an `AuditLogEntry`. The skills router takes `db: AsyncSession = Depends(get_db)` to write the entry transactionally with the state change.

---

## Cost & Budget

**Q: How does the per-scan budget work?**

`GovernanceGate` checks cumulative scan cost against `budget_policy.yaml` on every model call (pre-flight, with a conservative estimate). At 80% of the per-scan soft limit it emits a `budget_warning` SSE event. At the hard limit it raises `BudgetExceeded` — the orchestrator marks remaining agents `skipped` and closes the scan, keeping all findings collected so far. Total cost is still recorded.

**Q: Where do I see cost per scan?**

`GET /api/v1/cost/ledger` (per-call entries with model, tier, tokens, USD), `GET /api/v1/cost/summary` (rolled up by scan/model/tier), or the dashboard's Cost & Usage tab.

**Q: How is the model tier chosen per task?**

`config/model_tiers.yaml` → `task_defaults` maps each task type to a tier (`fast` / `balanced` / `top`); the GovernanceGate resolves the `(provider, model_id)` pair for that tier. Escalation rules can upgrade `balanced` → `top` when confidence is low or the diff is large.

**Q: Roughly what does a scan cost?**

A full scan with AI triage, explanations, and fixes typically lands around ~$0.50 with default tiers, because deterministic scanners do the heavy lifting for free and `fast`-tier models handle high-volume explanation work. The hard budget gate guarantees an upper bound regardless.

---

## API & Integration

**Q: How do I stream live scan progress?**

`GET /api/v1/scans/{id}/events` returns a server-sent event stream: `agent_started`, `llm_call`, `agent_completed`, `budget_warning`, `gate_required`, `scan_completed`.
```javascript
const es = new EventSource(`/api/v1/scans/${id}/events`);
es.onmessage = e => console.log(JSON.parse(e.data));
```

**Q: Can I trigger multiple scans at once?**

Yes. `POST /api/v1/scans/batch` accepts a list of full scan requests and validates every pipeline config exists before inserting any rows (atomic):
```json
{ "scans": [
    {"target_ref": "/repo/service-a", "pipeline_config_name": "pr-check"},
    {"target_ref": "/repo/service-b", "pipeline_config_name": "sca-scan"}
] }
```

**Q: How do I apply a fix?**

`POST /api/v1/fixes/{id}/apply` is a human gate. With a VCS token configured (GitHub or GitLab) it opens a pull request with the diff; without one it applies the patch locally. `POST /api/v1/fixes/{id}/reject` records the reason in the audit log.

**Q: How does pagination work?**

List endpoints return `{"items": [...], "next_cursor": "...", "limit": N}`. Pass `?cursor=<opaque>` to fetch the next page; `next_cursor: null` means the last page. Cursors are base64-encoded IDs.

---

## Audit & Compliance

**Q: What operations are audited?**

Every write to: `POST /fixes/{id}/apply` and `reject`; `POST /skills/{name}/activate` and `disable`; `PUT /config/model-tiers`; `PUT /config/budget-policy`; `POST /authorizations` and `DELETE /authorizations/{id}`; plus policy and suppression changes.

**Q: How do I query the audit log?**

`GET /api/v1/audit/?limit=100` returns the most recent entries (max 500). Each has `actor`, `action`, `target`, `before`, `after`, and `timestamp`.

**Q: Does Argus scan itself?**

Yes — the design calls for Argus to run its own scanner suite and produce a CycloneDX SBOM. The self-scan uses the `comprehensive-scan` config targeting the Argus repo root.

---

## Testing & CI

**Q: How do I run the tests without a database?**

```bash
pytest --ignore=tests/e2e -q
```
This runs all 433 unit and integration tests in ~40s. E2E tests in `tests/e2e/` require a live PostgreSQL connection.

**Q: My test patches the wrong thing and the real scanner runs — why?**

Scanner class names are resolved through `_AGENT_REGISTRY` at orchestrator import time, so patching the class after import doesn't change the registry. Use:
```python
from core.agents import orchestrator as orch_module
with patch.dict(orch_module._AGENT_REGISTRY, {"SemgrepAdapter": FakeSemgrep}):
    ...
```

**Q: How does the eval harness work?**

`python evals/harness.py --findings-file <path> --ground-truth evals/fixtures/ground_truth.json` computes precision, recall, FP rate, and F1 against labeled findings (±3 line tolerance). FP rate > 40% exits non-zero — wire it to CI to catch regressions.

---

## Suppression Rules

**Q: How do I suppress a known false positive?**

Three ways:
1. **API** — `POST /api/v1/suppressions` with `pattern_type: "fingerprint"` and the finding's `dedup_key`.
2. **.argusignore** — add a line at the repo root: `fp:<dedup_key>`, `path:tests/**`, or `rule:semgrep.sqli`.
3. **Finding status** — `PATCH /api/v1/findings/{id}` with `{"status": "dismissed"}` (one-off, no persistent rule).

**Q: What's the difference between `fingerprint`, `path_glob`, and `rule_id`?**

- `fingerprint` — exact match on `dedup_key`; most precise; re-suppresses if the finding recurs.
- `path_glob` — fnmatch on file path; good for whole directories (`vendor/**`, `tests/**`).
- `rule_id` — suppresses every finding from a rule ID; use when a rule is too noisy for a project.

**Q: Can suppression rules expire?**

Yes. Provide `expires_at` (ISO 8601 UTC). `GET /api/v1/suppressions` hides expired rules by default; pass `?include_expired=true` to see them.

---

## Scheduled Scans

**Q: How do I schedule a recurring scan?**

```json
POST /api/v1/schedules
{ "name": "nightly-main", "cron_expr": "0 2 * * *",
  "pipeline_config_name": "full-scan", "target_ref": "github.com/org/repo" }
```
Standard 5-field cron. Expressions not parseable by `croniter` are rejected.

**Q: How does the background scheduler work?**

A long-running `asyncio.Task` in the FastAPI lifespan polls every 30 seconds. Any `ScheduledScanRow` with `next_run_at ≤ now` and `enabled = true` gets a new `pending` scan, and `next_run_at` advances to the next cron fire time.

**Q: Can I pause a schedule without deleting it?**

Yes. `PATCH /api/v1/schedules/{id}/disable` sets `enabled = false` and clears `next_run_at`; `.../enable` re-enables and recomputes the next fire time.

---

## Compliance Report

**Q: How do I generate a compliance report for a scan?**

`GET /api/v1/scans/{id}/report` returns `severity_breakdown`, `owasp_top10`, `cwe_top10`, `risk_score`, and `total_findings`.

**Q: How is the risk score calculated?**

```
risk_score = (critical × 10) + (high × 5) + (medium × 2) + (low × 1)
```
Info/negligible findings don't contribute. It's intentionally simple — use it as a relative trend indicator across scans, not an absolute severity measure.

---

## Policy Engine

**Q: How do I define a security policy?**

`POST /api/v1/policies` with any combination of threshold fields:
```json
{ "name": "production-gate", "max_critical": 0, "max_high": 3,
  "max_risk_score": 30, "blocked_owasp": ["A03:2021"], "block_on_any_critical": true }
```
All fields are optional — omitting one leaves that constraint unenforced.

**Q: How does policy evaluation work?**

`POST /api/v1/policies/{policy_id}/evaluate/{scan_id}` builds a compliance report on the fly, evaluates it, and returns `passed` plus a list of `violations` (each names the rule, the actual value, and the limit). The result is persisted.

**Q: How do I block a CI/CD pipeline when a scan fails policy?**

Use `scripts/ci-gate.sh` (or `.bat` on Windows):
```bash
./scripts/ci-gate.sh --scan-id <uuid> --policy-id <policy-uuid>
```
Exit code 0 = pass, 1 = fail. Without `--policy-id`, all active policies are evaluated and any failure exits non-zero.

**Q: Can I have multiple policies?**

Yes — e.g. a lenient PR policy (`max_high=5`) and a strict production policy (`max_critical=0`). Evaluate against a specific one, or omit `--policy-id` to check all active policies at once.

---

## Bulk Operations

**Q: How do I suppress many findings at once?**

`POST /api/v1/findings/bulk-suppress` with up to 500 IDs:
```json
{ "finding_ids": ["id1", "id2"], "reason": "vendor library false positives" }
```
This creates a `fingerprint` suppression rule per finding and sets status `suppressed`. Findings without a `dedup_key` are reported in `skipped_ids`.

**Q: bulk-suppress vs bulk-dismiss?**

- `bulk-suppress` — creates persistent fingerprint rules; future scans auto-suppress the same finding.
- `bulk-dismiss` — marks findings dismissed in the current context only; no rule; future scans still report them.

**Q: How do I assign findings for triage?**

`POST /api/v1/findings/bulk-assign` with `assignee`. The assignee is stored in the finding's `location` JSONB and included in API responses.

---

## Multi-tenancy & RBAC

**Q: How does role-based access control work?**

Requests carry an `X-Argus-Role` header; the `require_role()` dependency enforces a minimum rank:

| Role | Rank | Access |
|---|---|---|
| viewer | 1 | Read-only: scans, findings, reports |
| analyst | 2 | + triage, suppress, dismiss, assign |
| admin | 3 | + org management, key rotation, config |

A missing header defaults to `viewer`; insufficient rank returns 403.

**Q: How do I create an organization and add members?**

```bash
POST /api/v1/orgs  {"name": "Accenture Security", "slug": "accenture-security"}
POST /api/v1/orgs/{org_id}/members  {"user_id": "alice@accenture.com", "role": "analyst"}
```
Slugs are lowercase alphanumeric with hyphens. Each org can hold multiple workspaces.

**Q: Is multi-tenancy enforced at the data layer?**

Phase 12 implements the org/workspace data model and role enforcement. Full row-level isolation (scoping every query to `org_id`) is a configuration-layer extension; single-tenant deployments use the org layer purely for access-control grouping.

---

## Integrations

**Q: How do I connect Argus to Jira?**

Set `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, then `POST /api/v1/integrations/jira/issue {"finding_id": "<uuid>"}` creates a Bug with full finding details.

**Q: How do I page on-call via PagerDuty?**

Set `PD_ROUTING_KEY`, then `POST /api/v1/integrations/pagerduty/trigger {"scan_id": "<uuid>", "severity": "critical"}`. Incidents are auto-deduplicated per scan.

**Q: What happens if an integration env var is not set?**

The endpoint returns HTTP 503 (`{"detail": "Jira integration not configured"}`). No silent failures — configure the env var or handle the 503 in your pipeline.

**Q: How are Slack rich messages different from the notification dispatcher?**

`core/notifications/dispatcher.py` sends plain-text webhook messages. `core/integrations/slack_rich.py` sends Block Kit cards with color-coded severity, finding links, and a context footer. Both use `SLACK_WEBHOOK_URL`; use `POST /integrations/slack/finding` for a rich card.

---

## Analytics

**Q: How do I get a trend of findings over time?**

`GET /api/v1/analytics/trends?granularity=day&days_back=30` returns `{"bucket": "2026-06-01", "total": 12, "critical": 1, ...}` per day (or week). Zero-finding days are included so charts have no gaps.

**Q: How is MTTR calculated?**

Mean Time to Remediate = average hours between a finding's creation and its scan's `finished_at` (proxy for fix time) for findings with `status="fixed"`. The response includes `sample_size` for statistical context.

**Q: How do I export all findings to CSV?**

```bash
curl -H "Authorization: Bearer $ARGUS_KEY" \
  "https://argus.internal/api/v1/scans/export/csv?days_back=30" -o findings.csv
```
Columns: `scan_id, target_ref, rule_id, severity, owasp_category, cwe, file, line, status, dedup_key`.

---

## Production Features

**Q: How does cursor-based pagination work?**

```bash
GET /api/v1/scans?limit=20
# → {"items": [...], "next_cursor": "dXVpZC0x...", "limit": 20}
GET /api/v1/scans?limit=20&cursor=dXVpZC0x...
```
Cursors are opaque base64-encoded IDs; `next_cursor: null` means the last page.

**Q: How does full-text search on findings work?**

`GET /api/v1/scans/{id}/findings?q=injection` runs a case-insensitive substring search across `rule_id`, `source_tool`, `cwe`, `owasp_category`, `explanation`, `dedup_key`, and `location.file`. It runs in-memory after the DB fetch, so it composes with cursor pagination.

**Q: How do I enable distributed tracing?**

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318`. Argus initializes a `TracerProvider` with a `BatchSpanProcessor` exporting to your OTLP collector (Jaeger, Tempo, Honeycomb). Without the env var, spans print to stdout for local debugging.

**Q: What do the "433 tests" cover?**

All 15 phases, in ~40s without a database: pure-function unit tests (suppression engine, policy evaluator, analytics, pagination, search), API tests via FastAPI dependency-override injection, integration-layer tests patching httpx for Jira/PD/Slack, scanner adapter tests patching subprocess calls, and (separately, requiring PostgreSQL) E2E acceptance tests.
