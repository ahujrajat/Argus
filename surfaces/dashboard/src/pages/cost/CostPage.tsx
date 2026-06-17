import { useQuery } from "@tanstack/react-query";
import { api, CostEntryDTO } from "../../api/client";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const TIER_COLOR: Record<string, string> = {
  fast: "#6366f1",
  balanced: "#f59e0b",
  top: "#ef4444",
};

export function CostPage() {
  const { data: summary } = useQuery({
    queryKey: ["cost-summary"],
    queryFn: api.getCostSummary,
  });
  const { data: ledger } = useQuery({
    queryKey: ["cost-ledger"],
    queryFn: api.getCostLedger,
  });

  const tierTotals = (ledger ?? []).reduce<Record<string, number>>((acc, e) => {
    acc[e.tier] = (acc[e.tier] ?? 0) + e.cost_usd;
    return acc;
  }, {});

  const tierChartData = Object.entries(tierTotals).map(([tier, cost]) => ({
    tier,
    cost,
  }));

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-2xl font-bold">Cost & Usage</h1>

      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard
            label="Total spend"
            value={`$${summary.total_cost_usd.toFixed(4)}`}
          />
          <StatCard
            label="Tokens in"
            value={summary.total_tokens_in.toLocaleString()}
          />
          <StatCard
            label="LLM calls"
            value={summary.total_calls.toLocaleString()}
          />
        </div>
      )}

      {tierChartData.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Spend by tier</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={tierChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="tier" stroke="#9CA3AF" />
              <YAxis
                stroke="#9CA3AF"
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
              />
              <Tooltip
                contentStyle={{
                  background: "#1F2937",
                  border: "none",
                  borderRadius: 8,
                }}
                formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]}
              />
              <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                {tierChartData.map((entry) => (
                  <Cell
                    key={entry.tier}
                    fill={TIER_COLOR[entry.tier] ?? "#6B7280"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-4">Ledger</h2>
        <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700 text-xs font-semibold text-gray-400 uppercase tracking-wide grid grid-cols-5 gap-4">
            <span>Scope</span>
            <span>Model</span>
            <span>Tier</span>
            <span>Tokens in/out</span>
            <span>Cost</span>
          </div>
          {(ledger ?? []).slice(0, 50).map((e: CostEntryDTO) => (
            <div
              key={e.id}
              className="px-4 py-2.5 border-b border-gray-800 grid grid-cols-5 gap-4 text-sm"
            >
              <span className="text-gray-400 truncate font-mono text-xs">
                {e.scope_type}
              </span>
              <span className="font-mono text-xs text-gray-300 truncate">
                {e.model_id.split("-").slice(-2).join("-")}
              </span>
              <span>
                <span
                  className="px-2 py-0.5 rounded text-xs font-medium"
                  style={{
                    background: (TIER_COLOR[e.tier] ?? "#6B7280") + "33",
                    color: TIER_COLOR[e.tier] ?? "#6B7280",
                  }}
                >
                  {e.tier}
                </span>
              </span>
              <span className="font-mono text-xs text-gray-400">
                {e.tokens_in.toLocaleString()} / {e.tokens_out.toLocaleString()}
              </span>
              <span className="font-mono text-xs text-emerald-400">
                ${e.cost_usd.toFixed(4)}
              </span>
            </div>
          ))}
          {(ledger ?? []).length === 0 && (
            <div className="px-4 py-8 text-center text-gray-600 text-sm">
              No cost entries yet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-5">
      <p className="text-xs text-gray-500 uppercase tracking-wide font-semibold mb-1">
        {label}
      </p>
      <p className="text-2xl font-bold font-mono">{value}</p>
    </div>
  );
}
