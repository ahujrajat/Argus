# Decisions

## D-001: Python core + TypeScript surfaces
**Decision:** Python for the core (agents, governance, scanners, API). TypeScript for
the dashboard, VS Code extension, and finRouter Gateway.
**Rationale:** Security ecosystem tooling (semgrep, trufflehog, bandit) is Python-native.
TypeScript is required for VS Code extensions and is natural for React.
**Alternative considered:** All-TypeScript monorepo.

## D-002: finRouter as LLM gateway
**Decision:** finRouter (npm) wrapped in a Fastify HTTP sidecar (`surfaces/finrouter-gateway/`).
Python GovernanceGate calls it via httpx.
**Rationale:** finRouter provides enterprise FinOps, AES-256-GCM key encryption, and
multi-provider support (Anthropic, OpenAI, Gemini, Mistral, Groq). No Python SDK exists,
so a sidecar is the integration path.
**Alternative considered:** LiteLLM (Python-native, but weaker FinOps).

## D-003: Provider-agnostic, self-hosted, privacy-first
**Decision:** Argus is provider-agnostic. Model strings in config/model_tiers.yaml must
match finRouter's provider identifiers. Zero-retention headers are added by the gateway
where the provider supports it. No code or findings leave the operator's boundary.

## D-004: Adversarial mindset for triage
**Decision:** The TriageAgent prompt frames every finding from an attacker's perspective —
exploit feasibility, attack scenario, and attack chain reasoning — rather than compliance-
checklist framing.
**Rationale:** Reduces false positives (dismissed if not exploitable), improves prioritization
(chained findings surface higher), and produces actionable output (developer sees the attack,
not just the rule ID).

## D-005: SecurityApproach as configurable methodology
**Decision:** Added a `SecurityApproach` enum (penetration_testing, adversary_emulation,
breach_and_attack_simulation, assumed_breach, blue_team, purple_team) that the scan trigger
UI exposes. Each approach drives a distinct agent prompt framing variant, report language,
and skill set loaded from `skills/approaches/`.
**Rationale:** Security teams use different methodologies. A red-team engagement, a
compliance audit, and a blue-team hardening review answer different questions and need
different agent prompts and output framing.
**Status:** Implemented in Phase 1 addendum (see `2026-06-17-phase1-security-approaches.md`):
enum in data model, approach-parameterized agent prompts (6 variants each for triage and
explainer), 6 approach skill files, approach selector in dashboard scan trigger.

## D-006: Both GitHub and GitLab simultaneously
**Decision:** Build a VCS abstraction layer and implement both adapters.
**Rationale:** Operator may have repos on both platforms.

## D-007: Budget caps — configurable at setup, conservative defaults
**Decision:** $5/scan hard limit, $200/month hard limit. Soft limits at 80%. All configurable
via config/budget_policy.yaml and the admin API.

## D-008: Auto-fix — propose-and-review only
**Decision:** Fixes are proposals. Humans approve before any repo write. Auto-apply mode
is off by default and restricted by policy when enabled.

## D-009: OWASP + CWE mapping only at first
**Decision:** No compliance framework mapping (SOC 2, PCI) in Phase 1. Expandable via
standards skills.
