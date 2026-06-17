# Argus Phase 1 — Scanning Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingestion agent (repo map + CodeContext), SARIF→Finding mapper, Semgrep SAST adapter, and TruffleHog secrets adapter — all deterministic, zero LLM tokens.

**Architecture:** Each scanner adapter shells out to the tool inside a subprocess, captures SARIF output, then normalizes via a shared SARIF mapper to `Finding` objects. The `IngestionAgent` builds a `CodeContext` (language map, entry points, file tree) that the agent layer re-uses via prompt caching.

**Tech Stack:** Python 3.12, subprocess, semgrep CLI, trufflehog CLI, SARIF schema, Pydantic v2.

## Global Constraints

- All constraints from foundation plan apply
- Scanner adapters are deterministic — zero LLM calls
- Raw secrets found by TruffleHog are redacted immediately on parse; only fingerprint + location stored
- Adapters run tools via `subprocess.run` with a timeout; tool binary paths are configurable via env vars
- SARIF output from tools is stored as artifacts in S3 before parsing

---

### Task 9: Ingestion agent + CodeContext

**Files:**
- Create: `core/agents/base.py`
- Create: `core/understanding/context.py`
- Create: `core/understanding/ingest.py`
- Create: `core/agents/ingestion.py`
- Create: `tests/core/agents/test_ingestion.py`
- Create: `tests/fixtures/vulnerable_python/app.py`
- Create: `tests/fixtures/vulnerable_python/requirements.txt`

**Interfaces:**
- Consumes: nothing (entry point of the pipeline)
- Produces:
  - `AgentContext(scan: Scan, skills: list[str], budget_slice_usd: float, gate: GovernanceGate)`
  - `AgentOutput(agent_id: str, data: dict, cost_usd: float, skipped: bool)`
  - `CodeContext(root: str, languages: dict[str, int], frameworks: list[str], file_count: int, repo_map: str, entry_points: list[str])`
  - `IngestionAgent.run(ctx: AgentContext) -> AgentOutput` where `output.data["code_context"]` is a `CodeContext`

- [ ] **Step 1: Create test fixture repo**

```python
# tests/fixtures/vulnerable_python/app.py
import sqlite3
import os

def get_user(username):
    conn = sqlite3.connect("users.db")
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return conn.execute(query).fetchone()

def render_comment(comment):
    # XSS vulnerability — unsanitized output
    return f"<div>{comment}</div>"

SECRET_KEY = "hardcoded-secret-abc123xyz"  # secret exposure

def read_file(path):
    # Path traversal vulnerability
    with open(os.path.join("/app/data", path)) as f:
        return f.read()
```

```
# tests/fixtures/vulnerable_python/requirements.txt
flask==2.3.0
```

- [ ] **Step 2: Write failing test**

```python
# tests/core/agents/test_ingestion.py
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from core.agents.ingestion import IngestionAgent
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Scan, ScanMode, ScanStatus, ModelTier
from core.understanding.context import CodeContext


@pytest.fixture
def ctx():
    scan = Scan(
        target_ref=str(Path("tests/fixtures/vulnerable_python").resolve()),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    gate = MagicMock()
    return AgentContext(scan=scan, skills=[], budget_slice_usd=0.25, gate=gate)


async def test_ingestion_detects_python(ctx):
    agent = IngestionAgent()
    result = await agent.run(ctx)
    assert isinstance(result, AgentOutput)
    assert result.skipped is False
    cc: CodeContext = CodeContext.model_validate(result.data["code_context"])
    assert "python" in cc.languages
    assert cc.file_count >= 1


async def test_ingestion_builds_repo_map(ctx):
    agent = IngestionAgent()
    result = await agent.run(ctx)
    cc = CodeContext.model_validate(result.data["code_context"])
    assert "app.py" in cc.repo_map
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/core/agents/test_ingestion.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement core/agents/base.py**

```python
# core/agents/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from core.model.entities import Scan

if TYPE_CHECKING:
    from core.governance.gate import GovernanceGate


@dataclass
class AgentContext:
    scan: Scan
    skills: list[str]
    budget_slice_usd: float
    gate: "GovernanceGate"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    agent_id: str
    data: dict[str, Any]
    cost_usd: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
