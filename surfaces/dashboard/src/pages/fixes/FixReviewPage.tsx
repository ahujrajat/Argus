// surfaces/dashboard/src/pages/fixes/FixReviewPage.tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ScanDTO, FixDTO } from "../../api/client";
import { DiffViewer } from "./DiffViewer";

const STATUS_GROUPS: Array<{
  status: FixDTO["status"] | FixDTO["status"][];
  label: string;
  badgeClass: string;
}> = [
  {
    status: "proposed",
    label: "Proposed",
    badgeClass: "bg-yellow-100 text-yellow-800",
  },
  {
    status: "applied",
    label: "Applied",
    badgeClass: "bg-green-100 text-green-800",
  },
  {
    status: ["rejected", "needs_attention"],
    label: "Rejected / Needs Attention",
    badgeClass: "bg-red-100 text-red-800",
  },
];

function matchesGroup(fix: FixDTO, group: typeof STATUS_GROUPS[0]): boolean {
  const statuses = Array.isArray(group.status) ? group.status : [group.status];
  return statuses.includes(fix.status);
}

function StatusBadge({ status }: { status: FixDTO["status"] }) {
  const group = STATUS_GROUPS.find((g) => matchesGroup({ status } as FixDTO, g));
  const cls = group?.badgeClass ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function ValidationBadge({ result }: { result: FixDTO["validation_result"] }) {
  if (!result) return <span className="text-xs text-gray-400">Not validated</span>;
  if (result.error) return <span className="text-xs text-red-600">Error: {result.error}</span>;
  return (
    <span className={`text-xs font-medium ${result.finding_cleared ? "text-green-700" : "text-red-700"}`}>
      {result.finding_cleared ? "Finding cleared" : "Finding not cleared"}
      {result.new_findings.length > 0 && ` · ${result.new_findings.length} new finding(s)`}
    </span>
  );
}

export function FixReviewPage() {
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null);
  const [selectedFix, setSelectedFix] = useState<FixDTO | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const qc = useQueryClient();

  const { data: scans = [] } = useQuery<ScanDTO[]>({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });

  const { data: fixes = [], isLoading: fixesLoading } = useQuery<FixDTO[]>({
    queryKey: ["fixes", selectedScanId],
    queryFn: () => api.listScanFixes(selectedScanId!),
    enabled: !!selectedScanId,
  });

  const applyMutation = useMutation({
    mutationFn: (fixId: string) => api.applyFix(fixId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fixes", selectedScanId] });
      setSelectedFix(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ fixId, reason }: { fixId: string; reason: string }) =>
      api.rejectFix(fixId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fixes", selectedScanId] });
      setSelectedFix(null);
      setShowRejectInput(false);
      setRejectReason("");
    },
  });

  const completedScans = scans.filter((s) => s.status === "completed");

  return (
    <div className="flex h-full bg-gray-50">
      {/* Left panel: list */}
      <div className="flex-1 overflow-auto p-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900 mb-1">Fix Review</h1>
          <p className="text-sm text-gray-500">
            Review AI-generated patches. Apply or reject — every action is audit-logged.
          </p>
        </div>

        {/* Scan selector */}
        <div className="mb-5">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Scan
          </label>
          <select
            className="w-full max-w-sm border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            value={selectedScanId ?? ""}
            onChange={(e) => {
              setSelectedScanId(e.target.value || null);
              setSelectedFix(null);
            }}
          >
            <option value="">Select a scan…</option>
            {completedScans.map((s) => (
              <option key={s.id} value={s.id}>
                {s.target_ref} — {new Date(s.started_at ?? "").toLocaleString()}
              </option>
            ))}
          </select>
        </div>

        {/* Fix groups */}
        {fixesLoading && (
          <div className="text-sm text-gray-400 mt-8 text-center">Loading fixes…</div>
        )}

        {!fixesLoading && selectedScanId && fixes.length === 0 && (
          <div className="mt-8 text-center text-gray-400 text-sm">
            No fixes generated for this scan yet.
          </div>
        )}

        {!fixesLoading &&
          STATUS_GROUPS.map((group) => {
            const groupFixes = fixes.filter((f) => matchesGroup(f, group));
            if (groupFixes.length === 0) return null;
            return (
              <div key={group.label} className="mb-6">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-2">
                  {group.label} ({groupFixes.length})
                </h2>
                <div className="flex flex-col gap-2">
                  {groupFixes.map((fix) => (
                    <button
                      key={fix.id}
                      onClick={() => setSelectedFix(fix)}
                      className={`w-full text-left bg-white rounded-xl border px-4 py-3 shadow-sm transition-all hover:shadow-md ${
                        selectedFix?.id === fix.id
                          ? "border-purple-400 ring-2 ring-purple-200"
                          : "border-gray-200"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-mono text-gray-700 truncate">
                          {fix.finding_id.slice(0, 8)}…
                        </span>
                        <StatusBadge status={fix.status} />
                      </div>
                      <p className="mt-1 text-xs text-gray-500 truncate">{fix.explanation}</p>
                      <div className="mt-1">
                        <ValidationBadge result={fix.validation_result} />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
      </div>

      {/* Right panel: diff viewer */}
      {selectedFix && (
        <div className="w-[52%] border-l border-gray-200 bg-white overflow-auto flex flex-col">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 font-mono">
                Fix {selectedFix.id.slice(0, 8)}
              </p>
              <p className="text-sm text-gray-700 mt-0.5">{selectedFix.explanation}</p>
            </div>
            <button
              onClick={() => setSelectedFix(null)}
              className="text-gray-400 hover:text-gray-600 text-lg leading-none"
              aria-label="Close"
            >
              &times;
            </button>
          </div>

          <div className="flex-1 overflow-auto px-6 py-4">
            <DiffViewer diff={selectedFix.diff} />

            {selectedFix.test && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
                  Verification test
                </p>
                <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs font-mono text-gray-700 overflow-auto">
                  {selectedFix.test}
                </pre>
              </div>
            )}

            {selectedFix.validation_result && (
              <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
                <p className="text-xs font-semibold text-gray-500 mb-1">Validation</p>
                <ValidationBadge result={selectedFix.validation_result} />
                {selectedFix.validation_result.new_findings.length > 0 && (
                  <ul className="mt-1 text-xs text-red-600 list-disc list-inside">
                    {selectedFix.validation_result.new_findings.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* Apply / Reject — only for proposed fixes */}
          {selectedFix.status === "proposed" && (
            <div className="px-6 py-4 border-t border-gray-100">
              {!showRejectInput ? (
                <div className="flex gap-3">
                  <button
                    onClick={() => applyMutation.mutate(selectedFix.id)}
                    disabled={applyMutation.isPending}
                    className="px-5 py-2 rounded-lg text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    style={{ background: "#A100FF" }}
                  >
                    {applyMutation.isPending ? "Applying…" : "Apply fix"}
                  </button>
                  <button
                    onClick={() => setShowRejectInput(true)}
                    className="px-5 py-2 rounded-lg text-sm font-semibold text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <textarea
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-purple-400"
                    rows={2}
                    placeholder="Reason for rejection…"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() =>
                        rejectMutation.mutate({
                          fixId: selectedFix.id,
                          reason: rejectReason,
                        })
                      }
                      disabled={rejectMutation.isPending || !rejectReason.trim()}
                      className="px-4 py-1.5 rounded-lg text-sm font-semibold text-white bg-gray-500 hover:bg-gray-600 disabled:opacity-50 transition-colors"
                    >
                      {rejectMutation.isPending ? "Rejecting…" : "Confirm reject"}
                    </button>
                    <button
                      onClick={() => {
                        setShowRejectInput(false);
                        setRejectReason("");
                      }}
                      className="px-4 py-1.5 rounded-lg text-sm font-medium text-gray-500 hover:text-gray-700"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
