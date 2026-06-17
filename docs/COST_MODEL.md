# Cost Model

## Principles
1. **Deterministic-first.** Zero LLM tokens for detection — all scanning is deterministic.
   LLM tokens are spent only on triage, false-positive filtering, fix generation, and explanation.
2. **Tiered intelligence.** Tasks are routed to the cheapest model that meets the quality bar.
3. **Prompt caching.** The stable `CodeContext` block is marked with a provider cache breakpoint
   so it is reused across all triage calls within a scan.
4. **Per-scan budget guard.** Hard cap enforced before each LLM call. Remaining work is
   marked `skipped` when the cap is hit, not silently dropped.

## Model tiers (as of 2026-06)

Verify current pricing at https://docs.anthropic.com/en/docs/about-claude/pricing before production deployment.
All rates are per 1M tokens.

| Tier | Anthropic | OpenAI | Google | Input est. | Output est. |
|------|-----------|--------|--------|------------|-------------|
| fast | claude-haiku-4-5 | gpt-4o-mini | gemini-2.0-flash | ~$1 | ~$5 |
| balanced | claude-sonnet-4-6 | gpt-4o | gemini-2.0-pro | ~$3 | ~$15 |
| top | claude-opus-4-8 | o1 | gemini-2.5-pro | ~$5 | ~$25 |

## Task → tier mapping

| Task | Tier | Rationale |
|------|------|-----------|
| Explanation | fast | Short output, low reasoning demand |
| Classification | fast | Simple categorization |
| Triage + FP filter | balanced | Needs code context + adversarial reasoning |
| Fix generation | balanced | Needs correctness, escalates to top for multi-file |
| Pattern/gap analysis | balanced→top | Deep architectural reasoning |

## Budget defaults

Per scan: $4 soft / $5 hard
Monthly: $160 soft / $200 hard

Configurable in `config/budget_policy.yaml`.

## Cost levers

- **Deterministic-first:** scanning adds zero cost
- **Prompt caching:** CodeContext reused within a scan — cache hit rate target >70%
- **Batch API:** at-rest and batch mode use the Batch API for ~50% discount (Phase 4)
- **Incremental scope:** real-time mode scans diffs only (Phase 3)
- **Right-sized context:** agents receive minimum necessary context, not the full repo

## Cost ledger

Every GovernanceGate call writes a `CostLedgerEntry` with: scope_type, scope_id,
tokens_in, tokens_out, cache_hits, tier, provider, model_id, batch_flag, cost_usd.
The Cost & Usage dashboard tab displays this live.