```

- [ ] **Step 5: Implement core/understanding/context.py**

```python
# core/understanding/context.py
from __future__ import annotations
from pydantic import BaseModel


class CodeContext(BaseModel):
    root: str
    languages: dict[str, int]   # language -> file count
    frameworks: list[str]
    file_count: int
    repo_map: str               # compact text representation of file tree
    entry_points: list[str]     # files that look like entry points
    size_bytes: int = 0
```

- [ ] **Step 6: Implement core/understanding/ingest.py**

```python
# core/understanding/ingest.py
from __future__ import annotations
from pathlib import Path
import os
from core.understanding.context import CodeContext

_LANG_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".tf": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".dockerfile": "dockerfile",
}

_FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "django": ["django", "manage.py"],
    "flask": ["flask", "Flask"],
    "express": ["express"],
    "spring": ["springframework"],
    "react": ["react", "ReactDOM"],
    "fastapi": ["fastapi", "FastAPI"],
}

_ENTRY_POINT_NAMES = {"main.py", "app.py", "server.py", "index.py", "manage.py", "wsgi.py", "asgi.py"}


def build_code_context(root: str, max_files: int = 500) -> CodeContext:
    root_path = Path(root).resolve()
    lang_counts: dict[str, int] = {}
    files: list[Path] = []
    total_bytes = 0

    for fp in root_path.rglob("*"):
        if fp.is_file() and not _is_ignored(fp):
            ext = fp.suffix.lower()
            lang = _LANG_EXTENSIONS.get(ext)
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
            files.append(fp)
            total_bytes += fp.stat().st_size
            if len(files) >= max_files:
                break

    frameworks = _detect_frameworks(root_path, files)
    repo_map = _build_repo_map(root_path, files)
    entry_points = [
        str(f.relative_to(root_path))
        for f in files
        if f.name in _ENTRY_POINT_NAMES
    ]

    return CodeContext(
        root=str(root_path),
        languages=lang_counts,
        frameworks=frameworks,
        file_count=len(files),
        repo_map=repo_map,
        entry_points=entry_points,
        size_bytes=total_bytes,
    )


def _is_ignored(fp: Path) -> bool:
    ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".pytest_cache"}
    return any(part in ignored_dirs for part in fp.parts)


def _detect_frameworks(root: Path, files: list[Path]) -> list[str]:
    detected = []
    all_text = ""
    for fp in files[:50]:
        try:
            all_text += fp.read_text(errors="ignore")[:2000]
        except OSError:
            pass
    for framework, signals in _FRAMEWORK_SIGNALS.items():
        if any(s in all_text for s in signals):
            detected.append(framework)
    req_files = list(root.glob("*requirements*.txt")) + list(root.glob("package.json"))
    for rf in req_files:
        try:
            content = rf.read_text(errors="ignore")
            for framework, signals in _FRAMEWORK_SIGNALS.items():
                if framework not in detected and any(s.lower() in content.lower() for s in signals):
                    detected.append(framework)
        except OSError:
            pass
    return detected


def _build_repo_map(root: Path, files: list[Path]) -> str:
    lines = []
    for fp in sorted(files):
        rel = fp.relative_to(root)
        lines.append(str(rel))
    return "\n".join(lines)
```

- [ ] **Step 7: Implement core/agents/ingestion.py**

```python
# core/agents/ingestion.py
from __future__ import annotations
from core.agents.base import AgentContext, AgentOutput
from core.understanding.ingest import build_code_context


class IngestionAgent:
    agent_id = "ingestion"

    async def run(self, ctx: AgentContext) -> AgentOutput:
        code_context = build_code_context(ctx.scan.target_ref)
        return AgentOutput(
            agent_id=self.agent_id,
            data={"code_context": code_context.model_dump()},
            cost_usd=0.0,
        )
```

- [ ] **Step 8: Run tests — expect pass**

```bash
pytest tests/core/agents/test_ingestion.py -v
```

Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add core/agents/base.py core/understanding/ core/agents/ingestion.py \
        tests/core/agents/test_ingestion.py tests/fixtures/
git commit -m "feat: ingestion agent, CodeContext, repo map builder"
```

---

### Task 10: SARIF mapper

