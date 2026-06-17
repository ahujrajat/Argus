import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, FindingDTO, APPROACH_LABELS } from "../../api/client";
import { FindingDetail } from "./FindingDetail";
import { TriggerScanModal } from "../scans/TriggerScanModal";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-yellow-500",
  low: "bg-blue-500",
  info: "bg-gray-500",
};

export function FindingsPage() {
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<FindingDTO | null>(null);
  const [showTrigger, setShowTrigger] = useState(false);

  const { data: scans } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });
  const { data: findings } = useQuery({
    queryKey: ["findings", selectedScanId],
    queryFn: () => api.getScanFindings(selectedScanId!),
    enabled: !!selectedScanId,
  });

  return (
    <div className="flex gap-6 h-full">
      <div className="flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Findings</h1>
          <div className="flex items-center gap-3">
            <select
              className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm"
              value={selectedScanId ?? ""}
              onChange={(e) => {
                setSelectedScanId(e.target.value);
                setSelectedFinding(null);
              }}
            >
              <option value="">Select a scan…</option>
              {scans?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.target_ref} — {s.status} — ${s.cost_usd.toFixed(3)}
                </option>
              ))}
            </select>
            {scans?.find((s) => s.id === selectedScanId)?.approach && (
              <span className="px-2 py-0.5 rounded-full bg-gray-800 border border-gray-700 text-xs text-gray-300">
                {APPROACH_LABELS[scans!.find((s) => s.id === selectedScanId)!.approach]}
              </span>
            )}
            <button
              onClick={() => setShowTrigger(true)}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-lg transition-colors"
            >
              + New Scan
            </button>
          </div>
        </div>

        {findings && findings.length === 0 && (
          <p className="text-gray-500">No findings for this scan.</p>
        )}

        <div className="flex flex-col gap-2">
          {findings?.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedFinding(f)}
              className={`text-left px-4 py-3 rounded-lg border transition-colors ${
                selectedFinding?.id === f.id
                  ? "border-indigo-500 bg-gray-800"
                  : "border-gray-700 bg-gray-900 hover:border-gray-500"
              }`}
            >
              <div className="flex items-center gap-3">
                <span
                  className={`${SEVERITY_COLOR[f.severity]} text-white text-xs font-bold px-2 py-0.5 rounded uppercase`}
                >
                  {f.severity}
                </span>
                <span className="font-mono text-sm text-gray-300">
                  {f.rule_id}
                </span>
                <span className="text-gray-500 text-sm">
                  {f.location.file}:{f.location.line_start}
                </span>
                {f.cwe && (
                  <span className="text-gray-600 text-xs">{f.cwe}</span>
                )}
                <span className="ml-auto text-gray-600 text-xs">
                  score {f.priority_score?.toFixed(1) ?? "—"}
                </span>
              </div>
              {f.attack_scenario && (
                <p className="mt-1 text-xs text-gray-400 truncate">
                  {f.attack_scenario}
                </p>
              )}
            </button>
          ))}
        </div>
      </div>

      {selectedFinding && (
        <FindingDetail
          finding={selectedFinding}
          onClose={() => setSelectedFinding(null)}
        />
      )}

      {showTrigger && <TriggerScanModal onClose={() => setShowTrigger(false)} />}
    </div>
  );
}
