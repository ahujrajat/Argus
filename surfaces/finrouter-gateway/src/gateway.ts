// surfaces/finrouter-gateway/src/gateway.ts
import { ChatRequest, ChatResponse, CostSummary } from "./types.js";

// finrouter is a CommonJS package — import dynamically
let routerInstance: any = null;

async function getRouter(): Promise<any> {
  if (routerInstance) return routerInstance;
  const { FinRouter } = await import("finrouter");
  const router = new FinRouter({
    providers: {
      anthropic: { apiKey: process.env.ANTHROPIC_API_KEY ?? "" },
      openai: { apiKey: process.env.OPENAI_API_KEY ?? "" },
      google: { apiKey: process.env.GOOGLE_API_KEY ?? "" },
      mistral: { apiKey: process.env.MISTRAL_API_KEY ?? "" },
      groq: { apiKey: process.env.GROQ_API_KEY ?? "" },
    },
  });
  await router.init();
  routerInstance = router;
  return router;
}

// Per-call spend accumulator (finRouter tracks internally; we shadow it inline)
let _totalCostUsd = 0;
let _totalTokensIn = 0;
let _totalTokensOut = 0;
const _providerStats: Record<string, { cost_usd: number; calls: number }> = {};

function _estimateCost(provider: string, model: string, tokensIn: number, tokensOut: number): number {
  // Conservative per-token estimates in USD; real cost comes from finRouter's ledger
  const rates: Record<string, { in: number; out: number }> = {
    "claude-haiku-4-5-20251001": { in: 1 / 1e6, out: 5 / 1e6 },
    "claude-sonnet-4-6": { in: 3 / 1e6, out: 15 / 1e6 },
    "claude-opus-4-8": { in: 5 / 1e6, out: 25 / 1e6 },
    "gpt-4o-mini": { in: 0.15 / 1e6, out: 0.6 / 1e6 },
    "gpt-4o": { in: 2.5 / 1e6, out: 10 / 1e6 },
  };
  const rate = rates[model] ?? { in: 3 / 1e6, out: 15 / 1e6 };
  return tokensIn * rate.in + tokensOut * rate.out;
}

export async function chat(req: ChatRequest): Promise<ChatResponse> {
  const router = await getRouter();

  const response = await router.chat("argus-system", {
    model: req.model,
    messages: req.messages,
    ...(req.max_tokens ? { max_tokens: req.max_tokens } : {}),
    ...(req.temperature !== undefined ? { temperature: req.temperature } : {}),
  });

  const content: string =
    response?.choices?.[0]?.message?.content ??
    response?.content?.[0]?.text ??
    response?.text ??
    String(response);

  const tokensIn: number = response?.usage?.prompt_tokens ?? response?.usage?.input_tokens ?? 0;
  const tokensOut: number = response?.usage?.completion_tokens ?? response?.usage?.output_tokens ?? 0;
  const provider = req.provider ?? "anthropic";
  const costUsd = _estimateCost(provider, req.model, tokensIn, tokensOut);

  _totalCostUsd += costUsd;
  _totalTokensIn += tokensIn;
  _totalTokensOut += tokensOut;
  _providerStats[provider] = {
    cost_usd: (_providerStats[provider]?.cost_usd ?? 0) + costUsd,
    calls: (_providerStats[provider]?.calls ?? 0) + 1,
  };

  return {
    content,
    usage: {
      tokens_in: tokensIn,
      tokens_out: tokensOut,
      cache_hit: false,
      cost_usd: costUsd,
      model_id: req.model,
      provider,
    },
  };
}

export function getCostSummary(): CostSummary {
  return {
    total_cost_usd: _totalCostUsd,
    total_tokens_in: _totalTokensIn,
    total_tokens_out: _totalTokensOut,
    by_provider: { ..._providerStats },
  };
}
