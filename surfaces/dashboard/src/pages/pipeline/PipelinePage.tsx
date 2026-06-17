import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Handle,
  Position,
  NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const TIER_COLOR: Record<string, string> = {
  fast: "#6366f1",
  balanced: "#f59e0b",
  top: "#ef4444",
  none: "#6B7280",
};

interface AgentData {
  label: string;
  agent: string;
  tier: string;
  budget_pct: number;
  [key: string]: unknown;
}

function AgentNode({ data }: NodeProps<Node<AgentData>>) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-5 py-4 min-w-[160px] shadow-xl">
      <Handle type="target" position={Position.Left} className="!bg-gray-600" />
      <p className="text-sm font-bold text-white">{data.label}</p>
      <p className="text-xs text-gray-400 mt-1">{data.agent}</p>
      <span
        className="mt-2 inline-block px-2 py-0.5 rounded text-xs font-semibold"
        style={{
          background: (TIER_COLOR[data.tier] ?? "#6B7280") + "22",
          color: TIER_COLOR[data.tier] ?? "#6B7280",
        }}
      >
        {data.tier}
      </span>
      {data.budget_pct > 0 && (
        <p className="text-xs text-gray-600 mt-1">{data.budget_pct}% budget</p>
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-gray-600"
      />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

// Full-scan default pipeline — mirrors config/pipeline_configs/full-scan.yaml
const INITIAL_NODES: Node<AgentData>[] = [
  {
    id: "ingestion",
    type: "agent",
    position: { x: 0, y: 100 },
    data: {
      label: "Ingestion",
      agent: "IngestionAgent",
      tier: "fast",
      budget_pct: 5,
    },
  },
  {
    id: "sast",
    type: "agent",
    position: { x: 220, y: 0 },
    data: {
      label: "SAST",
      agent: "SemgrepAdapter",
      tier: "none",
      budget_pct: 0,
    },
  },
  {
    id: "secrets",
    type: "agent",
    position: { x: 220, y: 200 },
    data: {
      label: "Secrets",
      agent: "TruffleHogAdapter",
      tier: "none",
      budget_pct: 0,
    },
  },
  {
    id: "triage",
    type: "agent",
    position: { x: 460, y: 100 },
    data: {
      label: "Triage",
      agent: "TriageAgent",
      tier: "balanced",
      budget_pct: 40,
    },
  },
  {
    id: "explainer",
    type: "agent",
    position: { x: 700, y: 100 },
    data: {
      label: "Explainer",
      agent: "ExplainerAgent",
      tier: "fast",
      budget_pct: 15,
    },
  },
];

const INITIAL_EDGES: Edge[] = [
  { id: "ing-sast", source: "ingestion", target: "sast", animated: false },
  { id: "ing-sec", source: "ingestion", target: "secrets", animated: false },
  { id: "sast-tri", source: "sast", target: "triage", animated: false },
  { id: "sec-tri", source: "secrets", target: "triage", animated: false },
  { id: "tri-exp", source: "triage", target: "explainer", animated: false },
];

export function PipelinePage() {
  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Pipeline</h1>
        <span className="text-xs text-gray-500 bg-gray-800 px-3 py-1 rounded-full">
          Read-only in Phase 1 — editing arrives in Phase 2
        </span>
      </div>
      <p className="text-sm text-gray-400">
        Default pipeline:{" "}
        <span className="text-white font-medium">full-scan</span>
      </p>
      <div className="flex-1 min-h-[500px] bg-gray-950 border border-gray-800 rounded-xl overflow-hidden">
        <ReactFlow
          nodes={INITIAL_NODES}
          edges={INITIAL_EDGES}
          nodeTypes={nodeTypes}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#374151" gap={24} />
          <Controls showInteractive={false} />
          <MiniMap
            nodeColor={(n) =>
              TIER_COLOR[(n.data?.tier as string) ?? "none"] ?? "#6B7280"
            }
            maskColor="#111827cc"
          />
        </ReactFlow>
      </div>
    </div>
  );
}
