import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow, Background, Controls,
  Node, Handle, Position, NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, PipelineListItem, PipelineDetailDTO } from "../../api/client";
import { usePipelineEditor } from "../../hooks/usePipelineEditor";
import { NodeConfigDrawer } from "./NodeConfigDrawer";
import { PipelineToolbar } from "./PipelineToolbar";

// ── AgentNode renderer ────────────────────────────────────────────────────────

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
  selected?: boolean;
  [key: string]: unknown;
}

function AgentNode({ data, id }: NodeProps<Node<AgentData>>) {
  const colors = TIER_COLOR[data.tier] ?? TIER_COLOR.none;
  const ring = data.selected ? "ring-2 ring-accent-500" : "";
  return (
    <div className={`bg-white border border-gray-200 rounded-xl px-5 py-4 min-w-[165px] shadow-card hover:shadow-card-hover transition-shadow cursor-pointer ${ring}`}>
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

// ── Clone modal ───────────────────────────────────────────────────────────────

function CloneModal({
  sourceName,
  onConfirm,
  onCancel,
}: {
  sourceName: string;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(`${sourceName}-copy`);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-xl shadow-xl p-6 w-80 space-y-4">
        <h3 className="text-sm font-semibold text-gray-900">Clone pipeline</h3>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">New name</label>
          <input
            autoFocus
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-500"
          />
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">Cancel</button>
          <button
            disabled={!name.trim()}
            onClick={() => onConfirm(name.trim())}
            className="px-4 py-2 bg-accent-600 text-white text-sm font-semibold rounded-lg hover:bg-accent-700 disabled:opacity-40"
          >
            Clone
          </button>
        </div>
      </div>
    </div>
  );
}

// ── PipelineGraph ─────────────────────────────────────────────────────────────

function PipelineGraph({ pipeline, readonly }: { pipeline: PipelineDetailDTO; readonly: boolean }) {
  const qc = useQueryClient();
  const editor = usePipelineEditor(pipeline);

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updatePipeline(pipeline.id, { definition: editor.toPipelineDefinition() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelines"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deletePipeline(pipeline.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelines"] }),
  });

  const cloneMutation = useMutation({
    mutationFn: (name: string) => api.clonePipeline(pipeline.id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
      setShowClone(false);
    },
  });

  const [showClone, setShowClone] = useState(false);

  // Mark selected node in data so AgentNode can highlight itself
  const displayNodes = editor.nodes.map((n) => ({
    ...n,
    data: { ...n.data, selected: n.id === editor.selectedNodeId },
  }));

  const selectedNode = editor.nodes.find((n) => n.id === editor.selectedNodeId) ?? null;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar row */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">{pipeline.name}</h2>
          <p className="text-[11px] text-gray-400">v{pipeline.version}</p>
        </div>
        <PipelineToolbar
          isFactory={pipeline.is_factory}
          isDirty={editor.isDirty}
          onSave={() => saveMutation.mutate()}
          onClone={() => setShowClone(true)}
          onReset={editor.resetToSaved}
          onDelete={() => {
            if (confirm(`Delete pipeline "${pipeline.name}"?`)) deleteMutation.mutate();
          }}
        />
      </div>

      {/* Graph */}
      <div className="flex-1 relative overflow-hidden">
        <ReactFlow
          nodes={displayNodes}
          edges={editor.edges}
          nodeTypes={nodeTypes}
          onNodesChange={editor.onNodesChange}
          onEdgesChange={editor.onEdgesChange}
          onConnect={readonly ? undefined : editor.onConnect}
          nodesDraggable={!readonly}
          nodesConnectable={!readonly}
          onNodeClick={(_, node) => editor.selectNode(node.id)}
          onPaneClick={() => editor.selectNode(null)}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#E5E7EB" gap={24} size={1} />
          <Controls
            showInteractive={false}
            style={{ background: "white", border: "1px solid #E5E7EB", borderRadius: 8 }}
          />
        </ReactFlow>

        <NodeConfigDrawer
          nodeId={editor.selectedNodeId}
          data={selectedNode ? (selectedNode.data as AgentData) : null}
          isFactory={pipeline.is_factory}
          onUpdate={editor.updateNode}
          onRemove={editor.removeNode}
          onClose={() => editor.selectNode(null)}
        />
      </div>

      {showClone && (
        <CloneModal
          sourceName={pipeline.name}
          onConfirm={(name) => cloneMutation.mutate(name)}
          onCancel={() => setShowClone(false)}
        />
      )}
    </div>
  );
}

// ── PipelinePage ──────────────────────────────────────────────────────────────

export function PipelinePage() {
  const { data: list = [] } = useQuery<PipelineListItem[]>({
    queryKey: ["pipelines"],
    queryFn: api.listPipelines,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Auto-select first pipeline when list loads
  useEffect(() => {
    if (list.length > 0 && selectedId === null) {
      setSelectedId(list[0].id);
    }
  }, [list, selectedId]);

  const { data: pipeline } = useQuery<PipelineDetailDTO>({
    queryKey: ["pipeline", selectedId],
    queryFn: () => api.getPipeline(selectedId!),
    enabled: selectedId !== null,
  });

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left rail */}
      <div className="w-56 flex-shrink-0 border-r border-gray-100 overflow-y-auto bg-gray-50 py-3">
        <p className="px-4 pb-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Pipelines</p>
        {list.map((item) => (
          <button
            key={item.id}
            onClick={() => setSelectedId(item.id)}
            className={`w-full text-left px-4 py-2.5 flex items-start gap-2 transition-colors ${
              item.id === selectedId
                ? "bg-accent-50 border-r-2 border-accent-500"
                : "hover:bg-gray-100"
            }`}
          >
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium truncate ${item.id === selectedId ? "text-accent-700" : "text-gray-800"}`}>
                {item.name}
              </p>
              <div className="flex items-center gap-1.5 mt-0.5">
                {item.is_factory && (
                  <span className="text-[10px] text-gray-400 font-medium">Factory</span>
                )}
                {item.is_default && (
                  <span className="text-[10px] text-accent-500 font-semibold">Default</span>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Graph panel */}
      <div className="flex-1 overflow-hidden">
        {pipeline ? (
          <PipelineGraph key={pipeline.id} pipeline={pipeline} readonly={pipeline.is_factory} />
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-gray-400">
            Select a pipeline
          </div>
        )}
      </div>
    </div>
  );
}
