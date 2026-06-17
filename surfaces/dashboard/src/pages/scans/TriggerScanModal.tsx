import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, SecurityApproach, APPROACH_LABELS, APPROACH_DESCRIPTIONS } from "../../api/client";

interface Props { onClose: () => void; }

const APPROACHES: SecurityApproach[] = [
  "penetration_testing", "adversary_emulation", "breach_and_attack_simulation",
  "assumed_breach", "blue_team", "purple_team",
];

const APPROACH_ICON: Record<SecurityApproach, React.ReactNode> = {
  penetration_testing: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L9.121 9.121m0 5.758a3 3 0 10-4.243-4.243 3 3 0 004.243 4.243z" />
    </svg>
  ),
  adversary_emulation: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  ),
  breach_and_attack_simulation: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  assumed_breach: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
    </svg>
  ),
  blue_team: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  purple_team: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
    </svg>
  ),
};

export function TriggerScanModal({ onClose }: Props) {
  const [targetRef, setTargetRef] = useState("");
  const [approach, setApproach] = useState<SecurityApproach>("penetration_testing");
  const [mode, setMode] = useState<"at_rest" | "real_time">("at_rest");
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => api.triggerScan({ target_ref: targetRef, mode, approach }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scans"] }); onClose(); },
  });

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.15)] w-[620px] max-h-[90vh] overflow-y-auto">
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "#A100FF" }}>
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <h2 className="text-lg font-bold text-gray-900">New Security Scan</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center text-gray-500 hover:text-gray-700 transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-5 flex flex-col gap-5">
          {/* Target */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Target
            </label>
            <input
              className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm font-mono text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:border-transparent"
              style={{ ["--tw-ring-color" as string]: "#A100FF" }}
              placeholder="/path/to/repo  or  github.com/org/repo@main"
              value={targetRef}
              onChange={(e) => setTargetRef(e.target.value)}
            />
          </div>

          {/* Security approach */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Security Approach
            </label>
            <div className="grid grid-cols-2 gap-2">
              {APPROACHES.map((a) => {
                const selected = approach === a;
                return (
                  <button
                    key={a}
                    onClick={() => setApproach(a)}
                    className={`text-left px-4 py-3 rounded-xl border-2 transition-all ${
                      selected
                        ? "border-[#A100FF] bg-accent-50"
                        : "border-gray-100 bg-gray-50 hover:border-gray-200 hover:bg-white"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className={selected ? "text-[#A100FF]" : "text-gray-400"}>
                        {APPROACH_ICON[a]}
                      </span>
                      <span className={`text-sm font-semibold ${selected ? "text-[#A100FF]" : "text-gray-700"}`}>
                        {APPROACH_LABELS[a]}
                      </span>
                      {selected && (
                        <span className="ml-auto w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: "#A100FF" }}>
                          <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 leading-snug">{APPROACH_DESCRIPTIONS[a]}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Mode */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Mode</label>
            <div className="flex gap-2">
              {(["at_rest", "real_time"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 py-2 rounded-lg border text-sm font-medium transition-all ${
                    mode === m
                      ? "border-[#A100FF] bg-accent-50 text-[#A100FF]"
                      : "border-gray-200 text-gray-600 hover:border-gray-300"
                  }`}
                >
                  {m === "at_rest" ? "At Rest — full scan" : "Real Time — diff only"}
                </button>
              ))}
            </div>
          </div>

          {/* Submit */}
          <button
            onClick={() => mutation.mutate()}
            disabled={!targetRef || mutation.isPending}
            className="w-full text-white font-semibold rounded-xl py-3 transition-all disabled:opacity-40"
            style={{ background: !targetRef || mutation.isPending ? "#D1D5DB" : "#A100FF" }}
            onMouseOver={(e) => { if (targetRef && !mutation.isPending) e.currentTarget.style.background = "#8200CC"; }}
            onMouseOut={(e) => { if (targetRef && !mutation.isPending) e.currentTarget.style.background = "#A100FF"; }}
          >
            {mutation.isPending ? "Starting…" : `Start ${APPROACH_LABELS[approach]} Scan`}
          </button>

          {mutation.isError && (
            <p className="text-sm text-red-500 text-center">{String(mutation.error)}</p>
          )}
        </div>
      </div>
    </div>
  );
}
