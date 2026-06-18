import { useState, useEffect } from "react";

interface NodeData {
  label: string;
  agent: string;
  tier: string;
  budget_pct: number;
}

interface Props {
  nodeId: string | null;
  data: NodeData | null;
  isFactory: boolean;
  onUpdate: (id: string, patch: Partial<NodeData>) => void;
  onRemove: (id: string) => void;
  onClose: () => void;
}

const TIERS = ["fast", "balanced", "top", "none"];

export function NodeConfigDrawer({ nodeId, data, isFactory, onUpdate, onRemove, onClose }: Props) {
  const [label, setLabel] = useState(data?.label ?? "");
  const [agent, setAgent] = useState(data?.agent ?? "");
  const [tier, setTier] = useState(data?.tier ?? "fast");
  const [budgetPct, setBudgetPct] = useState(data?.budget_pct ?? 0);

  useEffect(() => {
    setLabel(data?.label ?? "");
    setAgent(data?.agent ?? "");
    setTier(data?.tier ?? "fast");
    setBudgetPct(data?.budget_pct ?? 0);
  }, [nodeId, data]);

  const open = nodeId !== null && data !== null;

  function handleApply() {
    if (!nodeId) return;
    onUpdate(nodeId, { label, agent, tier, budget_pct: budgetPct });
    onClose();
  }

  function handleRemove() {
    if (!nodeId) return;
    onRemove(nodeId);
    onClose();
  }

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-10"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Drawer */}
      <div
        className={`fixed right-0 top-0 h-full z-20 bg-white border-l border-gray-200 shadow-xl flex flex-col transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ width: 280 }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Node Config</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {isFactory && (
          <div className="mx-5 mt-4 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <p className="text-[11px] text-gray-500">Factory pipeline — read-only. Clone to edit.</p>
          </div>
        )}

        {/* Fields */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Label</label>
            <input
              type="text"
              value={label}
              disabled={isFactory}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-gray-50 disabled:text-gray-400"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Agent</label>
            <input
              type="text"
              value={agent}
              disabled={isFactory}
              onChange={(e) => setAgent(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-gray-50 disabled:text-gray-400 font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Tier</label>
            <select
              value={tier}
              disabled={isFactory}
              onChange={(e) => setTier(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-gray-50 disabled:text-gray-400 bg-white"
            >
              {TIERS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Budget %
            </label>
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              value={budgetPct}
              disabled={isFactory}
              onChange={(e) => setBudgetPct(Number(e.target.value))}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-gray-50 disabled:text-gray-400"
            />
          </div>
        </div>

        {/* Footer */}
        {!isFactory && (
          <div className="px-5 py-4 border-t border-gray-100 space-y-2">
            <button
              onClick={handleApply}
              className="w-full px-4 py-2 bg-accent-600 text-white text-sm font-semibold rounded-lg hover:bg-accent-700 transition-colors"
            >
              Apply
            </button>
            <button
              onClick={handleRemove}
              className="w-full px-4 py-2 bg-white border border-red-200 text-red-600 text-sm font-semibold rounded-lg hover:bg-red-50 transition-colors"
            >
              Remove Node
            </button>
          </div>
        )}
      </div>
    </>
  );
}
