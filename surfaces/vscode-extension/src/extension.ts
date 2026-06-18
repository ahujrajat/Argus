// surfaces/vscode-extension/src/extension.ts
import * as vscode from "vscode";
import { registerTriggerScanCommand } from "./commands/triggerScan";
import { FindingsTreeProvider } from "./providers/FindingsTreeProvider";
import { FindingCodeLensProvider, registerShowFindingDetailCommand } from "./providers/FindingCodeLensProvider";

let _disposables: vscode.Disposable[] = [];

export function activate(context: vscode.ExtensionContext): void {
  const treeProvider = new FindingsTreeProvider();
  const codeLensProvider = new FindingCodeLensProvider();

  // Tree view
  const treeView = vscode.window.createTreeView("argus.findingsView", {
    treeDataProvider: treeProvider,
    showCollapseAll: true,
  });

  // CodeLens
  const codeLensRegistration = vscode.languages.registerCodeLensProvider(
    { scheme: "file" },
    codeLensProvider
  );

  // Commands
  const triggerCmd = registerTriggerScanCommand(context, treeProvider, codeLensProvider);
  const detailCmd = registerShowFindingDetailCommand();

  _disposables = [treeView, codeLensRegistration, triggerCmd, detailCmd, treeProvider, codeLensProvider];
  context.subscriptions.push(..._disposables);
}

export function deactivate(): void {
  for (const d of _disposables) {
    d.dispose();
  }
  _disposables = [];
}
