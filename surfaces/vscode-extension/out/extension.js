"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/extension.ts
var extension_exports = {};
__export(extension_exports, {
  activate: () => activate,
  deactivate: () => deactivate
});
module.exports = __toCommonJS(extension_exports);
var vscode4 = __toESM(require("vscode"));

// src/commands/triggerScan.ts
var vscode = __toESM(require("vscode"));
var APPROACHES = [
  { label: "Penetration Testing", value: "penetration_testing" },
  { label: "Adversary Emulation", value: "adversary_emulation" },
  { label: "Assumed Breach", value: "assumed_breach" },
  { label: "Blue Team", value: "blue_team" },
  { label: "Purple Team", value: "purple_team" }
];
var MODES = [
  { label: "At Rest \u2014 full scan", value: "at_rest" },
  { label: "Real Time \u2014 diff only", value: "real_time" }
];
function getApiBase() {
  return vscode.workspace.getConfiguration("argus").get("apiBase") ?? "http://localhost:8000";
}
function registerTriggerScanCommand(context, treeProvider, codeLensProvider) {
  return vscode.commands.registerCommand("argus.triggerScan", async () => {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
    const targetRef = await vscode.window.showInputBox({
      title: "Argus: Target",
      prompt: "Local path or github.com/org/repo@branch",
      value: workspaceRoot,
      ignoreFocusOut: true
    });
    if (!targetRef)
      return;
    const modeItem = await vscode.window.showQuickPick(
      MODES.map((m) => ({ label: m.label, detail: m.value })),
      { title: "Argus: Scan Mode", ignoreFocusOut: true }
    );
    if (!modeItem)
      return;
    const approachItem = await vscode.window.showQuickPick(
      APPROACHES.map((a) => ({ label: a.label, detail: a.value })),
      { title: "Argus: Security Approach", ignoreFocusOut: true }
    );
    if (!approachItem)
      return;
    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Argus: Starting scan\u2026",
        cancellable: false
      },
      async () => {
        try {
          const resp = await fetch(`${getApiBase()}/api/v1/scans/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              target_ref: targetRef,
              mode: modeItem.detail,
              approach: approachItem.detail
            })
          });
          if (!resp.ok) {
            const body = await resp.text();
            throw new Error(`${resp.status}: ${body}`);
          }
          const data = await resp.json();
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

// src/providers/FindingsTreeProvider.ts
var vscode2 = __toESM(require("vscode"));
var ScanItem = class extends vscode2.TreeItem {
  constructor(scan) {
    super(
      scan.target_ref.split("/").at(-1) ?? scan.target_ref,
      vscode2.TreeItemCollapsibleState.Collapsed
    );
    this.scan = scan;
    this.description = `${scan.status} \xB7 ${scan.id.slice(0, 8)}`;
    this.tooltip = `Scan ${scan.id}
Target: ${scan.target_ref}
Status: ${scan.status}`;
    this.contextValue = "scan";
  }
};
var FindingItem = class extends vscode2.TreeItem {
  constructor(finding, scanId) {
    const filename = finding.location.file.split("/").at(-1) ?? finding.location.file;
    super(
      `${finding.rule_id} \u2014 ${filename}:${finding.location.line_start}`,
      vscode2.TreeItemCollapsibleState.None
    );
    this.finding = finding;
    this.description = finding.severity.toUpperCase();
    this.tooltip = finding.explanation ?? finding.rule_id;
    this.contextValue = "finding";
    this.iconPath = new vscode2.ThemeIcon(
      finding.severity === "critical" || finding.severity === "high" ? "error" : finding.severity === "medium" ? "warning" : "info"
    );
    this.command = {
      command: "argus.showFindingDetail",
      title: "Show Finding",
      arguments: [finding]
    };
  }
};
var FindingsTreeProvider = class {
  _onDidChangeTreeData = new vscode2.EventEmitter();
  onDidChangeTreeData = this._onDidChangeTreeData.event;
  _scans = [];
  _findings = /* @__PURE__ */ new Map();
  _selectedScanId = null;
  _timer = null;
  constructor() {
    this._startPolling();
  }
  selectScan(scanId) {
    this._selectedScanId = scanId;
    this._refresh();
  }
  _startPolling() {
    this._timer = setInterval(() => this._refresh(), 5e3);
  }
  async _refresh() {
    try {
      const apiBase = vscode2.workspace.getConfiguration("argus").get("apiBase") ?? "http://localhost:8000";
      const resp = await fetch(`${apiBase}/api/v1/scans/`);
      if (resp.ok) {
        this._scans = await resp.json();
      }
      if (this._selectedScanId) {
        const fResp = await fetch(
          `${apiBase}/api/v1/scans/${this._selectedScanId}/findings`
        );
        if (fResp.ok) {
          this._findings.set(
            this._selectedScanId,
            await fResp.json()
          );
        }
      }
    } catch {
    }
    this._onDidChangeTreeData.fire();
  }
  getTreeItem(element) {
    return element;
  }
  getChildren(element) {
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
  updateFindings(scanId, findings) {
    this._findings.set(scanId, findings);
    this._onDidChangeTreeData.fire();
  }
  dispose() {
    if (this._timer !== null) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._onDidChangeTreeData.dispose();
  }
};

// src/providers/FindingCodeLensProvider.ts
var vscode3 = __toESM(require("vscode"));
var SEVERITY_EMOJI = {
  critical: "\u{1F534}",
  high: "\u{1F7E0}",
  medium: "\u{1F7E1}",
  low: "\u{1F535}",
  info: "\u26AA"
};
var FindingCodeLensProvider = class {
  _onDidChangeCodeLenses = new vscode3.EventEmitter();
  onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;
  // file path → findings on that file
  _findingsByFile = /* @__PURE__ */ new Map();
  updateFindings(findings) {
    this._findingsByFile.clear();
    for (const f of findings) {
      const abs = f.location.file;
      if (!this._findingsByFile.has(abs)) {
        this._findingsByFile.set(abs, []);
      }
      this._findingsByFile.get(abs).push(f);
    }
    this._onDidChangeCodeLenses.fire();
  }
  provideCodeLenses(document) {
    const findings = this._findingsByFile.get(document.uri.fsPath) ?? [];
    return findings.map((f) => {
      const line = Math.max(0, f.location.line_start - 1);
      const range = new vscode3.Range(line, 0, line, 0);
      const emoji = SEVERITY_EMOJI[f.severity] ?? "\u26AA";
      const label = `${emoji} Argus: ${f.rule_id}${f.cwe ? ` (${f.cwe})` : ""}`;
      return new vscode3.CodeLens(range, {
        title: label,
        command: "argus.showFindingDetail",
        arguments: [f]
      });
    });
  }
  dispose() {
    this._onDidChangeCodeLenses.dispose();
  }
};
function registerShowFindingDetailCommand() {
  return vscode3.commands.registerCommand(
    "argus.showFindingDetail",
    (finding) => {
      vscode3.window.showInformationMessage(
        `[${finding.severity.toUpperCase()}] ${finding.rule_id}
${finding.explanation ?? "No explanation available."}`,
        { modal: true }
      );
    }
  );
}

// src/extension.ts
var _disposables = [];
function activate(context) {
  const treeProvider = new FindingsTreeProvider();
  const codeLensProvider = new FindingCodeLensProvider();
  const treeView = vscode4.window.createTreeView("argus.findingsView", {
    treeDataProvider: treeProvider,
    showCollapseAll: true
  });
  const codeLensRegistration = vscode4.languages.registerCodeLensProvider(
    { scheme: "file" },
    codeLensProvider
  );
  const triggerCmd = registerTriggerScanCommand(context, treeProvider, codeLensProvider);
  const detailCmd = registerShowFindingDetailCommand();
  _disposables = [treeView, codeLensRegistration, triggerCmd, detailCmd, treeProvider, codeLensProvider];
  context.subscriptions.push(..._disposables);
}
function deactivate() {
  for (const d of _disposables) {
    d.dispose();
  }
  _disposables = [];
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  activate,
  deactivate
});
