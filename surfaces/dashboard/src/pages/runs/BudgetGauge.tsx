interface Props {
  usedUsd: number;
  limitUsd?: number;
}

export function BudgetGauge({ usedUsd, limitUsd = 5 }: Props) {
  const pct = Math.min((usedUsd / limitUsd) * 100, 100);
  const barColor = pct >= 80 ? "#ef4444" : pct >= 50 ? "#f59e0b" : "#A100FF";

  return (
    <div className="bg-white rounded-xl shadow-card p-4 min-w-[200px]">
      <div className="flex items-center justify-between mb-1">
        <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Budget</p>
        <span className="text-[11px] font-mono text-gray-500">{pct.toFixed(0)}%</span>
      </div>
      <p className="text-lg font-mono font-bold text-gray-900">
        ${usedUsd.toFixed(3)}
        <span className="text-gray-400 text-sm font-normal"> / ${limitUsd}</span>
      </p>
      <div className="mt-2.5 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
    </div>
  );
}
