# Argus — Adaptive AI Security Platform: Design Spec

**Date:** 2026-06-17
**Status:** Approved
**Phase in scope:** Phase 1 (Phases 2–6 deferred per phased delivery plan)

---

## 1. Mission

Argus is a provider-agnostic, cost-aware security platform that orchestrates deterministic scanners and AI agents to find vulnerabilities in code (SAST), dependencies (SCA), secrets, infrastructure-as-code, and running applications (DAST). It operates in three modes: code at rest, scheduled batch, and real-time developer loop. It prioritizes signal quality (low false positives, correct fixes) and cost discipline (deterministic-first, tiered models, explicit token budgeting) as first-class requirements.

---

## 2. Confirmed Decisions (Section 21 of spec)

| Question | Decision | Rationale |
|---|---|---|
| Core stack | Python + TypeScript surfaces | Security ecosystem is Python-native; TypeScript for React dashboard and VS Code extension |
| LLM orchestration | finRouter (sidecar gateway) | TypeScript library wrapping provider calls with enterprise FinOps, AES-256-GCM key encryption, hierarchical budget enforcement, and sub-5ms overhead. Wrapped in a thin Fastify HTTP gateway (`surfaces/finrouter-gateway/`) so the Python core calls it via HTTP. |
| Data residency | Self-hosted, privacy-first | Zero-retention headers per provider where supported; source code never leaves operator boundary |
| VCS integration | GitHub + GitLab simultaneously | VCS abstraction layer; both adapters built to the same interface |
| Budget caps | Configurable at setup, conservative defaults | $5/scan, $200/month; soft warning at 80%, hard stop at 100% |
| Auto-fix policy | Propose-and-review only (default) | No auto-commit to protected branches without explicit policy |
| Compliance mapping | OWASP + CWE only at first | Can expand via standards skills |
| Language priority | Python → JS/TS → Java → Go | Matches Phase 1 scanner and skill coverage |

---

## 3. Architecture

### 3.1 Layer overview

Four independent layers communicating through well-defined interfaces:

```
┌─────────────────────────────────────────────────────────────────┐
│  SURFACES (TypeScript)                                           │
│  Dashboard (React) · VS Code Extension · CI Step                │
└────────────────────────┬────────────────────────────────────────┘
                         │  REST + SSE  (OpenAPI 3.1)
┌────────────────────────▼────────────────────────────────────────┐
│  API LAYER (FastAPI / Python)                                    │
│  OpenAPI schema shared by all surfaces. Core never imports UI.   │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  CORE (Python)                                                   │
│  Orchestrator · GovernanceGate · Agents · Skills · Persistence  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Scanner Adapters (deterministic, zero LLM tokens)        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 UI independence

The dashboard and VS Code extension import only from `@argus/api-client` (generated from the OpenAPI schema) and `@argus/types` (also schema-generated). No Python package is imported by any TypeScript surface. The core FastAPI app has no knowledge of the React app.

### 3.3 Pipeline config is data

The orchestrator loads a named `PipelineConfig` (stored in PostgreSQL, editable via the Pipeline Design view) at scan time. Agent sequence, routing conditions, model tier per agent, and budget allocation per agent are all data — no agent wiring is hardcoded in Python. Three factory-default configs ship as YAML files in `config/pipeline_configs/` and are seeded into the database at first startup. The database is the runtime source of truth; the UI reads and writes the DB copy. Factory defaults are read-only and cannot be overwritten — users clone and customize.

### 3.4 Real-time via SSE

`GET /api/v1/scans/{id}/events` streams newline-delimited JSON events. The dashboard subscribes with `EventSource`. No polling.

Event schema:
```json
{"event": "agent_started",   "agent": "triage",   "timestamp": "..."}
{"event": "llm_call",        "agent": "triage",   "model": "claude-sonnet-4-6", "tokens_in": 4200, "cost_usd": 0.013}
{"event": "agent_completed", "agent": "triage",   "findings_out": 14, "elapsed_ms": 4100}
{"event": "gate_required",   "gate": "fix_apply", "fix_id": "fix_abc123"}
{"event": "budget_warning",  "used_pct": 80,      "used_usd": 4.00}
{"event": "scan_completed",  "total_cost_usd": 1.23}
```

---

## 4. Core Framework

### 4.1 Agent Orchestrator

```python
class BaseAgent(Protocol):
    async def run(self, ctx: AgentContext) -> AgentOutput: ...
