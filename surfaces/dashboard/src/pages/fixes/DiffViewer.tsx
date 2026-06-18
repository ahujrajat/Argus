// surfaces/dashboard/src/pages/fixes/DiffViewer.tsx

interface DiffViewerProps {
  diff: string;
}

type LineKind = "added" | "removed" | "context" | "header";

interface DiffLine {
  kind: LineKind;
  text: string;
}

function parseDiff(diff: string): DiffLine[] {
  return diff.split("\n").map((line): DiffLine => {
    if (line.startsWith("+++ ") || line.startsWith("--- ") || line.startsWith("@@ ")) {
      return { kind: "header", text: line };
    }
    if (line.startsWith("+")) return { kind: "added", text: line };
    if (line.startsWith("-")) return { kind: "removed", text: line };
    return { kind: "context", text: line };
  });
}

const KIND_STYLES: Record<LineKind, string> = {
  added: "bg-green-50 text-green-700",
  removed: "bg-red-50 text-red-700",
  context: "bg-gray-50 text-gray-700",
  header: "bg-gray-100 text-gray-500 font-semibold",
};

export function DiffViewer({ diff }: DiffViewerProps) {
  const lines = parseDiff(diff);

  if (!diff.trim()) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
        No diff available
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-lg border border-gray-200 bg-white">
      <pre className="text-xs font-mono leading-5">
        {lines.map((line, i) => (
          <div
            key={i}
            className={`px-4 py-0.5 whitespace-pre ${KIND_STYLES[line.kind]}`}
          >
            {line.text || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}
