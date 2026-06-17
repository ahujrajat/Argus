import { FindingDTO } from "../../api/client";

interface Props {
  finding: FindingDTO;
  onClose: () => void;
}

export function FindingDetail({ finding, onClose }: Props) {
  return (
    <div className="w-96 bg-gray-900 border border-gray-700 rounded-xl p-6 flex flex-col gap-4 overflow-auto">
      <div className="flex justify-between items-start">
        <h2 className="font-mono text-sm font-bold text-gray-200 break-all">
          {finding.rule_id}
        </h2>
        <button
          onClick={onClose}
          className="text-gray-600 hover:text-gray-300 text-xl leading-none"
        >
          ×
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <Tag label={finding.severity.toUpperCase()} color="bg-orange-600" />
        {finding.cwe && <Tag label={finding.cwe} color="bg-gray-700" />}
        {finding.owasp_category && (
          <Tag label={`OWASP ${finding.owasp_category}`} color="bg-gray-700" />
        )}
        <Tag
          label={`conf ${(finding.confidence * 100).toFixed(0)}%`}
          color="bg-gray-800"
        />
        <Tag
          label={`exploit ${(finding.exploit_likelihood * 100).toFixed(0)}%`}
          color="bg-gray-800"
        />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
          Location
        </h3>
        <p className="font-mono text-sm text-indigo-400">
          {finding.location.file}:{finding.location.line_start}
        </p>
        {finding.location.snippet && (
          <pre className="mt-2 p-3 bg-gray-800 rounded text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap">
            {finding.location.snippet}
          </pre>
        )}
      </div>

      {finding.reachability && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Reachability
          </h3>
          <p className="text-sm text-gray-300">{finding.reachability}</p>
        </div>
      )}

      {finding.attack_scenario && (
        <div>
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1">
            Attack Scenario
          </h3>
          <p className="text-sm text-gray-200 leading-relaxed">
            {finding.attack_scenario}
          </p>
        </div>
      )}

      {finding.explanation && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Explanation & Fix
          </h3>
          <p className="text-sm text-gray-300 leading-relaxed">
            {finding.explanation}
          </p>
        </div>
      )}
    </div>
  );
}

function Tag({ label, color }: { label: string; color: string }) {
  return (
    <span
      className={`${color} text-white px-2 py-0.5 rounded text-xs font-medium`}
    >
      {label}
    </span>
  );
}
