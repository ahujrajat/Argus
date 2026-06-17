import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, SecurityApproach, APPROACH_LABELS, APPROACH_DESCRIPTIONS } from "../../api/client";

interface Props { onClose: () => void; }

const APPROACHES: SecurityApproach[] = [
  "penetration_testing",
  "adversary_emulation",
  "breach_and_attack_simulation",
  "assumed_breach",
  "blue_team",
  "purple_team",
];

const APPROACH_ICON: Record<SecurityApproach, string> = {
  penetration_testing: "⚔️",
  adversary_emulation: "🎭",
  breach_and_attack_simulation: "🔁",
  assumed_breach: "🔓",
  blue_team: "🛡️",
  purple_team: "🟣",
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
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-8 w-[600px] max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold">New Scan</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-2xl leading-none">×</button>
        </div>

        <div className="flex flex-col gap-5">
          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-1.5 block">
              Target (path or repo URL)
            </label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm font-mono focus:outline-none focus:border-indigo-500"
              placeholder="/path/to/repo or github.com/org/repo@main"
              value={targetRef}
              onChange={(e) => setTargetRef(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-2 block">
              Security Approach
            </label>
            <div className="grid grid-cols-2 gap-2">
              {APPROACHES.map((a) => (
                <button
                  key={a}
                  onClick={() => setApproach(a)}
                  className={`text-left px-4 py-3 rounded-xl border transition-all ${
                    approach === a
                      ? "border-indigo-500 bg-indigo-950"
                      : "border-gray-700 bg-gray-800 hover:border-gray-500"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-base">{APPROACH_ICON[a]}</span>
                    <span className="text-sm font-semibold text-white">{APPROACH_LABELS[a]}</span>
                  </div>
                  <p className="text-xs text-gray-400 leading-snug">{APPROACH_DESCRIPTIONS[a]}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-1.5 block">Mode</label>
            <select
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              value={mode}
              onChange={(e) => setMode(e.target.value as typeof mode)}
            >
              <option value="at_rest">At Rest — full scan</option>
              <option value="real_time">Real Time — diff only</option>
            </select>
          </div>

          <button
            onClick={() => mutation.mutate()}
            disabled={!targetRef || mutation.isPending}
            className="mt-2 w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-semibold rounded-xl py-3 transition-colors"
          >
            {mutation.isPending ? "Starting…" : `Start ${APPROACH_LABELS[approach]} Scan`}
          </button>

          {mutation.isError && (
            <p className="text-sm text-red-400">{String(mutation.error)}</p>
          )}
        </div>
      </div>
    </div>
  );
}
