import { useQuery } from "@tanstack/react-query";
import { api, CostEntryDTO } from "../../api/client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

const TIER_COLOR: Record<string, string> = {
  fast:     "#A100FF",
  balanced: "#f59e0b",
  top:      "#ef4444",
};

const TIER_LABEL: Record<string, string> = {
  fast: "Fast", balanced: "Balanced", top: "Top",
};

export function CostPage() {
  const { data: summary } = useQuery({ queryKey: ["cost-summary"], queryFn: api.getCostSummary });
  const { data: ledger }  = useQuery({ queryKey: ["cost-ledger"],   queryFn: api.getCostLedger });

  const tierTotals = (ledger ?? []).reduce<Record<string, number>>((acc, e) => {
    acc[e.tier] = (acc[e.tier] ?? 0) + e.cost_usd;
    return acc;
  }, {});
  const tierChartData = Object.entries(tierTotals).map(([tier, cost]) => ({ tier, cost }));

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">Cost & Usage</h1>
        <p className="text-sm text-gray-500 mt-0.5">LLM spend tracking across all scans</p>
      </div>

      {/* Stat cards */}
      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard
            label="Total spend"
            value={`$${summary.total_cost_usd.toFixed(4)}`}
            icon={<DollarIcon />}
            accent
          />
          <StatCard
            label="Tokens in"
            value={summary.total_tokens_in.toLocaleString()}
            icon={<TokenIcon />}
          />
          <StatCard
            label="LLM calls"
            value={summary.total_calls.toLocaleString()}
            icon={<CallIcon />}
          />
        </div>
      )}

      {/* Chart */}
      {tierChartData.length > 0 && (
        <div className="bg-white rounded-xl shadow-card p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Spend by tier</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={tierChartData} barCategoryGap="40%">
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
              <XAxis
                dataKey="tier"
                tick={{ fontSize: 12, fill: "#6B7280" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => TIER_LABEL[v] ?? v}
              />
              <YAxis
                tick={{ fontSize: 12, fill: "#6B7280" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
              />
              <Tooltip
                contentStyle={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]}
                cursor={{ fill: "#f5f5f7" }}
              />
              <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                {tierChartData.map((entry) => (
                  <Cell key={entry.tier} fill={TIER_COLOR[entry.tier] ?? "#A100FF"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Ledger table */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Cost Ledger</h2>
        <div className="bg-white rounded-xl shadow-card overflow-hidden">
          <div className="grid grid-cols-5 gap-4 px-4 py-2.5 bg-gray-50 border-b border-gray-100 text-[11px] font-semibold text-gray-500 uppercase tracking-wide">
            <span>Scope</span>
            <span>Model</span>
            <span>Tier</span>
            <span>Tokens in / out</span>
            <span className="text-right">Cost</span>
          </div>
          {(ledger ?? []).slice(0, 50).map((e: CostEntryDTO) => (
            <div key={e.id} className="grid grid-cols-5 gap-4 px-4 py-2.5 border-b border-gray-50 last:border-0 text-sm hover:bg-gray-50 transition-colors">
              <span className="font-mono text-xs text-gray-500 truncate">{e.scope_type}</span>
              <span className="font-mono text-xs text-gray-700 truncate">{e.model_id.split("-").slice(-2).join("-")}</span>
              <span>
                <span className="px-2 py-0.5 rounded text-[11px] font-semibold"
                  style={{ background: (TIER_COLOR[e.tier] ?? "#A100FF") + "18", color: TIER_COLOR[e.tier] ?? "#A100FF" }}>
                  {TIER_LABEL[e.tier] ?? e.tier}
                </span>
              </span>
              <span className="font-mono text-xs text-gray-500">
                {e.tokens_in.toLocaleString()} / {e.tokens_out.toLocaleString()}
              </span>
              <span className="font-mono text-xs text-green-600 font-semibold text-right">
                ${e.cost_usd.toFixed(4)}
              </span>
            </div>
          ))}
          {(ledger ?? []).length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">No cost entries yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon, accent }: { label: string; value: string; icon: React.ReactNode; accent?: boolean }) {
  return (
    <div className={`rounded-xl shadow-card p-5 flex items-start gap-4 ${accent ? "text-white" : "bg-white"}`}
      style={accent ? { background: "#A100FF" } : undefined}>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${accent ? "bg-white/20" : "bg-accent-50"}`}>
        <span className={accent ? "text-white" : "text-accent-DEFAULT"}>{icon}</span>
      </div>
      <div>
        <p className={`text-[11px] font-semibold uppercase tracking-wide mb-1 ${accent ? "text-white/70" : "text-gray-400"}`}>{label}</p>
        <p className={`text-2xl font-bold font-mono ${accent ? "text-white" : "text-gray-900"}`}>{value}</p>
      </div>
    </div>
  );
}

function DollarIcon() {
  return <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
function TokenIcon() {
  return <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" /></svg>;
}
function CallIcon() {
  return <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>;
}
