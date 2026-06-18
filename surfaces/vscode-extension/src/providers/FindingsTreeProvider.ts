// surfaces/vscode-extension/src/providers/FindingsTreeProvider.ts
import * as vscode from "vscode";

interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
}

interface FindingDTO {
  id: string;
  rule_id: string;
  severity: string;
  location: { file: string; line_start: number };
  explanation: string | null;
  status: string;
}

class ScanItem extends vscode.TreeItem {
  constructor(public readonly scan: ScanDTO) {
    super(
      scan.target_ref.split("/").at(-1) ?? scan.target_ref,
      vscode.TreeItemCollapsibleState.Collapsed
    );
    this.description = `${scan.status} · ${scan.id.slice(0, 8)}`;
    this.tooltip = `Scan ${scan.id}\nTarget: ${scan.target_ref}\nStatus: ${scan.status}`;
    this.contextValue = "scan";
  }
}

class FindingItem extends vscode.TreeItem {
  constructor(public readonly finding: FindingDTO, scanId: string) {
    const filename = finding.location.file.split("/").at(-1) ?? finding.location.file;
    super(
      `${finding.rule_id} — ${filename}:${finding.location.line_start}`,
      vscode.TreeItemCollapsibleState.None
    );
    this.description = finding.severity.toUpperCase();
    this.tooltip = finding.explanation ?? finding.rule_id;
    this.contextValue = "finding";
    this.iconPath = new vscode.ThemeIcon(
      finding.severity === "critical" || finding.severity === "high"
        ? "error"
        : finding.severity === "medium"
        ? "warning"
        : "info"
    );
    this.command = {
      command: "argus.showFindingDetail",
      title: "Show Finding",
      arguments: [finding],
    };
  }
}

type TreeNode = ScanItem | FindingItem;

export class FindingsTreeProvider
  implements vscode.TreeDataProvider<TreeNode>, vscode.Disposable
{
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _scans: ScanDTO[] = [];
  private _findings = new Map<string, FindingDTO[]>();
  private _selectedScanId: string | null = null;
  private _timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this._startPolling();
  }

  selectScan(scanId: string): void {
    this._selectedScanId = scanId;
    this._refresh();
  }

  private _startPolling(): void {
    this._timer = setInterval(() => this._refresh(), 5000);
  }

  private async _refresh(): Promise<void> {
    try {
      const apiBase = vscode.workspace
        .getConfiguration("argus")
        .get<string>("apiBase") ?? "http://localhost:8000";

      const resp = await fetch(`${apiBase}/api/v1/scans/`);
      if (resp.ok) {
        this._scans = (await resp.json()) as ScanDTO[];
      }

      if (this._selectedScanId) {
        const fResp = await fetch(
          `${apiBase}/api/v1/scans/${this._selectedScanId}/findings`
        );
        if (fResp.ok) {
          this._findings.set(
            this._selectedScanId,
            (await fResp.json()) as FindingDTO[]
          );
        }
      }
    } catch {
      // Silently ignore when API is unreachable
    }
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TreeNode): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TreeNode): TreeNode[] {
    if (!element) {
      return this._scans.map((s) => new ScanItem(s));
    }
    if (element instanceof ScanItem) {
      return (this._findings.get(element.scan.id) ?? []).map(
        (f) => new FindingItem(f, element.scan.id)
      );
    }
    return [];
  }

  updateFindings(scanId: string, findings: FindingDTO[]): void {
    this._findings.set(scanId, findings);
    this._onDidChangeTreeData.fire();
  }

  dispose(): void {
    if (this._timer !== null) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._onDidChangeTreeData.dispose();
  }
}