```

`AgentContext` carries scan state, loaded skill(s), and the token budget slice for this agent. `AgentOutput` is a typed Pydantic model. Agents never call `LLMClient` directly — all model calls go through `GovernanceGate`.

The orchestrator resolves the pipeline config, topologically sorts nodes, and executes edges using async task fan-out. Edge conditions are evaluated against the prior node's output.

### 4.2 GovernanceGate

Single chokepoint for all model calls. The Python core never calls LLM providers directly — all calls route through the finRouter Gateway sidecar.

1. Check remaining scan budget (Argus per-scan budget) → raise `BudgetExceeded` if over hard limit
2. Model router → pick `(provider, model_id)` from task type + node tier config
3. POST to `http://finrouter-gateway/chat` via `httpx` with model, messages, and `x-zero-retention` flag
4. finRouter Gateway: enforces org/team-level budget cascade, encrypts keys, routes to provider, injects zero-retention header where supported
5. GovernanceGate reads usage metadata from gateway response (`tokens_in`, `tokens_out`, `cache_hit`, `cost_usd`)
6. Record `CostLedgerEntry` (scan-level attribution)
7. Emit SSE event for live dashboard trace
8. Return completion

**Two-layer cost governance:**
- finRouter layer: org → department → team → user hierarchy, block/downgrade/warn actions, AES-256-GCM key management
- Argus layer: per-scan token budget and CostLedger for finding/fix-level attribution and dashboard reporting

### 4.3 Model Router

Config-driven, reading `config/model_tiers.yaml`. No model name appears in Python source. The router selects a `(provider, model_id)` pair and passes it to `GovernanceGate`, which sends it to the finRouter Gateway. finRouter re-validates against its own routing rules before forwarding.

```yaml
providers:
  default: anthropic

tiers:
  fast:
    anthropic:  claude-haiku-4-5-20251001
    openai:     gpt-4o-mini
    google:     gemini-2.0-flash
  balanced:
    anthropic:  claude-sonnet-4-6
    openai:     gpt-4o
    google:     gemini-2.0-pro
  top:
    anthropic:  claude-opus-4-8
    openai:     o1
    google:     gemini-2.5-pro

escalation_rules:
  - condition: "confidence < 0.5"
    from_tier: balanced
    to_tier: top
  - condition: "diff_files > 10"
    from_tier: balanced
    to_tier: top
```

Note: finRouter supports Anthropic, OpenAI, Gemini, Mistral, and Groq. Model strings in `model_tiers.yaml` must match finRouter's provider identifiers.

Default tier per task type:

| Task | Default tier | Escalate when |
|---|---|---|
| Routing, classification, extraction, simple explanation | fast | low confidence |
| Triage scoring, FP filtering, most fix gen, pattern analysis | balanced | multi-file or low confidence |
| Complex multi-file fixes, deep architectural analysis | top | n/a |

### 4.4 Budget Guard

Per-scan budget loaded from `config/budget_policy.yaml` (configurable at setup):

```yaml
per_scan:
  soft_limit_usd: 4.00   # warn at 80%
  hard_limit_usd: 5.00
monthly:
  soft_limit_usd: 160.00
  hard_limit_usd: 200.00
```

On soft limit: emit `budget_warning` SSE event, log, continue.
On hard limit: raise `BudgetExceeded`, mark remaining un-executed agents as `skipped`, surface clearly in results.

### 4.5 Skills Loading

Skills are lazy-loaded from `argus/skills/`. `SkillSelector` matches active scan's languages, frameworks, and finding types to skill names. Bodies are loaded only when their node executes.

---

## 5. Scanner Adapters

Deterministic. Zero LLM tokens. Each adapter:
1. Shells out to the tool inside a sandboxed container
2. Parses tool output
3. Emits SARIF
4. SARIF → `Finding` via the internal mapper (CWE + OWASP mapping, dedup key)

Phase 1 adapters:
- **Semgrep** (SAST): Python, JS/TS. Custom rule sets in `argus/skills/*/rules/`.
- **TruffleHog** (secrets): git history + working tree. Raw secret values are redacted immediately — only fingerprint + location stored.

Phase 4+ adapters: SCA (Grype/Syft), IaC (Checkov), DAST (Nuclei/ZAP).

---

## 6. Dashboard UI

React + TypeScript + Vite. Talks only to the FastAPI API. Two primary modes:

### 6.1 Pipeline Design View (design-time)

Built on React Flow. Each agent is a custom node with a config drawer (tier, budget slice, escalation condition, allowed skills). Named pipeline configs are switchable. Phase 1 ships this view read-only; drag/save interactions arrive in Phase 2.

### 6.2 Live Runs View (control plane)