**Files:**
- Create: `core/scanners/base.py`
- Create: `core/scanners/sarif.py`
- Create: `tests/core/scanners/test_sarif.py`
- Create: `tests/fixtures/sample.sarif.json`

**Interfaces:**
- Consumes: raw SARIF JSON dict
- Produces:
  - `SARIFMapper.map(sarif: dict, scan_id: UUID, source_tool: str) -> list[Finding]`
  - `BaseAdapter` protocol: `async def scan(ctx: AgentContext) -> AgentOutput`

- [ ] **Step 1: Create SARIF fixture**

```json
// tests/fixtures/sample.sarif.json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "semgrep",
        "rules": [{
          "id": "python.lang.security.audit.formatted-sql-query.formatted-sql-query",
          "name": "FormattedSQLQuery",
          "shortDescription": {"text": "Formatted SQL query"},
          "properties": {
            "tags": ["CWE-89", "OWASP-A03:2021"]
          }
        }]
      }
    },
    "results": [{
      "ruleId": "python.lang.security.audit.formatted-sql-query.formatted-sql-query",
      "level": "error",
      "message": {"text": "Detected a formatted string in a SQL statement."},
      "locations": [{
        "physicalLocation": {
          "artifactLocation": {"uri": "app.py"},
          "region": {"startLine": 5, "endLine": 6, "snippet": {"text": "query = f\"SELECT * FROM users WHERE username = '{username}'\""}}
        }
      }]
    }]
  }]
}
```

- [ ] **Step 2: Write failing test**

```python
# tests/core/scanners/test_sarif.py
from __future__ import annotations
import json
import pytest
from pathlib import Path
from uuid import uuid4
from core.scanners.sarif import SARIFMapper
from core.model.entities import Severity


def test_map_single_finding():
    sarif = json.loads(Path("tests/fixtures/sample.sarif.json").read_text())
    mapper = SARIFMapper()
    scan_id = uuid4()
    findings = mapper.map(sarif, scan_id, "semgrep")
    assert len(findings) == 1
    f = findings[0]
    assert f.scan_id == scan_id
    assert f.source_tool == "semgrep"
    assert f.severity == Severity.high
    assert f.cwe == "CWE-89"
    assert f.owasp_category == "A03:2021"
    assert f.location.file == "app.py"
    assert f.location.line_start == 5


def test_dedup_key_is_stable():
    sarif = json.loads(Path("tests/fixtures/sample.sarif.json").read_text())
    mapper = SARIFMapper()
    scan_id = uuid4()
    f1 = mapper.map(sarif, scan_id, "semgrep")[0]
    f2 = mapper.map(sarif, scan_id, "semgrep")[0]
    assert f1.dedup_key == f2.dedup_key


def test_missing_cwe_is_none():
    sarif = {
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "test", "rules": [{"id": "test-rule", "name": "Test"}]}},
                  "results": [{"ruleId": "test-rule", "level": "warning",
                                "message": {"text": "test"},
                                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "foo.py"},
                                               "region": {"startLine": 1, "endLine": 1}}}]}]}]
    }
    mapper = SARIFMapper()
    findings = mapper.map(sarif, uuid4(), "test")
    assert findings[0].cwe is None
    assert findings[0].severity == Severity.medium
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/core/scanners/test_sarif.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement core/scanners/base.py**

```python
# core/scanners/base.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from core.agents.base import AgentContext, AgentOutput


@runtime_checkable
class BaseAdapter(Protocol):
    agent_id: str

    async def scan(self, ctx: AgentContext) -> AgentOutput: ...
```

- [ ] **Step 5: Implement core/scanners/sarif.py**

```python
# core/scanners/sarif.py
from __future__ import annotations
from uuid import UUID
from core.model.entities import Finding, Severity, Location


_LEVEL_MAP: dict[str, Severity] = {
    "error": Severity.high,
    "warning": Severity.medium,
    "note": Severity.low,
    "none": Severity.info,
}

_CWE_OWASP: dict[str, str] = {
    "CWE-89": "A03:2021",
    "CWE-79": "A03:2021",
    "CWE-22": "A01:2021",
    "CWE-78": "A03:2021",
    "CWE-502": "A08:2021",
    "CWE-798": "A07:2021",
    "CWE-311": "A02:2021",
    "CWE-918": "A10:2021",
    "CWE-611": "A05:2021",
    "CWE-601": "A01:2021",
}


