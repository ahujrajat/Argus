# Argus — Adaptive AI Security Platform

Argus is a provider-agnostic, cost-aware security platform that orchestrates deterministic scanners and AI agents to find vulnerabilities in code (SAST), dependencies (SCA), secrets, infrastructure-as-code (IaC), and running applications (DAST). It operates in three modes: code at rest, scheduled batch, and real-time developer loop.

---

## Table of Contents

- [Mission](#mission)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Scanner Adapters](#scanner-adapters)
- [Pipeline Configs](#pipeline-configs)
- [Skills System](#skills-system)
- [API Reference](#api-reference)
- [Development](#development)
- [Testing](#testing)
- [Evaluation Harness](#evaluation-harness)
- [Phase Delivery Status](#phase-delivery-status)
- [FAQ](#faq)

---

## Mission

Argus prioritizes signal quality (low false positives, accurate fixes) and cost discipline (deterministic-first execution, tiered models, explicit token budgets) as first-class requirements. Source code never leaves the operator boundary. Every model call routes through a GovernanceGate that enforces per-scan and monthly spend limits before any token is spent.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  SURFACES (TypeScript)                                           │
│  Dashboard (React) · VS Code Extension · CI Step                │
└────────────────────────┬────────────────────────────────────────┘
                         │  REST + SSE  (OpenAPI 3.1)
┌────────────────────────▼────────────────────────────────────────┐
│  API LAYER  (FastAPI / Python 3.12)                              │
│  /api/v1/scans  /findings  /fixes  /skills  /audit  /config     │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  CORE (Python)                                                   │
│  Orchestrator · GovernanceGate · Agents · Skills · Persistence  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Scanner Adapters  (zero LLM tokens)                      │   │
│  │  Semgrep · TruffleHog · Grype · Checkov · Nuclei · ZAP   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                            │
┌────────▼──────────┐     ┌──────────▼──────────────────────────┐
│  PostgreSQL 16    │     │  finRouter Gateway (Fastify sidecar) │
│  asyncpg +        │     │  Provider-agnostic LLM routing,      │
│  SQLAlchemy 2     │     │  AES-256-GCM key mgmt, org budgets   │
└───────────────────┘     └─────────────────────────────────────┘
```

### Key design principles

- **Pipeline-as-data** — agent topology, model tier, and budget allocation are stored as YAML/JSON in `config/pipeline_configs/`, not hardcoded. The orchestrator reads them at scan time.
- **GovernanceGate** — single chokepoint for all model calls. Checks per-scan budget, routes to the cheapest viable model tier, calls finRouter Gateway, writes the `CostLedgerEntry`, emits SSE.
- **Deterministic-first** — scanner adapters produce findings with zero LLM tokens. AI agents fire only after deterministic dedup.
- **DAST authorization gate** — DAST adapters (Nuclei, ZAP) refuse to run without a valid non-expired `TargetAuthorization` row.
- **Audit log** — every privileged operation (fix apply, skill activate/disable, config change, DAST run) writes an `AuditLogEntry`.

---

## Prerequisites

| Dependency | Version |
|---|---|
| Python | 3.12+ |
| uv (package manager) | latest |
| PostgreSQL | 16 |
| Docker + Compose | for `docker-compose up` |
| Node.js | 20+ (dashboard + finRouter gateway) |
| Semgrep | `pip install semgrep` or `brew install semgrep` |
| TruffleHog | `brew install trufflesecurity/trufflehog/trufflehog` |
| Grype | `brew install anchore/grype/grype` (SCA) |
| Checkov | `pip install checkov` (IaC) |
| Nuclei | `go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest` (DAST) |
| ZAP | Download from zaproxy.org, `zap.sh` on PATH (DAST) |

Scanner binaries are optional — adapters emit a `skipped` output if the binary is not found.

---

## Quick Start

```bash
# 1. Clone and enter
git clone <repo> argus && cd argus

# 2. Start infrastructure
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
# Start infrastructure
docker compose up -d

# Python environment
uv venv; .venv\Scripts\activate
uv pip install -e ".[dev]"

# Migrations and run
alembic upgrade head
uvicorn core.api.app:app --reload --port 8000
```

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
| `SEMGREP_BIN` | `semgrep` | Override semgrep binary path |
| `TRUFFLEHOG_BIN` | `trufflehog` | Override TruffleHog binary path |
| `GRYPE_BIN` | `grype` | Override Grype binary path |
| `NUCLEI_BIN` | `nuclei` | Override Nuclei binary path |
| `ZAP_BIN` | `zap.sh` | Override ZAP binary path |

### Model tiers (`config/model_tiers.yaml`)

Controls which model handles each task type. Edit via `PUT /api/v1/config/model-tiers` (writes audit entry) or directly:

```yaml
providers:
  default: anthropic
tiers:
  fast:
    anthropic: claude-haiku-4-5-20251001
  balanced:
    anthropic: claude-sonnet-4-6
  top:
    anthropic: claude-opus-4-8
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
  soft_limit_usd: 4.00    # emits budget_warning SSE at 80%
  hard_limit_usd: 5.00    # raises BudgetExceeded, skips remaining agents
monthly:
  soft_limit_usd: 160.00
  hard_limit_usd: 200.00
on_soft_limit: warn
on_hard_limit: stop_and_mark_skipped
```

Edit via `PUT /api/v1/config/budget-policy`. All values must be positive.

---

## Scanner Adapters

| Adapter | Tool | Category | Zero-token |
|---|---|---|---|
| `SemgrepAdapter` | `semgrep` | SAST | yes |
| `TruffleHogAdapter` | `trufflehog` | Secrets | yes |
| `GrypeAdapter` | `grype` | SCA | yes |
| `CheckovAdapter` | `checkov` | IaC | yes |
| `NucleiAdapter` | `nuclei` | DAST | yes |
| `ZAPAdapter` | `zap.sh` | DAST | yes |

All DAST adapters check `ctx.extra["dast_authorized"]` before running. The orchestrator populates this flag by querying `TargetAuthorizationRow` before the pipeline executes. If no valid non-expired authorization exists the adapter emits `skipped: true, skip_reason: "no_dast_authorization"`.

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

Skills are YAML files in `core/skills/builtin/` (shipped) and `core/skills/generated/` (AI-generated at runtime via `SkillCreatorAgent`).

Each skill carries:
- `languages` — language filter (empty = all)
- `frameworks` — framework filter (empty = all; non-empty = exclusive)
- `activation` — `active` | `inactive`
- `body` — guidance text injected into AI agent prompts

Built-in skills:
- `python-secure-coding` — Python/Django/Flask/FastAPI security guidance
- `secrets-detection` — TruffleHog triage guidance (universal)
- `iac-hardening` — Terraform/Kubernetes/CloudFormation/Helm guidance

Manage skills:
```bash
# List (with optional language filter)
GET /api/v1/skills/?language=python

# Activate / disable (writes audit entry)
POST /api/v1/skills/{name}/activate
POST /api/v1/skills/{name}/disable
```

---

## API Reference

All routes under `/api/v1/`. Interactive docs at `http://localhost:8000/docs`.

### Scans
```
POST   /scans                   Trigger a scan
GET    /scans                   List all scans
GET    /scans/{id}              Scan detail
DELETE /scans/{id}              Cancel
GET    /scans/{id}/events       SSE stream (live agent trace + cost)
POST   /scans/batch             Trigger multiple scans at once
```

### Findings & Fixes
```
GET    /scans/{id}/findings     Findings for a scan
GET    /findings/{id}           Finding detail
PATCH  /findings/{id}           Update status (open/dismissed)

GET    /fixes/{id}              Fix detail + diff
POST   /fixes/{id}/apply        Human-gate: open PR or apply locally
POST   /fixes/{id}/reject       Reject with reason
```

### Pipelines
```
GET    /pipelines               List pipeline configs
POST   /pipelines               Create custom pipeline
GET    /pipelines/{id}          Detail
PUT    /pipelines/{id}          Update (non-factory only)
DELETE /pipelines/{id}          Delete (non-factory only)
```

### Skills & Audit
```
GET    /skills                  List skills
POST   /skills/{name}/activate  Activate (writes audit entry)
POST   /skills/{name}/disable   Disable (writes audit entry)
GET    /audit                   Audit log (limit=100, max 500)
```

### Config
```
GET    /config                  Get both config files
PUT    /config/model-tiers      Update model tier config (writes audit)
PUT    /config/budget-policy    Update budget policy (writes audit)
```

### DAST Authorization
```
GET    /authorizations          List authorizations
POST   /authorizations          Create authorization for a target
DELETE /authorizations/{id}     Revoke
```

### Cost
```
GET    /cost/ledger             Per-call cost entries
GET    /cost/summary            Rolled-up by scan/model/tier
```

### SBOM & Diff (Phase 8)
```
GET    /scans/{id}/sbom                     CycloneDX 1.5 SBOM for a completed scan
GET    /scans/{id}/compare/{baseline_id}    Finding diff (new / persisted / resolved)
```

### Webhooks (Phase 8)
```
POST   /webhooks/github    GitHub push / PR webhook (HMAC-SHA256 verified)
POST   /webhooks/gitlab    GitLab Push Hook / Merge Request Hook (token verified)
```

### Auth & API Keys (Phase 9)
```
POST   /auth/keys           Generate a new API key (returns raw key once)
GET    /auth/keys           List active keys (requires auth)
DELETE /auth/keys/{id}      Revoke a key (requires auth)
```

Authentication: send the raw key in the `Authorization: Bearer <key>` header. The platform stores only the SHA-256 hash. A `ARGUS_MASTER_KEY` environment variable bypasses DB lookup for bootstrapping.

### Suppression Rules (Phase 10)
```
POST   /suppressions        Create a suppression rule
GET    /suppressions        List rules (add ?include_expired=true for expired)
DELETE /suppressions/{id}   Delete a rule
```

Supported `pattern_type` values: `fingerprint` (exact dedup_key), `path_glob` (fnmatch), `rule_id` (exact rule identifier). Rules can carry an optional `expires_at` ISO timestamp.

`.argusignore` file format (place at repo root):
```
# comment
path:tests/**           # suppress all findings in tests/
rule:semgrep.sqli       # suppress a specific rule
fp:<dedup_key>          # suppress by fingerprint
vendor/**               # bare pattern = path_glob default
```

### Scheduled Scans (Phase 10)
```
POST   /schedules                   Create a scheduled scan (cron expression)
GET    /schedules                   List schedules
GET    /schedules/{id}              Schedule detail
PATCH  /schedules/{id}/enable       Enable (recomputes next_run_at)
PATCH  /schedules/{id}/disable      Disable (clears next_run_at)
DELETE /schedules/{id}              Delete
```

Cron expressions use standard 5-field format (`"0 2 * * *"` = daily at 02:00 UTC). The background scheduler polls every 30 seconds and enqueues a `ScanRow` for each due schedule.

### Compliance Report (Phase 10)
```
GET    /scans/{id}/report    OWASP Top 10 counts, CWE distribution, severity breakdown, risk score
```

Risk score formula: `critical×10 + high×5 + medium×2 + low×1`.

### Observability (Phase 9)
```
GET    /metrics    Prometheus text metrics (counter: scans, findings, cost; histogram: duration)
```

---

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run unit + integration tests (no DB required)
pytest --ignore=tests/e2e -q

# Run full suite (requires PostgreSQL running)
pytest -q

# Run a specific test file
pytest tests/core/scanners/test_zap.py -v

# Type checking
mypy core/ --ignore-missing-imports

# Lint
ruff check core/ tests/

# Generate a new Alembic migration
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

### Adding a new scanner adapter

1. Create `core/scanners/my_tool.py` implementing `async def scan(self, ctx: AgentContext) -> AgentOutput`
2. Set `agent_id = "my_tool"` on the class
3. Register it in `core/agents/orchestrator.py` `_AGENT_REGISTRY`
4. Add to `_SCANNER_AGENTS` (and `_DAST_AGENTS` if it's a DAST tool)
5. Add a pipeline config YAML referencing the agent name
6. Write tests in `tests/core/scanners/test_my_tool.py`

### Windows `.bat` equivalents

Every shell script in this repo has a corresponding `.bat` file for Windows. When adding new scripts, create both `scripts/my-script.sh` and `scripts/my-script.bat`.

---

## Testing

The test suite is organized by layer:

```
tests/
  core/
    agents/          # orchestrator, triage, explainer, fix, pattern, DAST auth
    api/             # scans, findings, fixes, pipelines, skills, config, audit,
                     # suppressions, schedules, compliance report
    scanners/        # semgrep, trufflehog, grype, checkov, nuclei, zap
    scheduler/       # background cron runner
    suppression/     # suppression engine + .argusignore parser
    skills/          # skill loader, selector, creator
    understanding/   # ingestion, diff
    test_db.py       # schema/migration smoke tests
    test_seed.py     # pipeline config seeding
  e2e/               # end-to-end (requires live PostgreSQL)
  evals/             # eval harness unit tests
```

Run without a database:
```bash
pytest --ignore=tests/e2e -q   # 307 tests
```

Run everything (needs `docker compose up -d`):
```bash
pytest -q
```

---

## Evaluation Harness

```bash
# Evaluate a findings JSON file against ground truth
python evals/harness.py \
  --findings-file /tmp/findings.json \
  --ground-truth evals/fixtures/ground_truth.json

# Evaluate live scan from running API
python evals/harness.py \
  --scan-id <uuid> \
  --ground-truth evals/fixtures/ground_truth.json
```

Metrics: precision, recall, FP rate, F1. Exits non-zero if FP rate exceeds 40% (build-breaking threshold).

Ground truth fixture: `evals/fixtures/ground_truth.json` — 4 known findings in a vulnerable Python fixture (SQLi, XSS, hardcoded secret, path traversal).

---

## Phase Delivery Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Core scaffold, SAST + secrets scanners, triage, explainer, cost ledger, SSE, dashboard | Done |
| 2 | Fix generation, patch validation, PR creation, VCS integration (GitHub + GitLab), pipeline builder | Done |
| 3 | VS Code extension, real-time diff mode, CI step | Done |
| 4 | Batch API, SCA (Grype), IaC (Checkov) | Done |
| 5 | Skills system, PatternAgent, SkillCreatorAgent | Done |
| 6 | DAST (Nuclei + ZAP), authorization gate | Done |
| 7 | Audit log API, Config API, eval harness tests | Done |
| 8 | CycloneDX SBOM export, scan diff API, GitHub/GitLab webhooks, OpenAPI export scripts | Done |
| 9 | API key auth, Prometheus metrics, notification dispatcher, rate limiting (slowapi) | Done |
| 10 | Suppression rules (.argusignore), scheduled scans (cron), compliance report, background scheduler | Done |

---

## FAQ

See [FAQ.md](FAQ.md).
