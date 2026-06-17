import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useScanEvents } from "../../hooks/useScanEvents";
import { RunTrace } from "./RunTrace";
import { BudgetGauge } from "./BudgetGauge";

export function RunsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: scans } = useQuery({ queryKey: ["scans"], queryFn: api.listScans });
  const { events, connected } = useScanEvents(selectedId);

  const totalCost = events.filter((e) => e.event === "llm_call").reduce((s, e) => s + (e.cost_usd ?? 0), 0);
  const modelCounts: Record<string, number> = {};
  events.filter((e) => e.event === "llm_call").forEach((e) => {
    if (e.model_id) modelCounts[e.model_id] = (modelCounts[e.model_id] ?? 0) + 1;
  });

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Live Runs</h1>
          <p className="text-sm text-gray-500 mt-0.5">Real-time pipeline execution trace</p>
        </div>
        {connected && (
          <span className="flex items-center gap-1.5 px-3 py-1 bg-green-50 border border-green-200 rounded-full text-xs font-semibold text-green-700">
            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
            Live
          </span>
        )}
      </div>

      {/* Scan selector */}
      <div className="bg-white rounded-xl shadow-card px-4 py-3 flex items-center gap-3">
        <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">Scan</label>
        <select
          className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 focus:outline-none"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.target.value || null)}
        >
          <option value="">Select a scan…</option>
          {scans?.map((s) => (
            <option key={s.id} value={s.id}>{s.target_ref} — {s.status}</option>
          ))}
        </select>
      </div>

      {/* Main layout */}
      <div className="flex gap-4 items-start">
        <RunTrace events={events} />
        <div className="flex flex-col gap-4 w-52 flex-shrink-0">
          <BudgetGauge usedUsd={totalCost} />
          {Object.entries(modelCounts).length > 0 && (
            <div className="bg-white rounded-xl shadow-card p-4">
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-3">Model Calls</p>
              {Object.entries(modelCounts).map(([m, c]) => (
                <div key={m} className="flex justify-between items-center text-xs py-1 border-b border-gray-50 last:border-0">
                  <span className="font-mono text-gray-600 truncate">{m.split("-").slice(-2).join("-")}</span>
                  <span className="font-bold text-gray-900 ml-2">{c}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
