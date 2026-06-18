# Argus — Adaptive AI Security Platform

> Find vulnerabilities faster. Understand them in context. Fix them with AI — under a hard cost budget you control.

Argus is a provider-agnostic, cost-aware security platform that unifies six industry-standard scanners and a team of AI agents behind a single API. It finds vulnerabilities in code (SAST), dependencies (SCA), secrets, infrastructure-as-code (IaC), and running applications (DAST) — then triages, explains, and fixes them while metering every AI dollar spent.

**Provider-agnostic · Cost-aware · Enterprise-ready** — `SAST · SCA · Secrets · IaC · DAST · AI-assisted remediation`

---

## What is Argus? (the non-technical version)

Modern software is assembled fast, from many parts. The tools meant to keep it secure haven't kept up:

- **Scanners shout, but don't think.** They emit thousands of findings per repository — mostly duplicates and false positives. Real risks drown in the noise.
- **The toolchain is fragmented.** A different tool for code, dependencies, secrets, infrastructure, and live apps — each with its own format and dashboard. No single view of risk.
- **AI is bolted on without controls.** Adding an LLM to scanning looks great in a demo, then the bill explodes. No budget, no metering, no audit trail.

**Argus fixes the workflow, not just the scanning.** It runs all your scanners, uses AI to tell you which findings actually matter and why, writes the code fix for the ones that do, and keeps the whole thing affordable and auditable. One platform, four outcomes:

| | |
|---|---|
| 🔎 **Find** | Six scanners sweep code, dependencies, secrets, infrastructure, and running apps — with zero AI cost. |
| 🧠 **Understand** | AI triages every finding: is it real, how exploitable, what's the blast radius? Noise is filtered out. |
| 🛠 **Fix** | For confirmed issues, AI drafts a precise, diff-ready code patch and a test — ready to review and merge. |
| ⚖️ **Govern** | Hard cost budgets, policies, suppression rules, RBAC, and a full audit trail keep every scan compliant and affordable. |

### Who is it for?

- **Individual developers** — scan locally, review ranked findings, apply an AI fix as a pull request, all from the editor (VS Code extension) or the API.
- **Security teams** — one pane of glass across all scan types, bulk triage, policies, suppression rules, and a complete audit trail.
- **Enterprises** — org-wide deployment with multi-tenancy, RBAC, CI/CD gating, scheduled scans, compliance reporting, and observability wired into Prometheus, OpenTelemetry, Jira, PagerDuty, and Slack.

---

## Table of Contents

