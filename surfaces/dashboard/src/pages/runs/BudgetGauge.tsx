interface Props {
  usedUsd: number;
  limitUsd?: number;
}

export function BudgetGauge({ usedUsd, limitUsd = 5 }: Props) {
  const pct = Math.min((usedUsd / limitUsd) * 100, 100);
  const color =
    pct >= 80 ? "bg-red-500" : pct >= 50 ? "bg-yellow-500" : "bg-emerald-500";
  return (
    <div className="bg-gray-800 rounded-lg p-4 min-w-[180px]">
      <p className="text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide">
        Budget
      </p>
      <p className="text-lg font-mono text-white">
        ${usedUsd.toFixed(3)}{" "}
        <span className="text-gray-500 text-sm">/ ${limitUsd}</span>
      </p>
      <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