SSE subscription to `/api/v1/scans/{id}/events`. Renders:
- Per-agent progress row (status, elapsed, model used, cost)
- Budget gauge (live $X / $Y)
- Model router log (agent → model → tier)
- Inline approval queue for fix gates

### 6.3 Other tabs (Phase 1 subset)

- **Findings** — prioritized list with severity, CWE, OWASP, confidence; detail panel with explanation
- **Cost & Usage** — per-scan ledger, tier mix chart, cache-hit rate
- **Scans** — trigger, list, cancel

Fix Review and Skills tabs are scaffolded but inactive in Phase 1.

---

## 7. Data Model

All entities are Pydantic models with corresponding PostgreSQL tables managed by Alembic.

```
Scan                PipelineConfig      Finding
────────────────    ────────────────    ────────────────
id (uuid)           id (uuid)           id (uuid)
target_ref          name                scan_id
pipeline_config_id  version             rule_id
mode                definition (json)   source_tool
status              is_default          cwe
started_at          created_at          owasp_category
finished_at                             severity
tokens_in           Skill               exploit_likelihood
tokens_out          ────────────────    confidence
cache_hits          name                reachability
cost_usd            description         location (json)
model_usage (json)  version             dedup_key
                    family              status
Fix                 tools_allowed       fix_id
────────────────    status
id (uuid)           approved_by         CostLedgerEntry
finding_id          approved_at         ────────────────
diff                                    id (uuid)
test (optional)     AuditLogEntry       scope_type
explanation         ────────────────    scope_id
validation_result   id (uuid)           tokens_in
status              actor               tokens_out
reviewer            action              cache_hits
audit_ref           target              tier
                    before (json)       provider
PatternFinding      after (json)        model_id
────────────────    timestamp           batch_flag
id (uuid)                               cost_usd
scan_id             TargetAuthorization timestamp
issue               ────────────────
examples (json)     id (uuid)
risk                target
direction           scope_rules (json)
                    owner_confirmed
                    environment
                    rate_limits (json)
                    expires_at
```

---

## 8. API Surface

All routes under `/api/v1/`. OpenAPI 3.1 schema is the contract; TypeScript client is generated from it.

```
POST   /scans                        trigger
GET    /scans                        list
GET    /scans/{id}                   detail
DELETE /scans/{id}                   cancel
GET    /scans/{id}/events            SSE stream

GET    /scans/{id}/findings          list
GET    /findings/{id}                detail
PATCH  /findings/{id}                update status

GET    /fixes/{id}                   detail + diff
POST   /fixes/{id}/apply             gate: open PR or apply
POST   /fixes/{id}/reject            with reason

GET    /pipelines                    list
POST   /pipelines                    create
GET    /pipelines/{id}               detail
PUT    /pipelines/{id}               update
DELETE /pipelines/{id}               non-default only

GET    /skills                       list
POST   /skills/{name}/activate       human gate
POST   /skills/{name}/disable

GET    /cost/ledger                  entries
GET    /cost/summary                 rolled-up

GET    /authorizations               list
POST   /authorizations               create
DELETE /authorizations/{id}          revoke

GET    /health
GET    /config
PUT    /config/model-tiers
PUT    /config/budget-policy
```

---

## 9. Security of the Platform Itself

- **Least privilege:** agents and skills get only the tools they need; scanner and analysis paths are read-only by default
- **Sandboxed execution:** all scanners run in isolated containers with no access to secrets or networks beyond task scope
- **Secret redaction:** secrets found during scanning are redacted before any log write, DB write, model prompt, or UI render; only fingerprint + location stored
- **Zero-retention:** model calls include provider-specific zero-retention headers where supported
- **DAST authorization gate:** DAST refuses to run without an active `TargetAuthorization`; scope and rate limits enforced and logged
- **Audit log:** every privileged operation (fix apply, skill activation, DAST run, config change) writes an `AuditLogEntry`
- **Human gates:** fix application and skill activation require human approval by default
- **Own SBOM:** the platform scans itself and produces a CycloneDX SBOM

---

## 10. Repository Structure

