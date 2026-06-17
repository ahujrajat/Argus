import { FindingDTO } from "../../api/client";

interface Props {
  finding: FindingDTO;
  onClose: () => void;
}

const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-50 text-red-700 border border-red-200",
  high:     "bg-orange-50 text-orange-700 border border-orange-200",
  medium:   "bg-amber-50 text-amber-700 border border-amber-200",
  low:      "bg-blue-50 text-blue-700 border border-blue-200",
  info:     "bg-gray-100 text-gray-600 border border-gray-200",
};

export function FindingDetail({ finding, onClose }: Props) {
  return (
    <div className="w-[400px] flex-shrink-0 bg-white shadow-card-hover rounded-xl flex flex-col overflow-hidden border border-gray-100">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs text-gray-400 mb-1">Rule ID</p>
          <h2 className="font-mono text-sm font-bold text-gray-900 break-all leading-snug">
            {finding.rule_id}
          </h2>
        </div>
        <button
          onClick={onClose}
          className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center text-gray-500 hover:text-gray-700 transition-colors text-lg leading-none"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-5">
        {/* Metadata chips */}
        <div className="flex flex-wrap gap-1.5">
          <Chip label={finding.severity.toUpperCase()} className={SEVERITY_STYLE[finding.severity] ?? SEVERITY_STYLE.info} />
          {finding.cwe && <Chip label={finding.cwe} className="bg-gray-100 text-gray-600 border border-gray-200" />}
          {finding.owasp_category && <Chip label={`OWASP ${finding.owasp_category}`} className="bg-gray-100 text-gray-600 border border-gray-200" />}
          <Chip label={`Conf ${(finding.confidence * 100).toFixed(0)}%`} className="bg-gray-50 text-gray-500 border border-gray-200" />
          <Chip label={`Exploit ${(finding.exploit_likelihood * 100).toFixed(0)}%`} className="bg-gray-50 text-gray-500 border border-gray-200" />
        </div>

        {/* Location */}
        <Section label="Location">
          <p className="font-mono text-sm font-medium" style={{ color: "#A100FF" }}>
            {finding.location.file}:{finding.location.line_start}
          </p>
          {finding.location.snippet && (
            <pre className="mt-2 px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-700 font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed">
              {finding.location.snippet}
            </pre>
          )}
        </Section>

        {/* Reachability */}
        {finding.reachability && (
          <Section label="Reachability">
            <p className="text-sm text-gray-700 leading-relaxed">{finding.reachability}</p>
          </Section>
        )}

        {/* Attack scenario */}
        {finding.attack_scenario && (
          <div>
            <p className="text-[11px] font-semibold text-red-600 uppercase tracking-wide mb-2">Attack Scenario</p>
            <div className="px-3 py-3 bg-red-50 border-l-[3px] border-red-400 rounded-r-lg">
              <p className="text-sm text-red-800 leading-relaxed">{finding.attack_scenario}</p>
            </div>
          </div>
        )}

        {/* Explanation */}
        {finding.explanation && (
          <Section label="Explanation & Fix">
            <p className="text-sm text-gray-700 leading-relaxed">{finding.explanation}</p>
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2">{label}</p>
      {children}
    </div>
  );
}

function Chip({ label, className }: { label: string; className: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${className}`}>{label}</span>
  );
}
