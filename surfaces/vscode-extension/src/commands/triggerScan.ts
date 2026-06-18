// surfaces/vscode-extension/src/commands/triggerScan.ts
import * as vscode from "vscode";
import type { FindingsTreeProvider } from "../providers/FindingsTreeProvider";
import type { FindingCodeLensProvider } from "../providers/FindingCodeLensProvider";

const APPROACHES = [
  { label: "Penetration Testing", value: "penetration_testing" },
  { label: "Adversary Emulation", value: "adversary_emulation" },
  { label: "Assumed Breach", value: "assumed_breach" },
  { label: "Blue Team", value: "blue_team" },
  { label: "Purple Team", value: "purple_team" },
];

const MODES = [
  { label: "At Rest — full scan", value: "at_rest" },
  { label: "Real Time — diff only", value: "real_time" },
];

function getApiBase(): string {
  return (
    vscode.workspace
      .getConfiguration("argus")
      .get<string>("apiBase") ?? "http://localhost:8000"
  );
}

export function registerTriggerScanCommand(
  context: vscode.ExtensionContext,
  treeProvider: FindingsTreeProvider,
  codeLensProvider: FindingCodeLensProvider
): vscode.Disposable {
  return vscode.commands.registerCommand("argus.triggerScan", async () => {
    // --- target ref ---
    const workspaceRoot =
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";

    const targetRef = await vscode.window.showInputBox({
      title: "Argus: Target",
      prompt: "Local path or github.com/org/repo@branch",
      value: workspaceRoot,
      ignoreFocusOut: true,
    });
    if (!targetRef) return;

    // --- mode ---
    const modeItem = await vscode.window.showQuickPick(
      MODES.map((m) => ({ label: m.label, detail: m.value })),
      { title: "Argus: Scan Mode", ignoreFocusOut: true }
    );
    if (!modeItem) return;

    // --- approach ---
    const approachItem = await vscode.window.showQuickPick(
      APPROACHES.map((a) => ({ label: a.label, detail: a.value })),
      { title: "Argus: Security Approach", ignoreFocusOut: true }
    );
    if (!approachItem) return;

    // --- trigger ---
    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Argus: Starting scan…",
        cancellable: false,
      },
      async () => {
        try {
          const resp = await fetch(`${getApiBase()}/api/v1/scans/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              target_ref: targetRef,
              mode: modeItem.detail,
              approach: approachItem.detail,
            }),
          });

          if (!resp.ok) {
            const body = await resp.text();
            throw new Error(`${resp.status}: ${body}`);
          }

          const data = (await resp.json()) as { scan_id: string };
          vscode.window.showInformationMessage(
            `Argus scan started (ID: ${data.scan_id})`,
            "View Findings"
          ).then((sel) => {
            if (sel === "View Findings") {
              treeProvider.selectScan(data.scan_id);
            }
          });
        } catch (err) {
          vscode.window.showErrorMessage(`Argus scan failed: ${String(err)}`);
        }
      }
    );
  });
}
