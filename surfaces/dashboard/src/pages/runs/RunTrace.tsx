import { ScanEvent } from "../../hooks/useScanEvents";

interface Props {
  events: ScanEvent[];
}

export function RunTrace({ events }: Props) {
  const agentRows = new Map<
    string,
    {
      started: boolean;
      completed: boolean;
      cost: number;
      model?: string;
      skipped: boolean;
    }
  >();

  for (const e of events) {
    if (e.event === "agent_started" && e.agent) {
      agentRows.set(e.agent, {
        started: true,
        completed: false,
        cost: 0,
        skipped: false,
      });
    }
    if (e.event === "agent_completed" && e.agent) {
      const prev = agentRows.get(e.agent) ?? {
        started: true,
        completed: false,
        cost: 0,
        skipped: false,
      };
      agentRows.set(e.agent, {
        ...prev,
        completed: true,
        cost: e.cost_usd ?? 0,
        skipped: !!e.skipped,
      });
    }
    if (e.event === "llm_call" && e.agent) {
      const prev = agentRows.get(e.agent) ?? {
        started: true,
        completed: false,
        cost: 0,
        skipped: false,
      };
      agentRows.set(e.agent, {
        ...prev,
        model: e.model_id,
        cost: prev.cost + (e.cost_usd ?? 0),
      });
    }
  }

  const llmCalls = events.filter((e) => e.event === "llm_call");
  const budgetWarning = events.find((e) => e.event === "budget_warning");

  return (
    <div className="flex-1">
      <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700 text-xs font-semibold text-gray-400 uppercase tracking-wide grid grid-cols-4 gap-4">
          <span>Agent</span>
          <span>Status</span>
          <span>Model</span>
          <span>Cost</span>
        </div>
        {[...agentRows.entries()].map(([agent, info]) => (
          <div
            key={agent}
            className="px-4 py-3 border-b border-gray-800 grid grid-cols-4 gap-4 text-sm"
          >
            <span className="font-mono text-indigo-400">{agent}</span>
            <span>
              {info.skipped
                ? "skipped"
                : info.completed
                  ? "done"
                  : info.started
                    ? "running..."
                    : "queued"}
            </span>
            <span className="text-gray-400">{info.model ?? "—"}</span>
            <span className="font-mono">
              {info.cost > 0 ? `$${info.cost.toFixed(4)}` : "—"}
            </span>
          </div>
        ))}
        {agentRows.size === 0 && (
          <div className="px-4 py-8 text-center text-gray-600 text-sm">
            Waiting for scan events…
          </div>
        )}
      </div>

      {llmCalls.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Model Router Log
          </h3>
          <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
            {llmCalls.slice(-20).map((e, i) => (
              <div
                key={i}
                className="px-4 py-2 border-b border-gray-800 text-xs font-mono text-gray-400 flex gap-4"
              >
                <span className="text-indigo-400">{e.agent as string}</span>
                <span className="text-white">-&gt; {e.model_id as string}</span>
                <span>
                  {(e.tokens_in as number | undefined)?.toLocaleString()} in /{" "}
                  {(e.tokens_out as number | undefined)?.toLocaleString()} out
                </span>
                <span className="text-emerald-400">
                  ${(e.cost_usd as number | undefined)?.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {budgetWarning && (
        <div className="mt-4 px-4 py-3 bg-yellow-900/40 border border-yellow-700 rounded-lg text-sm text-yellow-300">
          Budget soft limit reached —{" "}
          {(budgetWarning as { used_pct?: number }).used_pct}% used ($
          {(budgetWarning as { used_usd?: number }).used_usd?.toFixed(2)})
        </div>
      )}
    </div>
  );
}