class SARIFMapper:
    def map(self, sarif: dict, scan_id: UUID, source_tool: str) -> list[Finding]:
        findings: list[Finding] = []
        for run in sarif.get("runs", []):
            rule_meta = self._index_rules(run)
            for result in run.get("results", []):
                finding = self._map_result(result, rule_meta, scan_id, source_tool)
                if finding:
                    findings.append(finding)
        return findings

    def _index_rules(self, run: dict) -> dict[str, dict]:
        rules = {}
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            rules[rule["id"]] = rule
        return rules

    def _map_result(self, result: dict, rule_meta: dict, scan_id: UUID, source_tool: str) -> Finding | None:
        rule_id = result.get("ruleId", "unknown")
        level = result.get("level", "warning")
        severity = _LEVEL_MAP.get(level, Severity.medium)
        if severity == Severity.high and "critical" in result.get("message", {}).get("text", "").lower():
            severity = Severity.critical

        loc_data = result.get("locations", [{}])[0]
        phys = loc_data.get("physicalLocation", {})
        region = phys.get("region", {})
        file_uri = phys.get("artifactLocation", {}).get("uri", "unknown")
        line_start = region.get("startLine", 0)
        line_end = region.get("endLine", line_start)
        snippet = region.get("snippet", {}).get("text")

        rule = rule_meta.get(rule_id, {})
        tags: list[str] = rule.get("properties", {}).get("tags", [])
        cwe = next((t for t in tags if t.startswith("CWE-")), None)
        owasp = next((t for t in tags if t.startswith("OWASP-")), None)
        if owasp:
            owasp = owasp.replace("OWASP-", "")
        elif cwe and cwe in _CWE_OWASP:
            owasp = _CWE_OWASP[cwe]

        dedup_key = f"{source_tool}:{rule_id}:{file_uri}:{line_start}"

        return Finding(
            scan_id=scan_id,
            rule_id=rule_id,
            source_tool=source_tool,
            cwe=cwe,
            owasp_category=owasp,
            severity=severity,
            location=Location(file=file_uri, line_start=line_start, line_end=line_end, snippet=snippet),
            dedup_key=dedup_key,
        )
```

- [ ] **Step 6: Run — expect pass**

```bash
pytest tests/core/scanners/test_sarif.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add core/scanners/base.py core/scanners/sarif.py \
        tests/core/scanners/test_sarif.py tests/fixtures/sample.sarif.json
git commit -m "feat: SARIF mapper with CWE and OWASP mapping"
```

---

### Task 11: Semgrep adapter

**Files:**
- Create: `core/scanners/semgrep.py`
- Create: `tests/core/scanners/test_semgrep.py`

**Interfaces:**
- Consumes: `AgentContext` (uses `ctx.extra["code_context"]` for root path), `SARIFMapper`
- Produces: `AgentOutput` where `data["findings"]` is `list[dict]` (serialized `Finding` objects), `data["sarif_raw"]` is the raw SARIF dict

- [ ] **Step 1: Verify semgrep is installed**

```bash
which semgrep || pip install semgrep
semgrep --version
```

Expected: version string like `1.x.x`

- [ ] **Step 2: Write failing test**

```python
# tests/core/scanners/test_semgrep.py
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4
from core.scanners.semgrep import SemgrepAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode
from core.understanding.context import CodeContext


