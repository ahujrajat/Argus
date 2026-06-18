import { useState, useCallback } from "react";
import {
  Node, Edge,
  applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, Connection, addEdge,
} from "@xyflow/react";
import type { PipelineDetailDTO, PipelineDefinitionDTO, NodeConfigDTO } from "../api/client";

interface AgentData {
  label: string;
  agent: string;
  tier: string;
  budget_pct: number;
  [key: string]: unknown;
}

type AgentNode = Node<AgentData>;

function layoutNodes(nodes: NodeConfigDTO[], edges: { from: string; to: string }[]): AgentNode[] {
  // BFS-based layout: assign column by longest-path distance from roots
  const inDegree = new Map<string, number>();
  const children = new Map<string, string[]>();

  for (const n of nodes) {
    inDegree.set(n.id, 0);
    children.set(n.id, []);
  }
  for (const e of edges) {
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1);
    children.get(e.from)?.push(e.to);
  }

  const columns: string[][] = [];
  const visited = new Set<string>();
  let queue = nodes.map((n) => n.id).filter((id) => (inDegree.get(id) ?? 0) === 0);

  while (queue.length > 0) {
    columns.push(queue);
    visited.add(...queue);
    const next: string[] = [];
    for (const id of queue) {
      for (const child of children.get(id) ?? []) {
        if (!visited.has(child)) {
          next.push(child);
          visited.add(child);
        }
      }
    }
    queue = next;
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const positioned: AgentNode[] = [];
  const X_STEP = 220;
  const Y_STEP = 150;

  for (let col = 0; col < columns.length; col++) {
    const ids = columns[col];
    const totalHeight = (ids.length - 1) * Y_STEP;
    for (let row = 0; row < ids.length; row++) {
      const id = ids[row];
      const def = nodeMap.get(id)!;
      positioned.push({
        id,
        type: "agent",
        position: { x: col * X_STEP, y: row * Y_STEP - totalHeight / 2 },
        data: {
          label: id.charAt(0).toUpperCase() + id.slice(1).replace(/_/g, " "),
          agent: def.agent,
          tier: def.tier,
          budget_pct: def.budget_pct,
        },
      });
    }
  }

  // Append any nodes not reached by BFS (disconnected)
  for (const n of nodes) {
    if (!positioned.find((p) => p.id === n.id)) {
      positioned.push({
        id: n.id,
        type: "agent",
        position: { x: 0, y: positioned.length * Y_STEP },
        data: {
          label: n.id.charAt(0).toUpperCase() + n.id.slice(1).replace(/_/g, " "),
          agent: n.agent,
          tier: n.tier,
          budget_pct: n.budget_pct,
        },
      });
    }
  }

  return positioned;
}

function definitionToFlow(
  def: PipelineDefinitionDTO
): { nodes: AgentNode[]; edges: Edge[] } {
  const edges: Edge[] = def.edges.map((e) => ({
    id: `${e.from}-${e.to}`,
    source: e.from,
    target: e.to,
    style: { stroke: "#D1D5DB", strokeWidth: 1.5 },
  }));
  const nodes = layoutNodes(def.nodes, def.edges);
  return { nodes, edges };
}

export interface PipelineEditorState {
  nodes: AgentNode[];
  edges: Edge[];
  isDirty: boolean;
  selectedNodeId: string | null;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  selectNode: (id: string | null) => void;
  updateNode: (id: string, patch: Partial<AgentData>) => void;
  removeNode: (id: string) => void;
  resetToSaved: () => void;
  toPipelineDefinition: () => PipelineDefinitionDTO;
}

export function usePipelineEditor(
  pipeline: PipelineDetailDTO | null
): PipelineEditorState {
  const initial = pipeline ? definitionToFlow(pipeline.definition) : { nodes: [], edges: [] };

  const [nodes, setNodes] = useState<AgentNode[]>(initial.nodes);
  const [edges, setEdges] = useState<Edge[]>(initial.edges);
  const [savedNodes, setSavedNodes] = useState<AgentNode[]>(initial.nodes);
  const [savedEdges, setSavedEdges] = useState<Edge[]>(initial.edges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const isDirty =
    JSON.stringify(nodes.map((n) => ({ id: n.id, data: n.data }))) !==
    JSON.stringify(savedNodes.map((n) => ({ id: n.id, data: n.data }))) ||
    JSON.stringify(edges.map((e) => ({ s: e.source, t: e.target }))) !==
    JSON.stringify(savedEdges.map((e) => ({ s: e.source, t: e.target })));

  const onNodesChange = useCallback(
    (changes: NodeChange[]) =>
      setNodes((nds) => applyNodeChanges(changes, nds) as AgentNode[]),
    []
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((eds) =>
        addEdge(
          { ...connection, style: { stroke: "#D1D5DB", strokeWidth: 1.5 } },
          eds
        )
      ),
    []
  );

  const selectNode = useCallback((id: string | null) => setSelectedNodeId(id), []);

  const updateNode = useCallback((id: string, patch: Partial<AgentData>) => {
    setNodes((nds) =>
      nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))
    );
  }, []);

  const removeNode = useCallback((id: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== id));
    setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
    setSelectedNodeId((sel) => (sel === id ? null : sel));
  }, []);

  const resetToSaved = useCallback(() => {
    setNodes(savedNodes);
    setEdges(savedEdges);
    setSelectedNodeId(null);
  }, [savedNodes, savedEdges]);

  const toPipelineDefinition = useCallback((): PipelineDefinitionDTO => {
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        agent: n.data.agent,
        tier: n.data.tier,
        budget_pct: n.data.budget_pct,
      })),
      edges: edges.map((e) => ({
        from: e.source,
        to: e.target,
        condition: null,
      })),
    };
  }, [nodes, edges]);

  return {
    nodes,
    edges,
    isDirty,
    selectedNodeId,
    onNodesChange,
    onEdgesChange,
    onConnect,
    selectNode,
    updateNode,
    removeNode,
    resetToSaved,
    toPipelineDefinition,
  };
}