```
argus/
  core/
    agents/           # orchestrator + specialist subagents
    governance/       # GovernanceGate, model router, budget guard, ledger
    scanners/         # adapters: semgrep, trufflehog, (grype, checkov, nuclei later)
    understanding/    # ingestion, repo map, language detection
    remediation/      # fix validation, PR/ticket workflow, review gates
    model/            # Pydantic data model + SARIF mapper
    api/              # FastAPI app + OpenAPI schema
  skills/
    languages/        # python, javascript-typescript, java, go
    frameworks/       # django, flask, express, spring, react
    vuln-classes/     # injection, xss, ssrf, secrets-exposure, ...
    tools/            # semgrep-tool, trufflehog-tool, ...
    standards/        # owasp-top-10, cwe-mapping, sarif
    meta/             # skill-creator
  surfaces/
    dashboard/          # React + TypeScript + Vite
    vscode-extension/   # TypeScript extension
    ci/                 # CI step + severity gate shell/YAML
    finrouter-gateway/  # Fastify HTTP wrapper around finRouter npm library
                        # Exposes POST /chat, GET /cost/summary
                        # Adds zero-retention header forwarding, per-call usage response
  sandbox/            # container definitions for isolated execution
  evals/              # benchmark repos + harness
  docs/
    ARCHITECTURE.md
    COST_MODEL.md
    DECISIONS.md
    SECURITY.md
    superpowers/specs/
  config/
    model_tiers.yaml
    budget_policy.yaml
    pipeline_configs/   # default full-scan, pr-check, real-time YAMLs
```

---

## 11. Phase 1 Scope

### Delivers

**Core:**
- Full monorepo scaffold
- `PipelineConfig` model + default configs
- finRouter Gateway sidecar (`surfaces/finrouter-gateway/`) — Fastify service wrapping finRouter, exposes `POST /chat` and `GET /cost/summary`, adds zero-retention header forwarding and per-call usage in response body
- `GovernanceGate` — calls finRouter Gateway via httpx, model router, per-scan budget guard
- `CostLedgerEntry` writer via LiteLLM callbacks
- Per-scan token budget guard
- `IngestionAgent` — language/framework detection, repo map, `CodeContext`
- Semgrep adapter (SAST, Python + JS/TS) + TruffleHog adapter (secrets)
- SARIF → `Finding` mapper (CWE + OWASP mapping)
- `TriageAgent` — dedup, severity+reachability scoring, FP filtering (balanced tier; the `CodeContext` block is marked with a provider cache breakpoint so it is reused across all triage calls within a scan without re-billing as fresh input)
- `ExplainerAgent` — per-finding explanation (fast tier)
- FastAPI app (full schema; unimplemented routes return 501)
- SSE event stream for scan progress
- Secret redaction in all write paths
- `AuditLogEntry` writer

**Persistence:**
- PostgreSQL schema (all entities, including future-phase ones)
- Alembic migrations
- S3-compatible object storage for SARIF artifacts

**Skills (Phase 1):**
- `languages/python`, `languages/javascript-typescript`
- `tools/semgrep-tool`, `tools/trufflehog-tool`
- `vuln-classes/injection`, `vuln-classes/xss`, `vuln-classes/secrets-exposure`
- `standards/owasp-top-10`

**Dashboard (Phase 1 subset):**
- Findings tab (prioritized list + detail + explanation)
- Live Runs tab (SSE trace, budget gauge, model router log)
- Cost & Usage tab (per-scan ledger, tier mix)
- Pipeline Design tab (read-only view of default pipeline)
- Fix Review and Skills tabs: scaffolded, inactive

### Acceptance checklist

- [ ] Full scan of a fixture repo produces normalized findings mapped to CWE and OWASP
- [ ] Triage reduces false positives measurably and ranks findings by severity+reachability
- [ ] Cost ledger records tokens, tier, and dollar cost per scan — visible in dashboard
- [ ] No secret written in cleartext to logs, DB, model prompt, or UI
- [ ] Model router logs a tier choice for every model call, defaulting to cheapest viable tier
- [ ] SSE stream delivers live pipeline trace to dashboard

### Deferred to later phases

| Capability | Phase |
|---|---|
| Fix generation, patch validation, PR creation | 2 |
| Pipeline builder interactions (drag/drop/save) | 2 |
| GitHub + GitLab VCS integration | 2 |
| VS Code extension | 3 |
| Real-time / incremental diff mode | 3 |
| Batch API dispatch | 4 |
| SCA (Grype/Syft), IaC (Checkov) | 4 |
| Pattern & gap subagent, skill-creator | 5 |
| DAST (Nuclei/ZAP) | 6 |

---

## 12. Evaluation Harness

Benchmark targets (evals/):
- OWASP WebGoat or Juice Shop (known-vulnerable fixture)
- A clean fixture repo (verifies no false positives on safe code)

Metrics tracked per run:
- Precision, recall, false-positive rate vs ground truth labels
- Fix correctness (applies, builds, tests pass, no regression)
- Cost per finding, cost per fix, cache-hit rate, tier mix

A regression in false-positive rate is treated as a build-breaking issue.