- [Mission](#mission)
- [Architecture](#architecture)
- [Choosing Your Scan: Mode × Pipeline × Approach](#choosing-your-scan-mode--pipeline--approach)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Scanner Adapters](#scanner-adapters)
- [AI Agents](#ai-agents)
- [Pipeline Configs](#pipeline-configs)
- [Skills System](#skills-system)
- [Cost & Governance](#cost--governance)
- [Security & RBAC](#security--rbac)
- [API Reference](#api-reference)
- [Integrations & Observability](#integrations--observability)
- [Development](#development)
- [Testing](#testing)
- [Evaluation Harness](#evaluation-harness)
- [Phase Delivery Status](#phase-delivery-status)
- [FAQ](#faq)

---

## Mission

Argus prioritizes **signal quality** (low false positives, accurate fixes) and **cost discipline** (deterministic-first execution, tiered models, explicit token budgets) as first-class requirements.

Two principles are non-negotiable:

1. **Source code never leaves the operator boundary.** All model calls route through the finRouter Gateway with zero-retention headers; you control which provider keys are in scope.
2. **Every model call is governed.** A single GovernanceGate enforces per-scan and monthly spend limits *before* any token is spent. There is no path to an unbudgeted AI call.

---

## Architecture

Argus is layered. Cheap, deterministic work happens first; AI runs only where it adds value; and the source code stays inside your boundary.

```
┌─────────────────────────────────────────────────────────────────┐
│  SURFACES (TypeScript)                                            │
│  Dashboard (React) · VS Code Extension · CI Step · CLI Gate       │
└────────────────────────┬──────────────────────────────────────────┘
                         │  REST + SSE  (OpenAPI 3.1)
┌────────────────────────▼──────────────────────────────────────────┐
│  API LAYER  (FastAPI / Python 3.12)                               │
│  API-key auth · RBAC · rate limiting · cursor pagination · search │
└────────────────────────┬──────────────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────────────┐
│  ORCHESTRATOR (Python)                                            │
│  Pipeline engine · GovernanceGate · AI agents · Skills            │
│  cost ledger · audit log                                          │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Scanner Adapters  (zero LLM tokens)                      │    │
│  │  Semgrep · TruffleHog · Grype · Checkov · Nuclei · ZAP    │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         │                            │
┌────────▼──────────┐     ┌──────────▼──────────────────────────┐
│  PostgreSQL 16    │     │  finRouter Gateway (Fastify sidecar) │
│  asyncpg +        │     │  Provider-agnostic LLM routing,      │
│  SQLAlchemy 2     │     │  AES-256-GCM key mgmt, org budgets   │
└───────────────────┘     └─────────────────────────────────────┘
```

### Key design principles

- **Pipeline-as-data** — agent topology, model tier, and budget allocation are stored as YAML/JSON in `config/pipeline_configs/`, not hardcoded. The orchestrator reads them at scan time and executes independent nodes in parallel via `asyncio.gather` after a topological sort.
- **Deterministic-first** — scanner adapters produce findings with zero LLM tokens. AI agents fire only after deterministic dedup, so you never pay an LLM to look at a duplicate.
- **GovernanceGate** — single chokepoint for all model calls. Checks per-scan budget, routes to the cheapest viable model tier, calls the finRouter Gateway, writes the `CostLedgerEntry`, and emits a live SSE event.
- **DAST authorization gate** — DAST adapters (Nuclei, ZAP) refuse to run without a valid, non-expired `TargetAuthorization` row.
- **Audit everything** — every privileged operation (fix apply, skill toggle, config change, DAST run, policy change) writes an immutable `AuditLogEntry` with actor, action, before, and after.

---

## Choosing Your Scan: Mode × Pipeline × Approach

Argus exposes **three independent dials** on every scan. They combine freely — the same codebase can be scanned many ways for many audiences.

```jsonc
POST /api/v1/scans
{
  "target_ref": "github.com/org/repo",
  "mode": "at_rest",                 // dial 1 — when & how much
  "pipeline_config_name": "full-scan", // dial 2 — which tools run
  "approach": "penetration_testing"  // dial 3 — through which lens
}
```

### Dial 1 — Scan Mode (when & how much)

How the scan is triggered and scoped. Set via the `mode` field.

| Mode | Behavior | Typical use |
|---|---|---|
| `at_rest` | Full audit of a target (default) | Scheduled audits, baselining a repo |
| `batch` | Many targets scanned together | Org-wide nightly sweeps, monorepo fleets |
| `real_time` | Only files changed in the working tree are scanned (computes a git diff and passes changed files to scanners) | The developer inner loop / PR feedback |

### Dial 2 — Pipeline Config (which tools run)

A named recipe of scanners + agents. See [Pipeline Configs](#pipeline-configs) for the full list (`full-scan`, `pr-check`, `real-time`, `sca-scan`, `iac-scan`, `dast-scan`, `comprehensive-scan`) and how to author your own.

### Dial 3 — Security Approach (through which lens)

The **analytical mindset** the AI agents adopt. Set via the `approach` field, this re-frames the triage and explanation of the *same findings* to serve different audiences — red teams, blue teams, and control owners — from a single scan.

| Approach | What the AI emphasizes |
|---|---|
| `penetration_testing` *(default)* | Reachability, minimal payload, blast radius, and exploit chains — the attacker's view. |
| `adversary_emulation` | Maps each finding to MITRE ATT&CK techniques and the threat-actor groups that use them. |
| `breach_and_attack_simulation` | Would existing controls (WAF / SIEM / EDR / IDS) catch it? Flags control gaps. |
| `assumed_breach` | Post-compromise value only: privilege escalation, lateral movement, credential harvesting, persistence. |
| `blue_team` | Detection opportunities, log sources, SIEM signatures, and hardening steps — no exploit payloads. |
| `purple_team` | Both sides: the attack technique *and* the detection rule + log source that should fire. |

> Example: a SQL-injection finding scanned with `blue_team` yields the log entry and detection rule that would catch exploitation; the same finding with `assumed_breach` is deprioritized unless it enables lateral movement.

---

## Prerequisites

| Dependency | Version |
|---|---|
| Python | 3.12+ |
| uv (package manager) | latest |
| PostgreSQL | 16 |
| Docker + Compose | for `docker compose up` |
| Node.js | 20+ (dashboard + finRouter gateway) |
| Semgrep | `pip install semgrep` or `brew install semgrep` (SAST) |
| TruffleHog | `brew install trufflesecurity/trufflehog/trufflehog` (Secrets) |
| Grype | `brew install anchore/grype/grype` (SCA) |
| Checkov | `pip install checkov` (IaC) |
| Nuclei | `go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest` (DAST) |
| ZAP | Download from zaproxy.org, `zap.sh` on PATH (DAST) |

Scanner binaries are **optional** — adapters emit a `skipped` output (not an error) if the binary is not found, and the scan continues with the remaining agents.

---

## Quick Start

**Linux / macOS:**
```bash
# 1. Clone and enter
git clone https://github.com/ahujrajat/Argus argus && cd argus

# 2. Start infrastructure (PostgreSQL + finRouter gateway)
docker compose up -d

# 3. Create Python environment
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 4. Copy and populate environment
cp .env.example .env
# Set ANTHROPIC_API_KEY (or OPENAI_API_KEY / GOOGLE_API_KEY)

# 5. Run database migrations
alembic upgrade head

# 6. Start the API
uvicorn core.api.app:app --reload --port 8000

# 7. (Optional) Start the dashboard
cd surfaces/dashboard && npm install && npm run dev

# 8. Trigger your first scan
curl -s -X POST http://localhost:8000/api/v1/scans \
  -H "Content-Type: application/json" \
  -d '{"target_ref": "/path/to/your/repo", "pipeline_config_name": "full-scan"}'
```

**Windows (PowerShell):**
```powershell
docker compose up -d
uv venv; .venv\Scripts\activate
uv pip install -e ".[dev]"
alembic upgrade head
uvicorn core.api.app:app --reload --port 8000
```

Then open **http://localhost:8000/docs** for interactive Swagger UI.

---

## Configuration

### Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://argus:argus@localhost:5432/argus` | PostgreSQL connection string |
| `FINROUTER_GATEWAY_URL` | `http://localhost:3001` | finRouter sidecar URL |
| `ANTHROPIC_API_KEY` | — | Passed to finRouter gateway |
| `OPENAI_API_KEY` | — | Optional alternative provider |
| `GOOGLE_API_KEY` | — | Optional alternative provider |
| `LOG_LEVEL` | `INFO` | structlog level |
| `SEMGREP_BIN` / `TRUFFLEHOG_BIN` / `GRYPE_BIN` / `NUCLEI_BIN` / `ZAP_BIN` | tool name | Override scanner binary paths |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Enable OTLP tracing export (see [Observability](#integrations--observability)) |

### Model tiers (`config/model_tiers.yaml`)

Controls which model handles each task type. Edit via `PUT /api/v1/config/model-tiers` (writes an audit entry) or directly:

```yaml
providers:
  default: anthropic
tiers:
  fast:
    anthropic: claude-haiku-4-5-20251001      # cheap, high-volume work
  balanced:
    anthropic: claude-sonnet-4-6              # default for triage / fixes
  top:
    anthropic: claude-opus-4-8                # escalation when confidence is low
task_defaults:
  triage: balanced
  explanation: fast
  fix_generation: balanced
  pattern_analysis: balanced
  skill_creation: balanced
```

### Budget policy (`config/budget_policy.yaml`)

```yaml
per_scan:
  soft_limit_usd: 4.00    # emits a budget_warning SSE event at this threshold
  hard_limit_usd: 5.00    # raises BudgetExceeded, skips remaining AI agents
monthly:
  soft_limit_usd: 160.00
  hard_limit_usd: 200.00
on_soft_limit: warn
on_hard_limit: stop_and_mark_skipped
```

Edit via `PUT /api/v1/config/budget-policy`. All values must be positive.

---

## Scanner Adapters

All adapters run with **zero LLM tokens** and emit findings in a normalized schema (deduplicated and fingerprinted downstream).

| Adapter | Tool | Category |
|---|---|---|
| `SemgrepAdapter` | `semgrep` | SAST (static analysis) |
| `TruffleHogAdapter` | `trufflehog` | Secrets |
| `GrypeAdapter` | `grype` | SCA (dependency CVEs) |
| `CheckovAdapter` | `checkov` | IaC (Terraform / K8s / CloudFormation) |
| `NucleiAdapter` | `nuclei` | DAST (running app) |
| `ZAPAdapter` | `zap.sh` | DAST (running app) |

DAST adapters check `ctx.extra["dast_authorized"]` before running. The orchestrator populates this flag by querying `TargetAuthorizationRow` before the pipeline executes. With no valid, non-expired authorization, the adapter emits `skipped: true, skip_reason: "no_dast_authorization"`.

---

## AI Agents

AI agents run only after deterministic scanning and dedup. Every call is metered through the GovernanceGate.

| Agent | Role |
|---|---|
| `IngestionAgent` | Indexes the target; detects languages and frameworks (drives skill selection). |
| `TriageAgent` | Confirms findings, scores exploit likelihood and confidence, filters false positives. Re-framed by the chosen [security approach](#dial-3--security-approach-through-which-lens). |
| `ExplainerAgent` | Writes plain-language risk + business-impact explanations, also approach-aware. |
| `FixAgent` | Generates a diff-ready code patch plus a validating test. |
| `PatternAgent` | Connects individual findings into systemic, cross-cutting risks. |
| `SkillCreatorAgent` | Authors new [skills](#skills-system) at runtime for a named security domain. |

---

## Pipeline Configs

Factory pipelines in `config/pipeline_configs/` are seeded into PostgreSQL at startup:

| Name | Agents |
|---|---|
| `full-scan` | Ingestion → Semgrep + TruffleHog → Triage → Explainer → Fix |
| `pr-check` | Ingestion → Semgrep + TruffleHog → Triage → Explainer |
| `real-time` | Ingestion → Semgrep → Triage |
| `sca-scan` | Ingestion → Grype → Triage → Explainer |
| `iac-scan` | Ingestion → Checkov → Triage → Explainer |
| `dast-scan` | Nuclei → Triage → Explainer (+ PatternAgent parallel) |
| `comprehensive-scan` | Ingestion → all scanners → Triage → Explainer → PatternAgent |

Custom pipeline configs can be created via `POST /api/v1/pipelines` with a full YAML/JSON definition. Factory defaults cannot be overwritten; clone them first.

---

## Skills System

Skills are how Argus **adapts** to your stack. A skill is a focused block of security guidance injected into AI agent prompts at scan time, matched automatically to the scan by language and framework.

Skills are YAML files in `core/skills/builtin/` (shipped) and `core/skills/generated/` (AI-generated at runtime). Each skill carries:

- `languages` — language filter (empty = all)
- `frameworks` — framework filter (empty = all; non-empty = must overlap)
- `activation` — `active` | `inactive`
- `body` — guidance text injected into AI agent prompts

**Built-in skills:** `python-secure-coding` · `secrets-detection` · `iac-hardening`.

**How adaptation works:** the `IngestionAgent` detects, say, Python + Django → the `SkillSelector` pulls every active skill whose language/framework filters match → that guidance is injected into the triage, explainer, and fix prompts. Irrelevant skills never activate. Missing a domain? The `SkillCreatorAgent` authors a brand-new skill on the fly, and it is usable immediately.

```bash
# List (with optional language filter)
GET  /api/v1/skills/?language=python

# Activate / disable (each writes an audit entry)
POST /api/v1/skills/{name}/activate
POST /api/v1/skills/{name}/disable
```

---

## Cost & Governance

The GovernanceGate makes AI spend a **budget, not a surprise**. Every AI call follows the same path:

1. An agent requests an LLM call.
2. The gate checks the cumulative scan cost against `budget_policy.yaml` (pre-flight, with a conservative estimate).
3. It routes the task to the cheapest viable model tier (`fast` / `balanced` / `top`).
4. **Within budget** → the call proceeds via the finRouter Gateway.
5. **Over the hard limit** → `BudgetExceeded` is raised; the orchestrator marks remaining agents `skipped` and closes the scan. Findings collected so far are kept.
6. Tokens in/out and USD cost are written to the cost ledger; a Prometheus counter and SSE event fire.

At 80% of the per-scan soft limit, a `budget_warning` SSE event is emitted. Inspect spend any time:

```
GET /api/v1/cost/ledger     Per-call entries (model, tier, tokens, USD)
GET /api/v1/cost/summary    Rolled up by scan / model / tier
```

---

## Security & RBAC

| Feature | Summary |
|---|---|
| **API-key auth** | Send the raw key as `Authorization: Bearer <key>`. Only the SHA-256 hash is stored. `ARGUS_MASTER_KEY` env var bootstraps the first key. |
| **RBAC** | `X-Argus-Role` header: `viewer` (read-only) · `analyst` (triage/suppress) · `admin` (full). Enforced by the `require_role()` dependency; 403 on insufficient rank. |
| **Rate limiting** | 60 req/min per IP via slowapi, configurable per endpoint. |
| **Audit log** | Every privileged write records actor, action, target, before, after, timestamp — immutable and queryable. |
| **Suppression rules** | By `fingerprint`, `path_glob`, or `rule_id`; expirable; plus a `.argusignore` file at repo root. |
| **Policy engine** | Threshold + blocked-category gates evaluated in CI (exit code). |
| **DAST authorization gate** | Live-app scanners refuse to run without a valid, non-expired target authorization. |
| **Secret redaction** | `core/model/redaction.py` replaces raw secret values with a fingerprint before any DB write, log, prompt, or UI serialization. |

---

## API Reference

All routes under `/api/v1/`. Interactive docs at `http://localhost:8000/docs`.

### Scans
```
POST   /scans                   Trigger a scan (body: target_ref, mode, approach, pipeline_config_name)
GET    /scans?limit=20&cursor=  List scans (cursor-paginated)
GET    /scans/{id}              Scan detail
DELETE /scans/{id}              Cancel
GET    /scans/{id}/events       SSE stream (live agent trace + cost)
POST   /scans/batch             Trigger multiple scans at once (body: {"scans": [ ... ]})
```

### Findings & Fixes
```
GET    /scans/{id}/findings?limit=50&cursor=&q=   Findings (cursor-paginated, full-text q)
GET    /findings/{id}           Finding detail
PATCH  /findings/{id}           Update status (open / dismissed)

GET    /fixes/{id}              Fix detail + diff
POST   /fixes/{id}/apply        Human-gate: open PR or apply locally
POST   /fixes/{id}/reject       Reject with reason
```

### Bulk Finding Operations
```
POST   /findings/bulk-suppress   Suppress up to 500 findings by fingerprint
POST   /findings/bulk-dismiss    Mark up to 500 findings dismissed
POST   /findings/bulk-assign     Assign up to 500 findings to a user/team
```

### Pipelines, Skills, Audit, Config
```
GET/POST/PUT/DELETE  /pipelines[/{id}]   Manage pipeline configs (non-factory editable)
GET    /skills                            List skills
POST   /skills/{name}/activate|disable    Toggle a skill (writes audit entry)
GET    /audit?limit=100                   Audit log (max 500)
GET    /config                            Get both config files
PUT    /config/model-tiers                Update model tier config (writes audit)
PUT    /config/budget-policy              Update budget policy (writes audit)
```

### DAST Authorization & Cost
```
GET/POST/DELETE  /authorizations[/{id}]   Manage DAST target authorizations
GET    /cost/ledger                        Per-call cost entries
GET    /cost/summary                       Rolled-up cost by scan / model / tier
```

### SBOM, Diff & Compliance
```
GET    /scans/{id}/sbom                     CycloneDX 1.5 SBOM for a completed scan
GET    /scans/{id}/compare/{baseline_id}    Finding diff (new / persisted / resolved)
GET    /scans/{id}/report                   OWASP/CWE/severity breakdown + risk score
```
Risk score formula: `critical×10 + high×5 + medium×2 + low×1`.

### Webhooks
```
POST   /webhooks/github    GitHub push / PR webhook (HMAC-SHA256 verified)
POST   /webhooks/gitlab    GitLab Push / Merge Request Hook (token verified)
```

### Auth & API Keys
```
POST   /auth/keys           Generate a new API key (returns the raw key once)
GET    /auth/keys           List active keys (requires auth)
DELETE /auth/keys/{id}      Revoke a key
```

### Suppression Rules
```
POST   /suppressions        Create a rule (pattern_type: fingerprint | path_glob | rule_id; optional expires_at)
GET    /suppressions        List rules (?include_expired=true to include expired)
DELETE /suppressions/{id}   Delete a rule
```

`.argusignore` format (repo root):
```
# comment
path:tests/**           # suppress all findings in tests/
rule:semgrep.sqli       # suppress a specific rule
fp:<dedup_key>          # suppress by fingerprint
vendor/**               # bare pattern = path_glob default
```

### Scheduled Scans
```
POST   /schedules                   Create a scheduled scan (5-field cron, e.g. "0 2 * * *")
GET    /schedules[/{id}]            List / detail
PATCH  /schedules/{id}/enable       Enable (recomputes next_run_at)
PATCH  /schedules/{id}/disable      Disable (clears next_run_at)
DELETE /schedules/{id}              Delete
```
A background scheduler polls every 30 seconds and enqueues a scan for each due schedule.

### Policies
```
POST   /policies                             Create a security policy
GET    /policies?active_only=true            List policies
GET    /policies/{id}                        Policy detail
DELETE /policies/{id}                        Delete a policy
POST   /policies/{id}/evaluate/{scan_id}     Evaluate a scan against a policy (persists result)
GET    /policies/evaluations/scan/{scan_id}  All evaluations for a scan
```
Fields (all optional): `max_critical`, `max_high`, `max_medium`, `max_low`, `max_risk_score`, `blocked_owasp` (list), `blocked_cwe` (list), `block_on_any_critical` (bool). Omitting a field leaves that constraint unenforced.

### Organizations & RBAC
```
POST/GET/DELETE  /orgs[/{id}]               Manage organizations
POST/GET         /orgs/{id}/members         Add / list members (body: user_id, role)
DELETE           /orgs/{id}/members/{mid}   Remove member
```
Slugs must be lowercase alphanumeric with hyphens. Role enforcement is via the `X-Argus-Role` header (`viewer` / `analyst` / `admin`).

### Integrations
```
POST   /integrations/jira/issue          Create a Jira issue from a finding   (env: JIRA_URL, JIRA_API_TOKEN, JIRA_EMAIL, JIRA_PROJECT_KEY)
POST   /integrations/pagerduty/trigger   Trigger a PagerDuty incident          (env: PD_ROUTING_KEY)
POST   /integrations/slack/finding       Post a rich Block Kit card to Slack   (env: SLACK_WEBHOOK_URL)
```
Returns HTTP 503 if the integration's environment variable is not configured.

### Analytics & Export
```
GET    /analytics/trends?granularity=day&days_back=30    Finding counts bucketed by day/week (zero-filled)
GET    /analytics/mttr?days_back=90                      Mean time to remediate (hours + sample size)
GET    /analytics/top-rules?top_n=10&days_back=30        Most frequent rule IDs
GET    /analytics/summary?days_back=30                   Scan totals, severity breakdown, top OWASP, avg risk
GET    /scans/export/csv?days_back=30                    Download findings as CSV (StreamingResponse)
```

### Observability
```
GET    /metrics    Prometheus text metrics (counters: scans, findings, cost; histogram: duration)
```

### Pagination & Search

List endpoints return `{"items": [...], "next_cursor": "...", "limit": N}`. Cursors are opaque, base64-encoded IDs; a `null` `next_cursor` means the last page. The `q` parameter on findings performs case-insensitive substring search across `rule_id`, `source_tool`, `cwe`, `owasp_category`, `explanation`, `dedup_key`, and `location.file`.

---

## Integrations & Observability

- **Jira / PagerDuty / Slack** — see the [Integrations](#integrations) endpoints above. All are opt-in via environment variables and return 503 when unconfigured.
- **Prometheus** — scrape `GET /metrics`. Alert on the `argus_llm_cost_usd_total` rate; dashboard `argus_scan_duration_seconds`.
- **OpenTelemetry** — set `OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318` to export traces to Jaeger / Tempo / Honeycomb via a `BatchSpanProcessor`. Without the env var, spans print to stdout for local debugging.
- **CycloneDX** — every completed scan can emit a 1.5 SBOM via `GET /scans/{id}/sbom`.

---

## Development

```bash
uv pip install -e ".[dev]"

# Run unit + integration tests (no DB required)
pytest --ignore=tests/e2e -q

# Run full suite (requires PostgreSQL running)
pytest -q

# Type checking & lint
mypy core/ --ignore-missing-imports
ruff check core/ tests/

# Generate a new Alembic migration
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

### Adding a new scanner adapter

1. Create `core/scanners/my_tool.py` implementing `async def scan(self, ctx: AgentContext) -> AgentOutput`.
2. Set `agent_id = "my_tool"` on the class.
3. Register it in `core/agents/orchestrator.py` `_AGENT_REGISTRY`.
4. Add it to `_SCANNER_AGENTS` (and `_DAST_AGENTS` if it's a DAST tool).
5. Add a pipeline config YAML referencing the agent name.
6. Write tests in `tests/core/scanners/test_my_tool.py`.

### CI Gate

Wire Argus into CI/CD with `scripts/ci-gate.sh` (Linux/macOS) or `scripts/ci-gate.bat` (Windows):

```bash
# Evaluate a scan against all active policies (exits non-zero on failure)
ARGUS_API_URL=https://argus.internal ARGUS_API_KEY=argus_xxxx \
  ./scripts/ci-gate.sh --scan-id <uuid>

# Evaluate against a specific policy
./scripts/ci-gate.sh --scan-id <uuid> --policy-id <policy-uuid>
```

GitHub Actions example:
```yaml
- name: Argus security gate
  run: ./scripts/ci-gate.sh --scan-id ${{ steps.scan.outputs.scan_id }}
  env:
    ARGUS_API_URL: ${{ secrets.ARGUS_URL }}
    ARGUS_API_KEY: ${{ secrets.ARGUS_KEY }}
```

### Windows `.bat` equivalents

Every shell script in this repo has a corresponding `.bat` file for Windows (`ci-gate`, `export-openapi`). When adding new scripts, create both `scripts/my-script.sh` and `scripts/my-script.bat` with identical functionality.

### Presentation deck

The Accenture-themed overview deck is generated from code:
```bash
.venv/bin/python scripts/generate_deck.py Argus_Platform_Deck.pptx
```

---

## Testing

The suite is organized by layer:

```
tests/
  core/
    agents/          # orchestrator, triage, explainer, fix, pattern, DAST auth
    api/             # scans, findings, fixes, pipelines, skills, config, audit,
                     # suppressions, schedules, compliance report, policies, bulk,
                     # orgs, integrations, analytics, pagination, search
    analytics/       # trend computation pure functions
    integrations/    # jira, pagerduty, slack_rich unit tests
    scanners/        # semgrep, trufflehog, grype, checkov, nuclei, zap
    scheduler/       # background cron runner
    suppression/     # suppression engine + .argusignore parser
    skills/          # skill loader, selector, creator
    understanding/   # ingestion, diff
  e2e/               # end-to-end (requires live PostgreSQL)
  evals/             # eval harness unit tests
```

```bash
pytest --ignore=tests/e2e -q   # 433 tests, no database required (~40s)
pytest -q                      # full suite (needs docker compose up -d)
```

---

## Evaluation Harness

```bash
# Evaluate a findings JSON file against ground truth
python evals/harness.py --findings-file /tmp/findings.json \
  --ground-truth evals/fixtures/ground_truth.json

# Evaluate a live scan from the running API
python evals/harness.py --scan-id <uuid> \
  --ground-truth evals/fixtures/ground_truth.json
```

Metrics: precision, recall, FP rate, F1. Exits non-zero if FP rate exceeds 40% (build-breaking). Ground truth fixture: `evals/fixtures/ground_truth.json` — 4 known findings (SQLi, XSS, hardcoded secret, path traversal).

---

## Phase Delivery Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Core scaffold, SAST + secrets scanners, triage, explainer, cost ledger, SSE, dashboard | ✅ Done |
| 2 | Fix generation, patch validation, PR creation, VCS integration (GitHub + GitLab), pipeline builder | ✅ Done |
| 3 | VS Code extension, real-time diff mode, CI step | ✅ Done |
| 4 | Batch API, SCA (Grype), IaC (Checkov) | ✅ Done |
| 5 | Skills system, PatternAgent, SkillCreatorAgent | ✅ Done |
| 6 | DAST (Nuclei + ZAP), authorization gate | ✅ Done |
| 7 | Audit log API, Config API, eval harness tests | ✅ Done |
| 8 | CycloneDX SBOM export, scan diff API, GitHub/GitLab webhooks, OpenAPI export scripts | ✅ Done |
| 9 | API key auth, Prometheus metrics, notification dispatcher, rate limiting (slowapi) | ✅ Done |
| 10 | Suppression rules (.argusignore), scheduled scans (cron), compliance report, background scheduler | ✅ Done |
| 11 | Policy engine, CI gate script, bulk finding operations (suppress/dismiss/assign) | ✅ Done |
| 12 | Multi-tenancy & RBAC — organizations, workspaces, roles (admin/analyst/viewer) | ✅ Done |
| 13 | Integrations hub — Jira, PagerDuty, Slack Block Kit rich messages | ✅ Done |
| 14 | Trend analytics — finding trends, MTTR, top rules, summary, CSV export | ✅ Done |
| 15 | Production polish — cursor pagination, full-text search, OpenTelemetry tracing | ✅ Done |

---

## FAQ

See [FAQ.md](FAQ.md).
