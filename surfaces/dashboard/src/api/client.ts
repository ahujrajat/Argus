const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type SecurityApproach =
  | "penetration_testing"
  | "adversary_emulation"
  | "breach_and_attack_simulation"
  | "assumed_breach"
  | "blue_team"
  | "purple_team";

export const APPROACH_LABELS: Record<SecurityApproach, string> = {
  penetration_testing: "Penetration Testing",
  adversary_emulation: "Adversary Emulation",
  breach_and_attack_simulation: "Breach & Attack Simulation",
  assumed_breach: "Assumed Breach",
  blue_team: "Blue Team",
  purple_team: "Purple Team",
};

export const APPROACH_DESCRIPTIONS: Record<SecurityApproach, string> = {
  penetration_testing: "Breadth-first: find and exploit all vulnerabilities in scope",
  adversary_emulation: "Replay threat actor TTPs mapped to MITRE ATT&CK",
  breach_and_attack_simulation: "Validate controls: would WAF/SIEM/EDR catch this?",
  assumed_breach: "Post-compromise: lateral movement, privilege escalation, persistence",
  blue_team: "Defensive: detection engineering, hardening, control gap analysis",
  purple_team: "Red + blue feedback loop: every attack paired with a detection rule",
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

export interface FindingDTO {
  id: string;
  rule_id: string;
  source_tool: string;
  cwe: string | null;
  owasp_category: string | null;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: number;
  exploit_likelihood: number;
  reachability: string | null;
  location: { file: string; line_start: number; line_end: number; snippet?: string };
  status: string;
  explanation: string | null;
  attack_scenario?: string;
  priority_score?: number;
}

export interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  approach: SecurityApproach;
  cost_usd: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface CostEntryDTO {
  id: string;
  scope_type: string;
  scope_id: string;
  tokens_in: number;
  tokens_out: number;
  tier: string;
  provider: string;
  model_id: string;
  cost_usd: number;
  timestamp: string;
}

export interface NodeConfigDTO {
  id: string;
  agent: string;
  tier: string;
  budget_pct: number;
}

export interface EdgeDTO {
  from: string;
  to: string;
  condition: string | null;
}

export interface PipelineDefinitionDTO {
  nodes: NodeConfigDTO[];
  edges: EdgeDTO[];
}

export interface PipelineListItem {
  id: string;
  name: string;
  version: number;
  is_default: boolean;
  is_factory: boolean;
}

export interface PipelineDetailDTO {
  id: string;
  name: string;
  version: number;
  is_default: boolean;
  is_factory: boolean;
  definition: PipelineDefinitionDTO;
}

export interface FixDTO {
  id: string;
  finding_id: string;
  diff: string;
  test: string | null;
  explanation: string;
  validation_result: {
    applied: boolean;
    finding_cleared: boolean;
    new_findings: string[];
    error: string | null;
  } | null;
  status: "proposed" | "applied" | "pr_opened" | "rejected" | "needs_attention";
  reviewer: string | null;
  audit_ref: string | null;
}

export interface TriggerScanRequest {
  target_ref: string;
  mode?: string;
  approach?: SecurityApproach;
  pipeline_config_name?: string;
}

export const api = {
  listScans: () => get<ScanDTO[]>("/api/v1/scans/"),
  triggerScan: (body: TriggerScanRequest) =>
    post<{ scan_id: string }>("/api/v1/scans/", body),
  getScanFindings: (scanId: string) =>
    get<FindingDTO[]>(`/api/v1/scans/${scanId}/findings`),
  getCostLedger: () => get<CostEntryDTO[]>("/api/v1/cost/ledger"),
  getCostSummary: () =>
    get<{
      total_cost_usd: number;
      total_tokens_in: number;
      total_calls: number;
    }>("/api/v1/cost/summary"),
  listScanFixes: (scanId: string) =>
    get<FixDTO[]>(`/api/v1/scans/${scanId}/fixes`),
  applyFix: (fixId: string) =>
    post<{ status: string; fix_id: string }>(`/api/v1/fixes/${fixId}/apply`, {}),
  rejectFix: (fixId: string, reason: string) =>
    post<{ status: string; fix_id: string }>(`/api/v1/fixes/${fixId}/reject`, { reason }),
  getScan: (id: string) => get<ScanDTO>(`/api/v1/scans/${id}`),
  cancelScan: (id: string) => del(`/api/v1/scans/${id}`),
  listPipelines: () => get<PipelineListItem[]>("/api/v1/pipelines"),
  getPipeline: (id: string) => get<PipelineDetailDTO>(`/api/v1/pipelines/${id}`),
  createPipeline: (body: { name: string; definition: PipelineDefinitionDTO; is_default?: boolean }) =>
    post<PipelineDetailDTO>("/api/v1/pipelines", body),
  updatePipeline: (id: string, body: { definition: PipelineDefinitionDTO; is_default?: boolean }) =>
    put<PipelineDetailDTO>(`/api/v1/pipelines/${id}`, body),
  deletePipeline: (id: string) => del(`/api/v1/pipelines/${id}`),
  clonePipeline: (id: string, name: string) =>
    post<PipelineDetailDTO>(`/api/v1/pipelines/${id}/clone`, { name }),
};
