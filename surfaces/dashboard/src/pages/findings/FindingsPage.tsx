import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, FindingDTO, APPROACH_LABELS } from "../../api/client";
import { FindingDetail } from "./FindingDetail";
import { TriggerScanModal } from "../scans/TriggerScanModal";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-50 text-red-700 border border-red-200",
  high:     "bg-orange-50 text-orange-700 border border-orange-200",
  medium:   "bg-amber-50 text-amber-700 border border-amber-200",
  low:      "bg-blue-50 text-blue-700 border border-blue-200",
  info:     "bg-gray-100 text-gray-600 border border-gray-200",
};

export function FindingsPage() {
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<FindingDTO | null>(null);
  const [showTrigger, setShowTrigger] = useState(false);

  const { data: scans } = useQuery({ queryKey: ["scans"], queryFn: api.listScans });
  const { data: findings } = useQuery({
    queryKey: ["findings", selectedScanId],
    queryFn: () => api.getScanFindings(selectedScanId!),
    enabled: !!selectedScanId,
  });

  const activeScan = scans?.find((s) => s.id === selectedScanId);

  return (
    <div className="flex gap-6 h-full">
      <div className="flex-1 flex flex-col gap-5 min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Findings</h1>
            <p className="text-sm text-gray-500 mt-0.5">Vulnerability triage and prioritization</p>
          </div>
          <button
            onClick={() => setShowTrigger(true)}
            className="flex items-center gap-2 px-4 py-2 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
            style={{ background: "#A100FF" }}
            onMouseOver={(e) => (e.currentTarget.style.background = "#8200CC")}
            onMouseOut={(e) => (e.currentTarget.style.background = "#A100FF")}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Scan
          </button>
        </div>

        {/* Scan selector */}
        <div className="bg-white rounded-xl shadow-card px-4 py-3 flex items-center gap-3">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">Scan</label>
          <select
            className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:border-transparent"
            style={{ ["--tw-ring-color" as string]: "#A100FF" }}
            value={selectedScanId ?? ""}
            onChange={(e) => { setSelectedScanId(e.target.value); setSelectedFinding(null); }}
          >
            <option value="">Select a scan…</option>
            {scans?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.target_ref} — {s.status} — ${s.cost_usd.toFixed(3)}
              </option>
            ))}
          </select>
          {activeScan?.approach && (
            <span className="px-3 py-1 rounded-full text-xs font-medium border border-[#D18EFF] text-[#6200CC] bg-accent-50 whitespace-nowrap">
              {APPROACH_LABELS[activeScan.approach]}
            </span>
          )}
          {findings && (
            <span className="text-xs text-gray-400 whitespace-nowrap">{findings.length} findings</span>
          )}
        </div>

        {/* Empty state */}
        {findings && findings.length === 0 && (
          <div className="bg-white rounded-xl shadow-card px-6 py-12 text-center">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-700">No findings for this scan</p>
            <p className="text-xs text-gray-400 mt-1">This scan completed with no detected vulnerabilities.</p>
          </div>
        )}

        {/* Findings list */}
        {findings && findings.length > 0 && (
          <div className="bg-white rounded-xl shadow-card overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[80px_1fr_180px_100px_80px] gap-4 px-4 py-2.5 bg-gray-50 border-b border-gray-100 text-[11px] font-semibold text-gray-500 uppercase tracking-wide">
              <span>Severity</span>
              <span>Rule / Location</span>
              <span>Attack scenario</span>
              <span>CWE</span>
              <span className="text-right">Score</span>
            </div>
            {findings.map((f) => (
              <button
                key={f.id}
                onClick={() => setSelectedFinding(f)}
                className={`w-full text-left grid grid-cols-[80px_1fr_180px_100px_80px] gap-4 px-4 py-3 border-b border-gray-50 transition-colors last:border-0 ${
                  selectedFinding?.id === f.id
                    ? "bg-accent-50 border-l-[3px] border-l-[#A100FF]"
                    : "hover:bg-gray-50"
                }`}
                style={selectedFinding?.id === f.id ? { borderLeft: "3px solid #A100FF" } : undefined}
              >
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold uppercase self-start ${SEVERITY_STYLE[f.severity] ?? SEVERITY_STYLE.info}`}>
                  {f.severity}
                </span>
                <div className="min-w-0">
                  <p className="font-mono text-sm text-gray-800 truncate">{f.rule_id}</p>
                  <p className="text-xs text-gray-400 mt-0.5 truncate">{f.location.file}:{f.location.line_start}</p>
                </div>
                <p className="text-xs text-gray-500 truncate self-center">{f.attack_scenario ?? "—"}</p>
                <p className="text-xs font-mono text-gray-500 self-center">{f.cwe ?? "—"}</p>
                <p className="text-xs font-mono text-right self-center text-gray-700 font-semibold">
                  {f.priority_score?.toFixed(1) ?? "—"}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedFinding && (
        <FindingDetail finding={selectedFinding} onClose={() => setSelectedFinding(null)} />
      )}

      {showTrigger && <TriggerScanModal onClose={() => setShowTrigger(false)} />}
    </div>
  );
}