@pytest.fixture
def ctx():
    scan = Scan(
        target_ref=str(Path("tests/fixtures/vulnerable_python").resolve()),
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    cc = CodeContext(
        root=str(Path("tests/fixtures/vulnerable_python").resolve()),
        languages={"python": 1},
        frameworks=[],
        file_count=1,
        repo_map="app.py",
        entry_points=["app.py"],
    )
    gate = MagicMock()
    return AgentContext(
        scan=scan,
        skills=[],
        budget_slice_usd=0.0,
        gate=gate,
        extra={"code_context": cc.model_dump()},
    )


async def test_semgrep_finds_sql_injection(ctx):
    adapter = SemgrepAdapter()
    result = await adapter.scan(ctx)
    findings = result.data["findings"]
    assert len(findings) >= 1
    rule_ids = [f["rule_id"] for f in findings]
    assert any("sql" in rid.lower() or "injection" in rid.lower() for rid in rule_ids)


async def test_semgrep_cost_is_zero(ctx):
    adapter = SemgrepAdapter()
    result = await adapter.scan(ctx)
    assert result.cost_usd == 0.0
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/core/scanners/test_semgrep.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement core/scanners/semgrep.py**

```python
# core/scanners/semgrep.py
from __future__ import annotations
import json
import subprocess
import os
import tempfile
import structlog
from core.agents.base import AgentContext, AgentOutput
from core.scanners.sarif import SARIFMapper
from core.understanding.context import CodeContext

log = structlog.get_logger()

SEMGREP_BIN = os.environ.get("SEMGREP_BIN", "semgrep")
SEMGREP_TIMEOUT = int(os.environ.get("SEMGREP_TIMEOUT", "120"))


class SemgrepAdapter:
    agent_id = "sast_semgrep"

    def __init__(self) -> None:
        self._mapper = SARIFMapper()

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        cc = CodeContext.model_validate(ctx.extra.get("code_context", {}))
        root = cc.root

        with tempfile.NamedTemporaryFile(suffix=".sarif.json", delete=False) as tmp:
            sarif_path = tmp.name

        cmd = [
            SEMGREP_BIN, "scan",
            "--config", "auto",
            "--sarif",
            "--output", sarif_path,
            "--timeout", str(SEMGREP_TIMEOUT),
            "--no-git-ignore",
            root,
        ]

        log.info("semgrep_scan_start", root=root, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SEMGREP_TIMEOUT + 10,
            )
            if proc.returncode not in (0, 1):  # 0=clean, 1=findings found
                log.warning("semgrep_nonzero_exit", returncode=proc.returncode, stderr=proc.stderr[:500])
        except subprocess.TimeoutExpired:
            log.error("semgrep_timeout", root=root)
            return AgentOutput(agent_id=self.agent_id, data={"findings": [], "sarif_raw": {}},
                               cost_usd=0.0, skipped=True, skip_reason="semgrep_timeout")

        try:
            with open(sarif_path) as f:
                sarif = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            log.error("semgrep_sarif_parse_error", error=str(e))
            return AgentOutput(agent_id=self.agent_id, data={"findings": [], "sarif_raw": {}},
                               cost_usd=0.0, skipped=True, skip_reason="sarif_parse_error")
        finally:
            os.unlink(sarif_path)

        findings = self._mapper.map(sarif, ctx.scan.id, "semgrep")
        log.info("semgrep_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={
                "findings": [f.model_dump(mode="json") for f in findings],
                "sarif_raw": sarif,
            },
            cost_usd=0.0,
        )
```

- [ ] **Step 5: Run — expect pass**

```bash
pytest tests/core/scanners/test_semgrep.py -v
```

Expected: 2 passed. (Semgrep must be installed and have network access for `--config auto` on first run.)

- [ ] **Step 6: Commit**

```bash
git add core/scanners/semgrep.py tests/core/scanners/test_semgrep.py
git commit -m "feat: Semgrep SAST adapter with SARIF output"
```

---

### Task 12: TruffleHog secrets adapter

**Files:**
- Create: `core/scanners/trufflehog.py`
- Create: `tests/core/scanners/test_trufflehog.py`

**Interfaces:**
- Consumes: `AgentContext` (uses `ctx.scan.target_ref` as filesystem path)
- Produces: `AgentOutput` where `data["findings"]` is `list[dict]` — each finding has a `location` and `dedup_key`; raw secret value is replaced with `[REDACTED]` and a `fingerprint` field is added

- [ ] **Step 1: Verify trufflehog is installed**

```bash
which trufflehog || brew install trufflehog
trufflehog --version
```

Expected: version string.

- [ ] **Step 2: Write failing test**

```python
# tests/core/scanners/test_trufflehog.py
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
from core.scanners.trufflehog import TruffleHogAdapter
from core.agents.base import AgentContext
from core.model.entities import Scan, ScanMode
from core.understanding.context import CodeContext


@pytest.fixture
def ctx():
    root = str(Path("tests/fixtures/vulnerable_python").resolve())
    scan = Scan(target_ref=root, pipeline_config_id=uuid4(), mode=ScanMode.at_rest)
    cc = CodeContext(root=root, languages={"python": 1}, frameworks=[], file_count=1,
                     repo_map="app.py", entry_points=[])
    gate = MagicMock()
    return AgentContext(scan=scan, skills=[], budget_slice_usd=0.0, gate=gate,
                        extra={"code_context": cc.model_dump()})


async def test_trufflehog_finds_secret(ctx):
    adapter = TruffleHogAdapter()
    result = await adapter.scan(ctx)
    findings = result.data["findings"]
    # Our fixture has SECRET_KEY = "hardcoded-secret-abc123xyz"
    assert len(findings) >= 1
    for f in findings:
        assert "[REDACTED]" not in str(f.get("location", ""))
        # raw secret must not appear in findings data
        assert "hardcoded-secret-abc123xyz" not in str(f)


async def test_trufflehog_cost_is_zero(ctx):
    adapter = TruffleHogAdapter()
    result = await adapter.scan(ctx)
    assert result.cost_usd == 0.0
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/core/scanners/test_trufflehog.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement core/scanners/trufflehog.py**

```python
# core/scanners/trufflehog.py
from __future__ import annotations
import json
import subprocess
import os
import structlog
from uuid import uuid4
from core.agents.base import AgentContext, AgentOutput
from core.model.entities import Finding, Severity, Location
from core.model.redaction import fingerprint

log = structlog.get_logger()

TRUFFLEHOG_BIN = os.environ.get("TRUFFLEHOG_BIN", "trufflehog")
TRUFFLEHOG_TIMEOUT = int(os.environ.get("TRUFFLEHOG_TIMEOUT", "60"))


class TruffleHogAdapter:
    agent_id = "secrets_trufflehog"

    async def scan(self, ctx: AgentContext) -> AgentOutput:
        root = ctx.scan.target_ref

        cmd = [
            TRUFFLEHOG_BIN, "filesystem",
            "--directory", root,
            "--json",
            "--no-update",
        ]

        log.info("trufflehog_scan_start", root=root, scan_id=str(ctx.scan.id))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TRUFFLEHOG_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            log.error("trufflehog_timeout", root=root)
            return AgentOutput(agent_id=self.agent_id, data={"findings": []},
                               cost_usd=0.0, skipped=True, skip_reason="trufflehog_timeout")

        findings = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            raw = event.get("Raw") or event.get("RawV2") or ""
            fp = fingerprint(raw) if raw else "unknown"

            source = event.get("SourceMetadata", {}).get("Data", {})
            file_path = (
                source.get("Filesystem", {}).get("file")
                or source.get("Git", {}).get("file")
                or "unknown"
            )
            line_num = int(
                source.get("Filesystem", {}).get("line")
                or source.get("Git", {}).get("line")
                or 0
            )

            finding = Finding(
                scan_id=ctx.scan.id,
                rule_id=f"secrets.{event.get('DetectorName', 'generic').lower()}",
                source_tool="trufflehog",
                cwe="CWE-798",
                owasp_category="A07:2021",
                severity=Severity.critical,
                confidence=float(event.get("Verified", False)),
                location=Location(
                    file=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    snippet="[REDACTED]",  # never store raw secret
                ),
                dedup_key=f"trufflehog:{event.get('DetectorName', 'generic')}:{fp[:16]}",
            )
            findings.append(finding)

        log.info("trufflehog_scan_complete", finding_count=len(findings), scan_id=str(ctx.scan.id))

        return AgentOutput(
            agent_id=self.agent_id,
            data={"findings": [f.model_dump(mode="json") for f in findings]},
            cost_usd=0.0,
        )
```

- [ ] **Step 5: Run — expect pass**

```bash
pytest tests/core/scanners/test_trufflehog.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/trufflehog.py tests/core/scanners/test_trufflehog.py
git commit -m "feat: TruffleHog secrets adapter with immediate redaction"
```

---

*Scanning plan complete. Continue with [2026-06-17-phase1-agents-api.md] for Tasks 13–16 (triage, explainer, orchestrator, FastAPI).*
