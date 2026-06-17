import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useScanEvents } from "../../hooks/useScanEvents";
import { RunTrace } from "./RunTrace";
import { BudgetGauge } from "./BudgetGauge";

export function RunsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: scans } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });
  const { events, connected } = useScanEvents(selectedId);

  const totalCost = events
    .filter((e) => e.event === "llm_call")
    .reduce((s, e) => s + (e.cost_usd ?? 0), 0);

  const modelCounts: Record<string, number> = {};
  events
    .filter((e) => e.event === "llm_call")
    .forEach((e) => {
      if (e.model_id)
        modelCounts[e.model_id] = (modelCounts[e.model_id] ?? 0) + 1;
    });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Live Runs</h1>
        <select
          className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.target.value || null)}
        >
          <option value="">Select a scan…</option>
          {scans?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.target_ref} — {s.status}
            </option>
          ))}
        </select>
        {connected && (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
            live
          </span>
        )}
      </div>

      <div className="flex gap-4">
        <RunTrace events={events} />
        <div className="flex flex-col gap-4 min-w-[200px]">
          <BudgetGauge usedUsd={totalCost} />
          {Object.entries(modelCounts).length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <p className="text-xs text-gray-400 mb-2 font-semibold uppercase tracking-wide">
                Model calls
              </p>
              {Object.entries(modelCounts).map(([m, c]) => (
                <div
                  key={m}
                  className="flex justify-between text-xs text-gray-300 py-0.5"
                >
                  <span className="font-mono truncate">
                    {m.split("-").slice(-2).join("-")}
                  </span>
                  <span className="text-white font-bold">{c}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
