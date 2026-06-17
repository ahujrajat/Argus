import {
  ReactFlow, Background, Controls, Node, Edge, Handle, Position, NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const TIER_COLOR: Record<string, { bg: string; text: string; dot: string }> = {
  fast:     { bg: "#F5E5FF", text: "#6200CC", dot: "#A100FF" },
  balanced: { bg: "#FEF3C7", text: "#92400E", dot: "#F59E0B" },
  top:      { bg: "#FEE2E2", text: "#991B1B", dot: "#EF4444" },
  none:     { bg: "#F3F4F6", text: "#6B7280", dot: "#9CA3AF" },
};

interface AgentData {
  label: string;
  agent: string;
  tier: string;
  budget_pct: number;
  [key: string]: unknown;
}

function AgentNode({ data }: NodeProps<Node<AgentData>>) {
  const colors = TIER_COLOR[data.tier] ?? TIER_COLOR.none;
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-5 py-4 min-w-[165px] shadow-card hover:shadow-card-hover transition-shadow">
      <Handle type="target" position={Position.Left} style={{ background: "#D1D5DB", width: 8, height: 8 }} />
      <p className="text-sm font-bold text-gray-900">{data.label}</p>
      <p className="text-[11px] text-gray-400 mt-0.5 font-mono">{data.agent}</p>
      <div className="flex items-center gap-2 mt-2.5">
        <span
          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold"
          style={{ background: colors.bg, color: colors.text }}
        >
          <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: colors.dot }} />
          {data.tier === "none" ? "deterministic" : data.tier}
        </span>
      </div>
      {data.budget_pct > 0 && (
        <p className="text-[11px] text-gray-400 mt-1.5">{data.budget_pct}% budget</p>
      )}
      <Handle type="source" position={Position.Right} style={{ background: "#D1D5DB", width: 8, height: 8 }} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

const INITIAL_NODES: Node<AgentData>[] = [
  { id: "ingestion", type: "agent", position: { x: 0,   y: 100 }, data: { label: "Ingestion", agent: "IngestionAgent",    tier: "fast",     budget_pct: 5  } },
  { id: "sast",      type: "agent", position: { x: 220, y: 0   }, data: { label: "SAST",      agent: "SemgrepAdapter",    tier: "none",     budget_pct: 0  } },
  { id: "secrets",   type: "agent", position: { x: 220, y: 200 }, data: { label: "Secrets",   agent: "TruffleHogAdapter", tier: "none",     budget_pct: 0  } },
  { id: "triage",    type: "agent", position: { x: 460, y: 100 }, data: { label: "Triage",    agent: "TriageAgent",       tier: "balanced", budget_pct: 40 } },
  { id: "explainer", type: "agent", position: { x: 700, y: 100 }, data: { label: "Explainer", agent: "ExplainerAgent",    tier: "fast",     budget_pct: 15 } },
];

const INITIAL_EDGES: Edge[] = [
  { id: "ing-sast", source: "ingestion", target: "sast",      style: { stroke: "#D1D5DB", strokeWidth: 1.5 } },
  { id: "ing-sec",  source: "ingestion", target: "secrets",   style: { stroke: "#D1D5DB", strokeWidth: 1.5 } },
  { id: "sast-tri", source: "sast",      target: "triage",    style: { stroke: "#D1D5DB", strokeWidth: 1.5 } },
  { id: "sec-tri",  source: "secrets",   target: "triage",    style: { stroke: "#D1D5DB", strokeWidth: 1.5 } },
  { id: "tri-exp",  source: "triage",    target: "explainer", style: { stroke: "#A100FF", strokeWidth: 2 } },
];

export function PipelinePage() {
  return (
    <div className="flex flex-col gap-5 h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Pipeline</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Active configuration: <span className="font-medium text-gray-700">full-scan</span>
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-accent-50 border border-accent-100 rounded-full text-xs font-semibold text-accent-600">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          Read-only · Phase 1
        </span>
      </div>

      <div className="flex-1 min-h-[500px] bg-white rounded-xl shadow-card overflow-hidden border border-gray-100">
        <ReactFlow
          nodes={INITIAL_NODES}
          edges={INITIAL_EDGES}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#E5E7EB" gap={24} size={1} />
          <Controls
            showInteractive={false}
            style={{ background: "white", border: "1px solid #E5E7EB", borderRadius: 8 }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
