import { ScanEvent } from "../../hooks/useScanEvents";

interface Props { events: ScanEvent[]; }

const STATUS_BADGE: Record<string, string> = {
  running:  "bg-blue-50 text-blue-600 border border-blue-200",
  done:     "bg-green-50 text-green-700 border border-green-200",
  skipped:  "bg-gray-100 text-gray-500 border border-gray-200",
  queued:   "bg-gray-50 text-gray-400 border border-gray-200",
};

export function RunTrace({ events }: Props) {
  const agentRows = new Map<string, { started: boolean; completed: boolean; cost: number; model?: string; skipped: boolean }>();

  for (const e of events) {
    if (e.event === "agent_started" && e.agent) {
      agentRows.set(e.agent, { started: true, completed: false, cost: 0, skipped: false });
    }
    if (e.event === "agent_completed" && e.agent) {
      const prev = agentRows.get(e.agent) ?? { started: true, completed: false, cost: 0, skipped: false };
      agentRows.set(e.agent, { ...prev, completed: true, cost: e.cost_usd ?? 0, skipped: !!e.skipped });
    }
    if (e.event === "llm_call" && e.agent) {
      const prev = agentRows.get(e.agent) ?? { started: true, completed: false, cost: 0, skipped: false };
      agentRows.set(e.agent, { ...prev, model: e.model_id, cost: prev.cost + (e.cost_usd ?? 0) });
    }
  }

  const llmCalls = events.filter((e) => e.event === "llm_call");
  const budgetWarning = events.find((e) => e.event === "budget_warning");

  const getStatusKey = (info: { started: boolean; completed: boolean; skipped: boolean }) =>
    info.skipped ? "skipped" : info.completed ? "done" : info.started ? "running" : "queued";

  return (
    <div className="flex-1 flex flex-col gap-4">
      {/* Agent progress table */}
      <div className="bg-white rounded-xl shadow-card overflow-hidden">
        <div className="grid grid-cols-4 gap-4 px-4 py-2.5 bg-gray-50 border-b border-gray-100 text-[11px] font-semibold text-gray-500 uppercase tracking-wide">
          <span>Agent</span>
          <span>Status</span>
          <span>Model</span>
          <span>Cost</span>
        </div>
        {[...agentRows.entries()].map(([agent, info]) => {
          const statusKey = getStatusKey(info);
          return (
            <div key={agent} className="grid grid-cols-4 gap-4 px-4 py-3 border-b border-gray-50 last:border-0 text-sm items-center">
              <span className="font-mono text-sm font-medium" style={{ color: "#A100FF" }}>{agent}</span>
              <span>
                <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold ${STATUS_BADGE[statusKey]}`}>
                  {statusKey === "running" ? (
                    <span className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
                      running
                    </span>
                  ) : statusKey}
                </span>
              </span>
              <span className="font-mono text-xs text-gray-500 truncate">{info.model?.split("-").slice(-2).join("-") ?? "—"}</span>
              <span className="font-mono text-xs text-gray-700">{info.cost > 0 ? `$${info.cost.toFixed(4)}` : "—"}</span>
            </div>
          );
        })}
        {agentRows.size === 0 && (
          <div className="px-4 py-10 text-center">
            <p className="text-sm text-gray-400">Select a running scan to see live events</p>
          </div>
        )}
      </div>

      {/* LLM router log */}
      {llmCalls.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2">Model Router Log</p>
          <div className="bg-white rounded-xl shadow-card overflow-hidden">
            {llmCalls.slice(-20).map((e, i) => (
              <div key={i} className="grid grid-cols-[120px_1fr_1fr_90px] gap-3 px-4 py-2 border-b border-gray-50 last:border-0 text-xs font-mono">
                <span className="font-semibold truncate" style={{ color: "#A100FF" }}>{e.agent as string}</span>
                <span className="text-gray-700 truncate">{e.model_id as string}</span>
                <span className="text-gray-400">
                  {(e.tokens_in as number | undefined)?.toLocaleString()} in / {(e.tokens_out as number | undefined)?.toLocaleString()} out
                </span>
                <span className="text-green-600 font-semibold text-right">${(e.cost_usd as number | undefined)?.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Budget warning */}
      {budgetWarning && (
        <div className="px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800 flex items-center gap-2">
          <svg className="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          Budget soft limit reached — {(budgetWarning as { used_pct?: number }).used_pct}% used (${(budgetWarning as { used_usd?: number }).used_usd?.toFixed(2)})
        </div>
      )}
    </div>
  );
}
