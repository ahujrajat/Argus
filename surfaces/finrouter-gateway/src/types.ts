// surfaces/finrouter-gateway/src/types.ts
export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  model: string;
  messages: ChatMessage[];
  provider?: string;
  zero_retention?: boolean;
  max_tokens?: number;
  temperature?: number;
}

export interface UsageInfo {
  tokens_in: number;
  tokens_out: number;
  cache_hit: boolean;
  cost_usd: number;
  model_id: string;
  provider: string;
}

export interface ChatResponse {
  content: string;
  usage: UsageInfo;
}

export interface CostSummary {
  total_cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  by_provider: Record<string, { cost_usd: number; calls: number }>;
}
