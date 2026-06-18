// surfaces/vscode-extension/src/providers/FindingCodeLensProvider.ts
import * as vscode from "vscode";

interface FindingDTO {
  id: string;
  rule_id: string;
  severity: string;
  location: { file: string; line_start: number; line_end: number };
  explanation: string | null;
  cwe: string | null;
}

const SEVERITY_EMOJI: Record<string, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🔵",
  info: "⚪",
};

export class FindingCodeLensProvider
  implements vscode.CodeLensProvider, vscode.Disposable
{
  private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

  // file path → findings on that file
  private _findingsByFile = new Map<string, FindingDTO[]>();

  updateFindings(findings: FindingDTO[]): void {
    this._findingsByFile.clear();
    for (const f of findings) {
      const abs = f.location.file;
      if (!this._findingsByFile.has(abs)) {
        this._findingsByFile.set(abs, []);
      }
      this._findingsByFile.get(abs)!.push(f);
    }
    this._onDidChangeCodeLenses.fire();
  }

  provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    const findings = this._findingsByFile.get(document.uri.fsPath) ?? [];
    return findings.map((f) => {
      const line = Math.max(0, f.location.line_start - 1);
      const range = new vscode.Range(line, 0, line, 0);
      const emoji = SEVERITY_EMOJI[f.severity] ?? "⚪";
      const label = `${emoji} Argus: ${f.rule_id}${f.cwe ? ` (${f.cwe})` : ""}`;
      return new vscode.CodeLens(range, {
        title: label,
        command: "argus.showFindingDetail",
        arguments: [f],
      });
    });
  }

  dispose(): void {
    this._onDidChangeCodeLenses.dispose();
  }
}

// Register showFindingDetail command (called from both tree and codelens)
export function registerShowFindingDetailCommand(): vscode.Disposable {
  return vscode.commands.registerCommand(
    "argus.showFindingDetail",
    (finding: FindingDTO) => {
      vscode.window.showInformationMessage(
        `[${finding.severity.toUpperCase()}] ${finding.rule_id}\n${finding.explanation ?? "No explanation available."}`,
        { modal: true }
      );
    }
  );
}
