# Argus Architecture

## System overview

Argus is four independent layers:

```
SURFACES (TypeScript)
  Dashboard (React) · VS Code Extension · CI Step
          │  REST + SSE (OpenAPI 3.1)
API LAYER (FastAPI / Python)
          │
CORE (Python)
  Orchestrator · GovernanceGate · Agents · Skills · Persistence
  Scanner Adapters (deterministic, zero LLM tokens)
```

## Layer rules
- Surfaces import only from the generated OpenAPI client. No Python imports in TypeScript.
- Core has no import from surfaces. The API layer is the boundary.
- All LLM calls go through `GovernanceGate` → finRouter Gateway → provider.
- Scanner adapters are deterministic. Zero LLM tokens for detection.

## Key components

### GovernanceGate
Single chokepoint for all LLM calls. Enforces per-scan budget, routes to the
correct provider+model via the model router, calls the finRouter Gateway via httpx,
records a CostLedgerEntry, and emits an SSE event.

### finRouter Gateway
TypeScript/Fastify sidecar wrapping the `finrouter` npm library. Runs on port 3001.
Handles provider routing, AES-256-GCM API key encryption, and org-level budget
enforcement. Adds zero-retention header forwarding. Python core never calls providers directly.

### Orchestrator
Loads a `PipelineConfig` from the database, topologically sorts nodes, and executes
them as an async task graph. Agent sequence and routing conditions are data, not code.

### Skills
Lazy-loaded markdown files from `argus/skills/`. `SkillSelector` matches active scan
context to skill names. Bodies load only when their node executes.

## Data flow (full-scan)
1. API receives POST /api/v1/scans — creates ScanRow, enqueues background task
2. Orchestrator loads pipeline config, executes nodes in order
3. IngestionAgent → CodeContext (repo map, languages, frameworks)
4. SemgrepAdapter + TruffleHogAdapter → SARIF → Finding (deterministic, zero tokens)
5. TriageAgent → enriches findings with adversarial scoring (GovernanceGate, balanced tier)
6. ExplainerAgent → adds attack-led explanations (GovernanceGate, fast tier)
7. Findings persisted to PostgreSQL, SARIF artifacts to S3
8. SSE events streamed throughout; dashboard Live Runs tab renders in real time

## Phase 1 scope
Phase 1 covers: SAST (Semgrep), secrets (TruffleHog), triage, explanation, dashboard
(Findings, Live Runs, Cost & Usage, Pipeline read-only), FastAPI, PostgreSQL, finRouter Gateway.

Phases 2–6 add: fix generation, VS Code extension, SCA, IaC, batch API, pattern/gap analysis,
DAST, and the Pipeline builder interactions.
