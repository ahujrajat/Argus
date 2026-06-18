# Phase 2b — VCS Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a VCS abstraction layer with GitHub and GitLab adapters, wire PR creation into the fix-apply endpoint, and expose a TargetAuthorization CRUD API that gates all VCS write operations.

**Architecture:** A `core/vcs/` package defines a `VCSProvider` typing.Protocol and provides a factory that parses `target_ref` strings to select the correct adapter. The existing `POST /api/v1/fixes/{id}/apply` endpoint gains an optional `create_pr` flag; when set it resolves the VCS provider for the scan's target, creates a branch, commits the diff, opens a PR, and writes an AuditLogEntry for every write action. A new `core/api/routers/authorizations.py` router manages TargetAuthorization rows and acts as the gate checked before any VCS write. VCS tokens are never logged or persisted — they exist only in memory for the lifetime of the request.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async (asyncpg), httpx (raw REST — no PyGitHub / python-gitlab), respx for HTTP mocking, pytest with asyncio_mode="auto", subprocess + `patch -p1` for local diff application.

## Global Constraints

- Python ≥ 3.12; `from __future__ import annotations` in every Python file
- httpx for all outbound HTTP calls; no GitHub/GitLab SDK packages
- VCS tokens: NEVER written to logs, NEVER stored in DB, NEVER appear in exception messages — hold in memory only for the duration of the request
- TargetAuthorization must exist with `owner_confirmed=True` and a non-expired `expires_at` (or `expires_at=None`) before any VCS write operation
- Every VCS write action (branch create, commit, PR open) writes an `AuditLogEntry` with `actor="api"`
- GovernanceGate is the ONLY path to LLM calls — `core/vcs/` must never import from `core/governance/`
- All tests use pytest with `asyncio_mode = "auto"`; HTTP calls mocked with respx
- Pydantic v2 throughout — no v1 compat shims

---

### Task 1: VCS protocol, exceptions, and factory

**Files:**
- Create: `core/vcs/__init__.py`
- Create: `core/vcs/protocol.py`
- Create: `core/vcs/factory.py`
- Create: `tests/core/vcs/__init__.py`
- Create: `tests/core/vcs/test_factory.py`

**Interfaces:**
- Produces:
  - `VCSProvider` protocol (typing.Protocol) in `core/vcs/protocol.py`
  - `VCSError(message: str, status_code: int)` exception in `core/vcs/protocol.py`
  - `VCSNotSupported(message: str)` exception in `core/vcs/protocol.py`
  - `get_vcs_provider(target_ref: str, token: str) -> VCSProvider` in `core/vcs/factory.py`

- [ ] **Step 1: Write the failing factory tests**

Create `tests/core/vcs/__init__.py` (empty).

Create `tests/core/vcs/test_factory.py`:

```python
from __future__ import annotations
import pytest
from core.vcs.factory import get_vcs_provider
from core.vcs.protocol import VCSNotSupported


def test_github_target_returns_github_adapter():
    provider = get_vcs_provider("github.com/acme/myrepo@main", token="ghp_test")
    from core.vcs.github import GitHubAdapter
    assert isinstance(provider, GitHubAdapter)


def test_gitlab_com_target_returns_gitlab_adapter():
    provider = get_vcs_provider("gitlab.com/acme/myrepo@main", token="glpat_test")
    from core.vcs.gitlab import GitLabAdapter
    assert isinstance(provider, GitLabAdapter)


def test_gitlab_selfhosted_target_returns_gitlab_adapter():
    provider = get_vcs_provider("gitlab.mycompany.com/team/svc@develop", token="glpat_test")
    from core.vcs.gitlab import GitLabAdapter
    assert isinstance(provider, GitLabAdapter)


def test_local_path_raises_vcs_not_supported():
    with pytest.raises(VCSNotSupported, match="local paths cannot create PRs"):
        get_vcs_provider("/home/user/myrepo@main", token="irrelevant")


def test_unknown_host_raises_vcs_not_supported():
    with pytest.raises(VCSNotSupported):
        get_vcs_provider("bitbucket.org/acme/repo@main", token="token")


def test_github_adapter_carries_correct_token():
    provider = get_vcs_provider("github.com/acme/myrepo@main", token="ghp_secret")
    assert provider._token == "ghp_secret"


def test_gitlab_adapter_carries_correct_base_url():
    provider = get_vcs_provider("gitlab.mycompany.com/team/svc@develop", token="tok")
    assert provider._base_url == "https://gitlab.mycompany.com/api/v4"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/test_factory.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'core.vcs'`

- [ ] **Step 3: Create `core/vcs/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 4: Create `core/vcs/protocol.py`**

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable


class VCSError(Exception):
    """Raised when a VCS API call returns a 4xx or 5xx response."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class VCSNotSupported(Exception):
    """Raised when the target_ref cannot be handled by any registered adapter."""


@runtime_checkable
class VCSProvider(Protocol):
    async def create_branch(
        self, repo: str, branch: str, from_branch: str
    ) -> None: ...

    async def commit_file(
        self,
        repo: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> None: ...

    async def create_pr(
        self,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> str: ...
    # returns PR URL

    async def get_file_content(
        self, repo: str, path: str, ref: str = "main"
    ) -> str: ...
```

- [ ] **Step 5: Create stub `core/vcs/github.py` so the factory import resolves**

```python
from __future__ import annotations


class GitHubAdapter:
    def __init__(self, token: str) -> None:
        self._token = token
```

- [ ] **Step 6: Create stub `core/vcs/gitlab.py` so the factory import resolves**

```python
from __future__ import annotations


class GitLabAdapter:
    def __init__(self, token: str, base_url: str) -> None:
        self._token = token
        self._base_url = base_url
```

- [ ] **Step 7: Create `core/vcs/factory.py`**

```python
from __future__ import annotations
from core.vcs.protocol import VCSProvider, VCSNotSupported


def get_vcs_provider(target_ref: str, token: str) -> VCSProvider:
    """Parse target_ref and return the appropriate VCSProvider.

    Supported formats:
      github.com/org/repo@branch
      gitlab.com/org/repo@branch
      gitlab.<host>/org/repo@branch

    Raises VCSNotSupported for local paths (starting with '/') or
    unrecognised hosts.
    """
    if target_ref.startswith("/"):
        raise VCSNotSupported("local paths cannot create PRs")

    host = target_ref.split("/")[0]

    if host == "github.com":
        from core.vcs.github import GitHubAdapter
        return GitHubAdapter(token=token)

    if host == "gitlab.com" or host.startswith("gitlab."):
        base_url = f"https://{host}/api/v4"
        from core.vcs.gitlab import GitLabAdapter
        return GitLabAdapter(token=token, base_url=base_url)

    raise VCSNotSupported(
        f"no VCS adapter registered for host '{host}'; "
        "supported: github.com, gitlab.com, gitlab.*"
    )
```

- [ ] **Step 8: Run tests to confirm they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/test_factory.py -v
```

Expected:
```
tests/core/vcs/test_factory.py::test_github_target_returns_github_adapter PASSED
tests/core/vcs/test_factory.py::test_gitlab_com_target_returns_gitlab_adapter PASSED
tests/core/vcs/test_factory.py::test_gitlab_selfhosted_target_returns_gitlab_adapter PASSED
tests/core/vcs/test_factory.py::test_local_path_raises_vcs_not_supported PASSED
tests/core/vcs/test_factory.py::test_unknown_host_raises_vcs_not_supported PASSED
tests/core/vcs/test_factory.py::test_github_adapter_carries_correct_token PASSED
tests/core/vcs/test_factory.py::test_gitlab_adapter_carries_correct_base_url PASSED
7 passed
```

- [ ] **Step 9: Commit**

```bash
git add core/vcs/__init__.py core/vcs/protocol.py core/vcs/factory.py \
        core/vcs/github.py core/vcs/gitlab.py \
        tests/core/vcs/__init__.py tests/core/vcs/test_factory.py
git commit -m "feat(vcs): add VCSProvider protocol, exceptions, and factory"
```

---

### Task 2: GitHub adapter

**Files:**
- Modify: `core/vcs/github.py` — full implementation (replaces stub)
- Test: `tests/core/vcs/test_github.py`

**Interfaces:**
- Consumes: `VCSError`, `VCSNotSupported` from `core/vcs/protocol.py`
- Produces:
  - `GitHubAdapter(token: str)` — implements `VCSProvider`
  - `GitHubAdapter.create_branch(repo, branch, from_branch) -> None`
  - `GitHubAdapter.commit_file(repo, branch, path, content, message) -> None`
  - `GitHubAdapter.create_pr(repo, head, base, title, body) -> str`  (returns PR URL)
  - `GitHubAdapter.get_file_content(repo, path, ref="main") -> str`

- [ ] **Step 1: Install respx (if not already present)**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && uv add --dev respx
```

Expected: `Resolved ... respx` in output, no errors.

- [ ] **Step 2: Write the failing GitHub adapter tests**

Create `tests/core/vcs/test_github.py`:

```python
from __future__ import annotations
import base64
import json
import pytest
import respx
import httpx
from core.vcs.github import GitHubAdapter
from core.vcs.protocol import VCSError


OWNER = "acme"
REPO = "myrepo"
REPO_FULL = "acme/myrepo"
TOKEN = "ghp_testtoken"
BASE = "https://api.github.com"


@pytest.fixture
def adapter() -> GitHubAdapter:
    return GitHubAdapter(token=TOKEN)


# ── create_branch ────────────────────────────────────────────────────────────

@respx.mock
async def test_create_branch_success(adapter: GitHubAdapter):
    # First GET refs/heads/main to fetch SHA
    respx.get(f"{BASE}/repos/{OWNER}/{REPO}/git/refs/heads/main").mock(
        return_value=httpx.Response(
            200,
            json={"object": {"sha": "abc123"}},
        )
    )
    # POST to create ref
    respx.post(f"{BASE}/repos/{OWNER}/{REPO}/git/refs").mock(
        return_value=httpx.Response(201, json={"ref": "refs/heads/argus/fix-deadbeef"})
    )
    await adapter.create_branch(REPO_FULL, "argus/fix-deadbeef", "main")


@respx.mock
async def test_create_branch_raises_vcs_error_on_422(adapter: GitHubAdapter):
    respx.get(f"{BASE}/repos/{OWNER}/{REPO}/git/refs/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "abc123"}})
    )
    respx.post(f"{BASE}/repos/{OWNER}/{REPO}/git/refs").mock(
        return_value=httpx.Response(422, json={"message": "Reference already exists"})
    )
    with pytest.raises(VCSError) as exc_info:
        await adapter.create_branch(REPO_FULL, "argus/fix-deadbeef", "main")
    assert exc_info.value.status_code == 422


# ── commit_file ──────────────────────────────────────────────────────────────

@respx.mock
async def test_commit_file_success(adapter: GitHubAdapter):
    file_sha = "fileshaabc"
    respx.get(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/app.py"
    ).mock(
        return_value=httpx.Response(200, json={"sha": file_sha})
    )
    respx.put(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/app.py"
    ).mock(
        return_value=httpx.Response(200, json={"content": {"sha": "newsha"}})
    )
    await adapter.commit_file(
        REPO_FULL,
        "argus/fix-deadbeef",
        "src/app.py",
        "print('fixed')\n",
        "fix: patch sql injection",
    )


@respx.mock
async def test_commit_file_new_file_no_sha(adapter: GitHubAdapter):
    # File does not exist yet — GET returns 404
    respx.get(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/new.py"
    ).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    respx.put(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/new.py"
    ).mock(return_value=httpx.Response(201, json={"content": {"sha": "newsha"}}))
    await adapter.commit_file(
        REPO_FULL,
        "argus/fix-deadbeef",
        "src/new.py",
        "# new file\n",
        "fix: add missing validation",
    )


@respx.mock
async def test_commit_file_raises_vcs_error_on_403(adapter: GitHubAdapter):
    respx.get(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/app.py"
    ).mock(return_value=httpx.Response(200, json={"sha": "sha1"}))
    respx.put(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/app.py"
    ).mock(return_value=httpx.Response(403, json={"message": "Forbidden"}))
    with pytest.raises(VCSError) as exc_info:
        await adapter.commit_file(
            REPO_FULL, "argus/fix-deadbeef", "src/app.py", "x", "msg"
        )
    assert exc_info.value.status_code == 403


# ── create_pr ────────────────────────────────────────────────────────────────

@respx.mock
async def test_create_pr_returns_url(adapter: GitHubAdapter):
    respx.post(f"{BASE}/repos/{OWNER}/{REPO}/pulls").mock(
        return_value=httpx.Response(
            201,
            json={"html_url": "https://github.com/acme/myrepo/pull/42"},
        )
    )
    url = await adapter.create_pr(
        REPO_FULL,
        "argus/fix-deadbeef",
        "main",
        "fix: sql injection in login",
        "Automated fix generated by Argus.",
    )
    assert url == "https://github.com/acme/myrepo/pull/42"


@respx.mock
async def test_create_pr_raises_vcs_error_on_422(adapter: GitHubAdapter):
    respx.post(f"{BASE}/repos/{OWNER}/{REPO}/pulls").mock(
        return_value=httpx.Response(422, json={"message": "Validation Failed"})
    )
    with pytest.raises(VCSError) as exc_info:
        await adapter.create_pr(REPO_FULL, "head", "main", "title", "body")
    assert exc_info.value.status_code == 422


# ── get_file_content ─────────────────────────────────────────────────────────

@respx.mock
async def test_get_file_content_returns_decoded_string(adapter: GitHubAdapter):
    raw = "def vulnerable(): pass\n"
    encoded = base64.b64encode(raw.encode()).decode()
    respx.get(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/src/app.py"
    ).mock(
        return_value=httpx.Response(200, json={"content": encoded, "encoding": "base64"})
    )
    content = await adapter.get_file_content(REPO_FULL, "src/app.py", ref="main")
    assert content == raw


@respx.mock
async def test_get_file_content_raises_vcs_error_on_404(adapter: GitHubAdapter):
    respx.get(
        f"{BASE}/repos/{OWNER}/{REPO}/contents/missing.py"
    ).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(VCSError) as exc_info:
        await adapter.get_file_content(REPO_FULL, "missing.py")
    assert exc_info.value.status_code == 404


# ── auth header ──────────────────────────────────────────────────────────────

@respx.mock
async def test_adapter_sends_bearer_token(adapter: GitHubAdapter):
    route = respx.get(f"{BASE}/repos/{OWNER}/{REPO}/git/refs/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "abc"}})
    )
    respx.post(f"{BASE}/repos/{OWNER}/{REPO}/git/refs").mock(
        return_value=httpx.Response(201, json={})
    )
    await adapter.create_branch(REPO_FULL, "argus/fix-x", "main")
    assert route.calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/test_github.py -v 2>&1 | head -20
```

Expected: errors such as `AttributeError: 'GitHubAdapter' object has no attribute 'create_branch'`

- [ ] **Step 4: Implement `core/vcs/github.py`**

```python
from __future__ import annotations
import base64
import httpx
from core.vcs.protocol import VCSError

_API_BASE = "https://api.github.com"


class GitHubAdapter:
    """VCSProvider implementation that calls GitHub REST API v3 via raw httpx."""

    def __init__(self, token: str) -> None:
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _parse_repo(self, repo: str) -> tuple[str, str]:
        """Split 'owner/name' into (owner, name)."""
        owner, name = repo.split("/", 1)
        return owner, name

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            try:
                msg = response.json().get("message", response.text)
            except Exception:
                msg = response.text
            raise VCSError(msg, response.status_code)

    async def create_branch(
        self, repo: str, branch: str, from_branch: str
    ) -> None:
        owner, name = self._parse_repo(repo)
        async with httpx.AsyncClient() as client:
            # Resolve the SHA of from_branch
            resp = await client.get(
                f"{_API_BASE}/repos/{owner}/{name}/git/refs/heads/{from_branch}",
                headers=self._headers(),
            )
            self._raise_for_status(resp)
            sha = resp.json()["object"]["sha"]

            # Create the new ref
            resp2 = await client.post(
                f"{_API_BASE}/repos/{owner}/{name}/git/refs",
                headers=self._headers(),
                json={"ref": f"refs/heads/{branch}", "sha": sha},
            )
            self._raise_for_status(resp2)

    async def commit_file(
        self,
        repo: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> None:
        owner, name = self._parse_repo(repo)
        encoded = base64.b64encode(content.encode()).decode()
        async with httpx.AsyncClient() as client:
            # Fetch current SHA (None if file doesn't exist yet)
            get_resp = await client.get(
                f"{_API_BASE}/repos/{owner}/{name}/contents/{path}",
                headers=self._headers(),
                params={"ref": branch},
            )
            sha: str | None = None
            if get_resp.status_code == 200:
                sha = get_resp.json()["sha"]
            elif get_resp.status_code != 404:
                self._raise_for_status(get_resp)

            payload: dict = {
                "message": message,
                "content": encoded,
                "branch": branch,
            }
            if sha is not None:
                payload["sha"] = sha

            put_resp = await client.put(
                f"{_API_BASE}/repos/{owner}/{name}/contents/{path}",
                headers=self._headers(),
                json=payload,
            )
            self._raise_for_status(put_resp)

    async def create_pr(
        self,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> str:
        owner, name = self._parse_repo(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_API_BASE}/repos/{owner}/{name}/pulls",
                headers=self._headers(),
                json={"title": title, "body": body, "head": head, "base": base},
            )
            self._raise_for_status(resp)
            return resp.json()["html_url"]

    async def get_file_content(
        self, repo: str, path: str, ref: str = "main"
    ) -> str:
        owner, name = self._parse_repo(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_API_BASE}/repos/{owner}/{name}/contents/{path}",
                headers=self._headers(),
                params={"ref": ref},
            )
            self._raise_for_status(resp)
            data = resp.json()
            return base64.b64decode(data["content"]).decode()
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/test_github.py -v
```

Expected:
```
tests/core/vcs/test_github.py::test_create_branch_success PASSED
tests/core/vcs/test_github.py::test_create_branch_raises_vcs_error_on_422 PASSED
tests/core/vcs/test_github.py::test_commit_file_success PASSED
tests/core/vcs/test_github.py::test_commit_file_new_file_no_sha PASSED
tests/core/vcs/test_github.py::test_commit_file_raises_vcs_error_on_403 PASSED
tests/core/vcs/test_github.py::test_create_pr_returns_url PASSED
tests/core/vcs/test_github.py::test_create_pr_raises_vcs_error_on_422 PASSED
tests/core/vcs/test_github.py::test_get_file_content_returns_decoded_string PASSED
tests/core/vcs/test_github.py::test_get_file_content_raises_vcs_error_on_404 PASSED
tests/core/vcs/test_github.py::test_adapter_sends_bearer_token PASSED
10 passed
```

- [ ] **Step 6: Commit**

```bash
git add core/vcs/github.py tests/core/vcs/test_github.py
git commit -m "feat(vcs): implement GitHubAdapter with httpx, full test coverage"
```

---

### Task 3: GitLab adapter

**Files:**
- Modify: `core/vcs/gitlab.py` — full implementation (replaces stub)
- Test: `tests/core/vcs/test_gitlab.py`

**Interfaces:**
- Consumes: `VCSError` from `core/vcs/protocol.py`
- Produces:
  - `GitLabAdapter(token: str, base_url: str)` — implements `VCSProvider`
  - `GitLabAdapter.create_branch(repo, branch, from_branch) -> None`
  - `GitLabAdapter.commit_file(repo, branch, path, content, message) -> None`
  - `GitLabAdapter.create_pr(repo, head, base, title, body) -> str`  (returns MR web_url)
  - `GitLabAdapter.get_file_content(repo, path, ref="main") -> str`

- [ ] **Step 1: Write the failing GitLab adapter tests**

Create `tests/core/vcs/test_gitlab.py`:

```python
from __future__ import annotations
import base64
import urllib.parse
import pytest
import respx
import httpx
from core.vcs.gitlab import GitLabAdapter
from core.vcs.protocol import VCSError


REPO = "acme/myrepo"
ENCODED_REPO = urllib.parse.quote(REPO, safe="")
TOKEN = "glpat_testtoken"
BASE = "https://gitlab.com/api/v4"


@pytest.fixture
def adapter() -> GitLabAdapter:
    return GitLabAdapter(token=TOKEN, base_url=BASE)


# ── create_branch ────────────────────────────────────────────────────────────

@respx.mock
async def test_create_branch_success(adapter: GitLabAdapter):
    respx.post(f"{BASE}/projects/{ENCODED_REPO}/repository/branches").mock(
        return_value=httpx.Response(
            201,
            json={"name": "argus/fix-deadbeef"},
        )
    )
    await adapter.create_branch(REPO, "argus/fix-deadbeef", "main")


@respx.mock
async def test_create_branch_raises_vcs_error_on_400(adapter: GitLabAdapter):
    respx.post(f"{BASE}/projects/{ENCODED_REPO}/repository/branches").mock(
        return_value=httpx.Response(400, json={"message": "Branch already exists"})
    )
    with pytest.raises(VCSError) as exc_info:
        await adapter.create_branch(REPO, "argus/fix-deadbeef", "main")
    assert exc_info.value.status_code == 400


# ── commit_file ──────────────────────────────────────────────────────────────

@respx.mock
async def test_commit_file_success(adapter: GitLabAdapter):
    respx.post(f"{BASE}/projects/{ENCODED_REPO}/repository/commits").mock(
        return_value=httpx.Response(201, json={"id": "abc123"})
    )
    await adapter.commit_file(
        REPO,
        "argus/fix-deadbeef",
        "src/app.py",
        "print('fixed')\n",
        "fix: patch sql injection",
    )


@respx.mock
async def test_commit_file_raises_vcs_error_on_400(adapter: GitLabAdapter):
    respx.post(f"{BASE}/projects/{ENCODED_REPO}/repository/commits").mock(
        return_value=httpx.Response(400, json={"message": "A file with this name doesn't exist"})
    )
    with pytest.raises(VCSError) as exc_info:
        await adapter.commit_file(REPO, "branch", "src/app.py", "x", "msg")
    assert exc_info.value.status_code == 400


# ── create_pr (merge request) ─────────────────────────────────────────────────

@respx.mock
async def test_create_pr_returns_web_url(adapter: GitLabAdapter):
    respx.post(f"{BASE}/projects/{ENCODED_REPO}/merge_requests").mock(
        return_value=httpx.Response(
            201,
            json={"web_url": "https://gitlab.com/acme/myrepo/-/merge_requests/7"},
        )
    )
    url = await adapter.create_pr(
        REPO,
        "argus/fix-deadbeef",
        "main",
        "fix: sql injection in login",
        "Automated fix generated by Argus.",
    )
    assert url == "https://gitlab.com/acme/myrepo/-/merge_requests/7"


@respx.mock
async def test_create_pr_raises_vcs_error_on_409(adapter: GitLabAdapter):
    respx.post(f"{BASE}/projects/{ENCODED_REPO}/merge_requests").mock(
        return_value=httpx.Response(409, json={"message": "Another open merge request already exists"})
    )
    with pytest.raises(VCSError) as exc_info:
        await adapter.create_pr(REPO, "head", "main", "title", "body")
    assert exc_info.value.status_code == 409


# ── get_file_content ─────────────────────────────────────────────────────────

@respx.mock
async def test_get_file_content_returns_decoded_string(adapter: GitLabAdapter):
    raw = "def vulnerable(): pass\n"
    encoded = base64.b64encode(raw.encode()).decode()
    encoded_path = urllib.parse.quote("src/app.py", safe="")
    respx.get(
        f"{BASE}/projects/{ENCODED_REPO}/repository/files/{encoded_path}"
    ).mock(
        return_value=httpx.Response(200, json={"content": encoded, "encoding": "base64"})
    )
    content = await adapter.get_file_content(REPO, "src/app.py", ref="main")
    assert content == raw


@respx.mock
async def test_get_file_content_raises_vcs_error_on_404(adapter: GitLabAdapter):
    encoded_path = urllib.parse.quote("missing.py", safe="")
    respx.get(
        f"{BASE}/projects/{ENCODED_REPO}/repository/files/{encoded_path}"
    ).mock(return_value=httpx.Response(404, json={"message": "404 File Not Found"}))
    with pytest.raises(VCSError) as exc_info:
        await adapter.get_file_content(REPO, "missing.py")
    assert exc_info.value.status_code == 404


# ── auth header ──────────────────────────────────────────────────────────────

@respx.mock
async def test_adapter_sends_bearer_token(adapter: GitLabAdapter):
    route = respx.post(
        f"{BASE}/projects/{ENCODED_REPO}/repository/branches"
    ).mock(return_value=httpx.Response(201, json={"name": "argus/fix-x"}))
    await adapter.create_branch(REPO, "argus/fix-x", "main")
    assert route.calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"


# ── self-hosted base URL ──────────────────────────────────────────────────────

@respx.mock
async def test_self_hosted_base_url_is_used():
    adapter = GitLabAdapter(token="tok", base_url="https://gitlab.myco.com/api/v4")
    route = respx.post(
        f"https://gitlab.myco.com/api/v4/projects/{ENCODED_REPO}/repository/branches"
    ).mock(return_value=httpx.Response(201, json={"name": "argus/fix-x"}))
    await adapter.create_branch(REPO, "argus/fix-x", "main")
    assert route.called
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/test_gitlab.py -v 2>&1 | head -20
```

Expected: errors such as `AttributeError: 'GitLabAdapter' object has no attribute 'create_branch'`

- [ ] **Step 3: Implement `core/vcs/gitlab.py`**

```python
from __future__ import annotations
import base64
import urllib.parse
import httpx
from core.vcs.protocol import VCSError


class GitLabAdapter:
    """VCSProvider implementation that calls GitLab REST API v4 via raw httpx.

    Supports both gitlab.com and self-hosted instances — pass the full
    base_url including '/api/v4', e.g. 'https://gitlab.myco.com/api/v4'.
    """

    def __init__(self, token: str, base_url: str) -> None:
        self._token = token
        self._base_url = base_url

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _project_id(self, repo: str) -> str:
        """URL-encode 'owner/repo' for use in path segments."""
        return urllib.parse.quote(repo, safe="")

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            try:
                data = response.json()
                msg = data.get("message") or data.get("error") or response.text
            except Exception:
                msg = response.text
            raise VCSError(msg, response.status_code)

    async def create_branch(
        self, repo: str, branch: str, from_branch: str
    ) -> None:
        pid = self._project_id(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/projects/{pid}/repository/branches",
                headers=self._headers(),
                json={"branch": branch, "ref": from_branch},
            )
            self._raise_for_status(resp)

    async def commit_file(
        self,
        repo: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> None:
        pid = self._project_id(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/projects/{pid}/repository/commits",
                headers=self._headers(),
                json={
                    "branch": branch,
                    "commit_message": message,
                    "actions": [
                        {
                            "action": "update",
                            "file_path": path,
                            "content": content,
                        }
                    ],
                },
            )
            self._raise_for_status(resp)

    async def create_pr(
        self,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> str:
        pid = self._project_id(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/projects/{pid}/merge_requests",
                headers=self._headers(),
                json={
                    "source_branch": head,
                    "target_branch": base,
                    "title": title,
                    "description": body,
                },
            )
            self._raise_for_status(resp)
            return resp.json()["web_url"]

    async def get_file_content(
        self, repo: str, path: str, ref: str = "main"
    ) -> str:
        pid = self._project_id(repo)
        encoded_path = urllib.parse.quote(path, safe="")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/projects/{pid}/repository/files/{encoded_path}",
                headers=self._headers(),
                params={"ref": ref},
            )
            self._raise_for_status(resp)
            data = resp.json()
            return base64.b64decode(data["content"]).decode()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/test_gitlab.py -v
```

Expected:
```
tests/core/vcs/test_gitlab.py::test_create_branch_success PASSED
tests/core/vcs/test_gitlab.py::test_create_branch_raises_vcs_error_on_400 PASSED
tests/core/vcs/test_gitlab.py::test_commit_file_success PASSED
tests/core/vcs/test_gitlab.py::test_commit_file_raises_vcs_error_on_400 PASSED
tests/core/vcs/test_gitlab.py::test_create_pr_returns_web_url PASSED
tests/core/vcs/test_gitlab.py::test_create_pr_raises_vcs_error_on_409 PASSED
tests/core/vcs/test_gitlab.py::test_get_file_content_returns_decoded_string PASSED
tests/core/vcs/test_gitlab.py::test_get_file_content_raises_vcs_error_on_404 PASSED
tests/core/vcs/test_gitlab.py::test_adapter_sends_bearer_token PASSED
tests/core/vcs/test_gitlab.py::test_self_hosted_base_url_is_used PASSED
10 passed
```

- [ ] **Step 5: Run all VCS tests together**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/ -v
```

Expected: 27 passed (7 factory + 10 github + 10 gitlab).

- [ ] **Step 6: Commit**

```bash
git add core/vcs/gitlab.py tests/core/vcs/test_gitlab.py
git commit -m "feat(vcs): implement GitLabAdapter with httpx, full test coverage"
```

---

### Task 4: TargetAuthorization CRUD API

**Files:**
- Create: `core/api/routers/authorizations.py`
- Modify: `core/api/app.py` — import and register authorizations router
- Create: `tests/core/api/test_authorizations.py`

**Interfaces:**
- Consumes:
  - `TargetAuthorizationRow` from `core/db/tables.py`
  - `TargetAuthorization` from `core/model/entities.py`
  - `get_db` from `core/api/deps.py`
- Produces:
  - `POST /api/v1/authorizations` → `{"id": str, "target": str, ...}`
  - `GET /api/v1/authorizations` → list of non-expired authorization dicts
  - `DELETE /api/v1/authorizations/{id}` → 204

- [ ] **Step 1: Write the failing authorization router tests**

Create `tests/core/api/test_authorizations.py`:

```python
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def client():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── POST /api/v1/authorizations ───────────────────────────────────────────────

async def test_create_authorization_returns_201(client):
    with patch("core.api.routers.authorizations.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)
        session.add = MagicMock()
        session.flush = AsyncMock()

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.post(
            "/api/v1/authorizations",
            json={
                "target": "github.com/acme/myrepo@main",
                "owner_confirmed": True,
                "environment": "non-production",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["target"] == "github.com/acme/myrepo@main"
    assert "id" in body


async def test_create_authorization_rejects_without_owner_confirmed(client):
    with patch("core.api.routers.authorizations.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.post(
            "/api/v1/authorizations",
            json={
                "target": "github.com/acme/myrepo@main",
                "owner_confirmed": False,
            },
        )
    assert resp.status_code == 422


# ── GET /api/v1/authorizations ────────────────────────────────────────────────

async def test_list_authorizations_returns_200(client):
    from unittest.mock import patch, AsyncMock, MagicMock
    from datetime import datetime, timezone, timedelta

    row = MagicMock()
    row.id = "550e8400-e29b-41d4-a716-446655440000"
    row.target = "github.com/acme/myrepo@main"
    row.scope_rules = {}
    row.owner_confirmed = True
    row.environment = "non-production"
    row.rate_limits = {}
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    with patch("core.api.routers.authorizations.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [row]
        session.execute = AsyncMock(return_value=result_mock)

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.get("/api/v1/authorizations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── DELETE /api/v1/authorizations/{id} ───────────────────────────────────────

async def test_delete_authorization_returns_204(client):
    from unittest.mock import patch, AsyncMock, MagicMock

    row = MagicMock()
    row.id = "550e8400-e29b-41d4-a716-446655440000"

    with patch("core.api.routers.authorizations.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = row
        session.execute = AsyncMock(return_value=result_mock)
        session.delete = AsyncMock()

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.delete(
            "/api/v1/authorizations/550e8400-e29b-41d4-a716-446655440000"
        )
    assert resp.status_code == 204


async def test_delete_authorization_returns_404_when_missing(client):
    with patch("core.api.routers.authorizations.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.delete(
            "/api/v1/authorizations/550e8400-e29b-41d4-a716-446655440001"
        )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/api/test_authorizations.py -v 2>&1 | head -20
```

Expected: `404` on route not found, or import errors from missing router module.

- [ ] **Step 3: Create `core/api/routers/authorizations.py`**

```python
# core/api/routers/authorizations.py
from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import TargetAuthorizationRow

router = APIRouter(prefix="/authorizations", tags=["authorizations"])


class CreateAuthorizationRequest(BaseModel):
    target: str
    owner_confirmed: bool
    environment: str = "non-production"
    scope_rules: dict = {}
    rate_limits: dict = {}
    expires_at: Optional[datetime] = None

    @field_validator("owner_confirmed")
    @classmethod
    def must_be_confirmed(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "owner_confirmed must be True — explicit confirmation required "
                "before authorizing any VCS write operations against a target"
            )
        return v


@router.post("/", status_code=201)
async def create_authorization(
    body: CreateAuthorizationRequest,
    db: AsyncSession = Depends(get_db),
):
    row = TargetAuthorizationRow(
        id=str(uuid4()),
        target=body.target,
        scope_rules=body.scope_rules,
        owner_confirmed=body.owner_confirmed,
        environment=body.environment,
        rate_limits=body.rate_limits,
        expires_at=body.expires_at,
    )
    db.add(row)
    await db.flush()
    return {
        "id": row.id,
        "target": row.target,
        "owner_confirmed": row.owner_confirmed,
        "environment": row.environment,
        "expires_at": row.expires_at,
    }


@router.get("/")
async def list_authorizations(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    q = select(TargetAuthorizationRow).where(
        (TargetAuthorizationRow.expires_at == None)  # noqa: E711
        | (TargetAuthorizationRow.expires_at > now)
    )
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "target": r.target,
            "owner_confirmed": r.owner_confirmed,
            "environment": r.environment,
            "expires_at": r.expires_at,
        }
        for r in rows
    ]


@router.delete("/{auth_id}", status_code=204)
async def revoke_authorization(
    auth_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TargetAuthorizationRow).where(
            TargetAuthorizationRow.id == str(auth_id)
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Authorization not found")
    await db.delete(row)
```

- [ ] **Step 4: Register router in `core/api/app.py`**

Open `/Users/rajat.a.ahuja/Dev/Argus/core/api/app.py` and add the import and registration. The file currently ends at line 53. Add after the existing router imports:

```python
# core/api/app.py
from __future__ import annotations
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.routers.authorizations import router as authorizations_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus
    app = FastAPI(title="Argus Security Platform", version="0.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")
    app.include_router(authorizations_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    # Stub routes for Phase 2+ (return 501)
    @app.get("/api/v1/pipelines")
    async def list_pipelines():
        return []

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    @app.get("/api/v1/fixes/{fix_id}")
    async def get_fix(fix_id: UUID):
        from fastapi import HTTPException
        raise HTTPException(501, "Fix generation available in Phase 2")

    return app

# Module-level instance for uvicorn
app = create_app()
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/api/test_authorizations.py -v
```

Expected:
```
tests/core/api/test_authorizations.py::test_create_authorization_returns_201 PASSED
tests/core/api/test_authorizations.py::test_create_authorization_rejects_without_owner_confirmed PASSED
tests/core/api/test_authorizations.py::test_list_authorizations_returns_200 PASSED
tests/core/api/test_authorizations.py::test_delete_authorization_returns_204 PASSED
tests/core/api/test_authorizations.py::test_delete_authorization_returns_404_when_missing PASSED
5 passed
```

- [ ] **Step 6: Confirm existing tests still pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/api/ -v
```

Expected: all tests pass (no regressions).

- [ ] **Step 7: Commit**

```bash
git add core/api/routers/authorizations.py core/api/app.py \
        tests/core/api/test_authorizations.py
git commit -m "feat(api): add TargetAuthorization CRUD endpoints"
```

---

### Task 5: Fix-apply endpoint with PR creation

**Files:**
- Create: `core/api/routers/fixes.py`
- Modify: `core/api/app.py` — register fixes router, remove the old stub `GET /api/v1/fixes/{fix_id}`
- Create: `tests/core/api/test_fixes.py`

**Interfaces:**
- Consumes:
  - `FixRow`, `FindingRow`, `ScanRow`, `TargetAuthorizationRow`, `AuditLogEntryRow` from `core/db/tables.py`
  - `get_vcs_provider(target_ref, token) -> VCSProvider` from `core/vcs/factory.py`
  - `VCSError`, `VCSNotSupported` from `core/vcs/protocol.py`
  - `get_db` from `core/api/deps.py`
- Produces:
  - `POST /api/v1/fixes/{id}/apply` with body `ApplyFixRequest`
  - On `create_pr=False`: status `"applied"`, AuditLogEntry action `"fix_applied_local"`
  - On `create_pr=True`: status `"pr_opened"`, `validation_result["pr_url"]` set, AuditLogEntry action `"fix_pr_created"`

- [ ] **Step 1: Write the failing fix-apply tests**

Create `tests/core/api/test_fixes.py`:

```python
from __future__ import annotations
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession


FIX_ID = str(uuid.uuid4())
FINDING_ID = str(uuid.uuid4())
SCAN_ID = str(uuid.uuid4())
AUTH_ID = str(uuid.uuid4())


def _make_fix_row(fix_id: str = FIX_ID, status: str = "proposed") -> MagicMock:
    row = MagicMock()
    row.id = fix_id
    row.finding_id = FINDING_ID
    row.diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-vulnerable()\n"
        "+safe()\n"
    )
    row.test = None
    row.explanation = "Replaces vulnerable call with safe equivalent"
    row.status = status
    row.validation_result = None
    return row


def _make_finding_row() -> MagicMock:
    row = MagicMock()
    row.id = FINDING_ID
    row.scan_id = SCAN_ID
    row.rule_id = "sqli-001"
    row.location = {"file": "src/app.py", "line_start": 1, "line_end": 1}
    return row


def _make_scan_row() -> MagicMock:
    row = MagicMock()
    row.id = SCAN_ID
    row.target_ref = "github.com/acme/myrepo@main"
    return row


def _make_auth_row() -> MagicMock:
    from datetime import datetime, timezone, timedelta
    row = MagicMock()
    row.id = AUTH_ID
    row.target = "github.com/acme/myrepo@main"
    row.owner_confirmed = True
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    return row


@pytest.fixture
async def client():
    from core.api.app import create_app
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── local apply (create_pr=False) ─────────────────────────────────────────────

async def test_apply_local_sets_status_applied(client):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()

    with (
        patch("core.api.routers.fixes.get_db") as mock_get_db,
        patch("core.api.routers.fixes.subprocess.run") as mock_run,
    ):
        session = AsyncMock(spec=AsyncSession)

        def _execute_side_effect(stmt, *args, **kwargs):
            result = MagicMock()
            # Return fix row for first execute, finding row for second
            result.scalar_one_or_none.side_effect = [fix_row, finding_row]
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.post(
            f"/api/v1/fixes/{FIX_ID}/apply",
            json={"create_pr": False},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert fix_row.status == "applied"


async def test_apply_local_returns_404_when_fix_missing(client):
    with patch("core.api.routers.fixes.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.post(
            f"/api/v1/fixes/{FIX_ID}/apply",
            json={"create_pr": False},
        )
    assert resp.status_code == 404


async def test_apply_local_writes_audit_log_entry(client):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    added_rows = []

    with (
        patch("core.api.routers.fixes.get_db") as mock_get_db,
        patch("core.api.routers.fixes.subprocess.run") as mock_run,
    ):
        session = AsyncMock(spec=AsyncSession)
        call_count = [0]

        def _execute_side_effect(stmt, *args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = fix_row
            else:
                result.scalar_one_or_none.return_value = finding_row
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)
        session.add = MagicMock(side_effect=added_rows.append)
        session.flush = AsyncMock()
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        await client.post(f"/api/v1/fixes/{FIX_ID}/apply", json={"create_pr": False})

    from core.db.tables import AuditLogEntryRow
    audit_rows = [r for r in added_rows if isinstance(r, AuditLogEntryRow)]
    assert len(audit_rows) == 1
    assert audit_rows[0].action == "fix_applied_local"
    assert audit_rows[0].actor == "api"


# ── PR creation (create_pr=True) ──────────────────────────────────────────────

async def test_apply_pr_sets_status_pr_opened(client):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    scan_row = _make_scan_row()
    auth_row = _make_auth_row()

    mock_provider = AsyncMock()
    mock_provider.create_branch = AsyncMock()
    mock_provider.commit_file = AsyncMock()
    mock_provider.get_file_content = AsyncMock(return_value="vulnerable()\n")
    mock_provider.create_pr = AsyncMock(
        return_value="https://github.com/acme/myrepo/pull/42"
    )

    with (
        patch("core.api.routers.fixes.get_db") as mock_get_db,
        patch("core.api.routers.fixes.get_vcs_provider", return_value=mock_provider),
    ):
        session = AsyncMock(spec=AsyncSession)
        call_count = [0]

        def _execute_side_effect(stmt, *args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = fix_row
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = finding_row
            elif call_count[0] == 3:
                result.scalar_one_or_none.return_value = scan_row
            else:
                result.scalar_one_or_none.return_value = auth_row
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.post(
            f"/api/v1/fixes/{FIX_ID}/apply",
            json={
                "create_pr": True,
                "vcs_token": "ghp_test",
                "pr_base_branch": "main",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pr_opened"
    assert body["pr_url"] == "https://github.com/acme/myrepo/pull/42"
    assert fix_row.status == "pr_opened"


async def test_apply_pr_returns_403_when_no_authorization(client):
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    scan_row = _make_scan_row()

    with patch("core.api.routers.fixes.get_db") as mock_get_db:
        session = AsyncMock(spec=AsyncSession)
        call_count = [0]

        def _execute_side_effect(stmt, *args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = fix_row
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = finding_row
            elif call_count[0] == 3:
                result.scalar_one_or_none.return_value = scan_row
            else:
                result.scalar_one_or_none.return_value = None  # no authorization
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        resp = await client.post(
            f"/api/v1/fixes/{FIX_ID}/apply",
            json={"create_pr": True, "vcs_token": "ghp_test"},
        )

    assert resp.status_code == 403


async def test_apply_pr_requires_vcs_token(client):
    """create_pr=True without a vcs_token should return 422."""
    resp = await client.post(
        f"/api/v1/fixes/{FIX_ID}/apply",
        json={"create_pr": True},
    )
    assert resp.status_code == 422


async def test_apply_pr_writes_three_audit_log_entries(client):
    """branch_create + commit + pr_opened each write an audit entry."""
    fix_row = _make_fix_row()
    finding_row = _make_finding_row()
    scan_row = _make_scan_row()
    auth_row = _make_auth_row()
    added_rows = []

    mock_provider = AsyncMock()
    mock_provider.create_branch = AsyncMock()
    mock_provider.commit_file = AsyncMock()
    mock_provider.get_file_content = AsyncMock(return_value="vulnerable()\n")
    mock_provider.create_pr = AsyncMock(
        return_value="https://github.com/acme/myrepo/pull/42"
    )

    with (
        patch("core.api.routers.fixes.get_db") as mock_get_db,
        patch("core.api.routers.fixes.get_vcs_provider", return_value=mock_provider),
    ):
        session = AsyncMock(spec=AsyncSession)
        call_count = [0]

        def _execute_side_effect(stmt, *args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = fix_row
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = finding_row
            elif call_count[0] == 3:
                result.scalar_one_or_none.return_value = scan_row
            else:
                result.scalar_one_or_none.return_value = auth_row
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)
        session.add = MagicMock(side_effect=added_rows.append)
        session.flush = AsyncMock()

        async def _fake_db():
            yield session

        mock_get_db.return_value = _fake_db()

        await client.post(
            f"/api/v1/fixes/{FIX_ID}/apply",
            json={"create_pr": True, "vcs_token": "ghp_test", "pr_base_branch": "main"},
        )

    from core.db.tables import AuditLogEntryRow
    audit_rows = [r for r in added_rows if isinstance(r, AuditLogEntryRow)]
    actions = {r.action for r in audit_rows}
    assert "vcs_branch_created" in actions
    assert "vcs_file_committed" in actions
    assert "fix_pr_created" in actions
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/api/test_fixes.py -v 2>&1 | head -30
```

Expected: `404 Not Found` for all apply tests (route doesn't exist yet).

- [ ] **Step 3: Create `core/api/routers/fixes.py`**

```python
# core/api/routers/fixes.py
from __future__ import annotations
import subprocess
import tempfile
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.api.deps import get_db
from core.db.tables import FixRow, FindingRow, ScanRow, TargetAuthorizationRow, AuditLogEntryRow
from core.vcs.factory import get_vcs_provider
from core.vcs.protocol import VCSError, VCSNotSupported

router = APIRouter(prefix="/fixes", tags=["fixes"])


class ApplyFixRequest(BaseModel):
    create_pr: bool = False
    vcs_token: Optional[str] = None
    pr_base_branch: str = "main"
    pr_title: Optional[str] = None

    @model_validator(mode="after")
    def vcs_token_required_when_create_pr(self) -> "ApplyFixRequest":
        if self.create_pr and not self.vcs_token:
            raise ValueError("vcs_token is required when create_pr=True")
        return self


def _write_audit(
    db: AsyncSession,
    actor: str,
    action: str,
    target: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> AuditLogEntryRow:
    entry = AuditLogEntryRow(
        id=str(uuid4()),
        actor=actor,
        action=action,
        target=target,
        before=before,
        after=after,
    )
    db.add(entry)
    return entry


@router.post("/{fix_id}/apply")
async def apply_fix(
    fix_id: UUID,
    body: ApplyFixRequest,
    db: AsyncSession = Depends(get_db),
):
    # ── Load fix ──────────────────────────────────────────────────────────────
    result = await db.execute(
        select(FixRow).where(FixRow.id == str(fix_id))
    )
    fix_row = result.scalar_one_or_none()
    if not fix_row:
        raise HTTPException(status_code=404, detail="Fix not found")

    # ── Load finding (needed for file path + rule_id) ─────────────────────────
    result = await db.execute(
        select(FindingRow).where(FindingRow.id == fix_row.finding_id)
    )
    finding_row = result.scalar_one_or_none()
    if not finding_row:
        raise HTTPException(status_code=404, detail="Finding not found for fix")

    # ── Local apply ───────────────────────────────────────────────────────────
    if not body.create_pr:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False
        ) as f:
            f.write(fix_row.diff)
            patch_path = f.name
        try:
            proc = subprocess.run(
                ["patch", "-p1", "--input", patch_path],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"patch failed: {proc.stderr}",
                )
        finally:
            os.unlink(patch_path)

        fix_row.status = "applied"
        _write_audit(
            db,
            actor="api",
            action="fix_applied_local",
            target=str(fix_id),
            before={"status": "proposed"},
            after={"status": "applied"},
        )
        await db.flush()
        return {"fix_id": str(fix_id), "status": "applied"}

    # ── PR creation path ──────────────────────────────────────────────────────
    # Load scan to get target_ref
    result = await db.execute(
        select(ScanRow).where(ScanRow.id == finding_row.scan_id)
    )
    scan_row = result.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found for finding")

    target_ref: str = scan_row.target_ref

    # Check TargetAuthorization (owner_confirmed + non-expired)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TargetAuthorizationRow).where(
            TargetAuthorizationRow.target == target_ref,
            TargetAuthorizationRow.owner_confirmed == True,  # noqa: E712
            (TargetAuthorizationRow.expires_at == None)  # noqa: E711
            | (TargetAuthorizationRow.expires_at > now),
        )
    )
    auth_row = result.scalar_one_or_none()
    if not auth_row:
        raise HTTPException(
            status_code=403,
            detail=(
                f"No active TargetAuthorization found for '{target_ref}'. "
                "Create one via POST /api/v1/authorizations before applying VCS fixes."
            ),
        )

    # Derive repo identifier from target_ref (strip host and @branch)
    # github.com/org/repo@main  →  "org/repo"
    after_host = target_ref.split("/", 1)[1]  # "org/repo@main"
    repo = after_host.split("@")[0]           # "org/repo"

    branch_name = f"argus/fix-{str(fix_id)[:8]}"
    base_branch = body.pr_base_branch
    file_path: str = finding_row.location["file"]
    rule_id: str = finding_row.rule_id

    pr_title = body.pr_title or f"fix: {rule_id} in {file_path}"
    pr_body = (
        f"Automated fix generated by Argus.\n\n"
        f"**Rule:** {rule_id}  \n"
        f"**File:** {file_path}  \n\n"
        f"```diff\n{fix_row.diff}\n```"
    )

    provider = get_vcs_provider(target_ref, token=body.vcs_token)

    # 1. Create branch
    await provider.create_branch(repo, branch_name, base_branch)
    _write_audit(
        db,
        actor="api",
        action="vcs_branch_created",
        target=f"{repo}:{branch_name}",
    )

    # 2. Commit patched file — apply diff in memory then write result
    current_content = await provider.get_file_content(repo, file_path, ref=base_branch)
    patched_content = _apply_diff_in_memory(current_content, fix_row.diff)
    await provider.commit_file(
        repo,
        branch_name,
        file_path,
        patched_content,
        pr_title,
    )
    _write_audit(
        db,
        actor="api",
        action="vcs_file_committed",
        target=f"{repo}:{branch_name}:{file_path}",
    )

    # 3. Open PR
    pr_url = await provider.create_pr(
        repo, branch_name, base_branch, pr_title, pr_body
    )

    # 4. Persist
    fix_row.status = "pr_opened"
    fix_row.validation_result = {
        **(fix_row.validation_result or {}),
        "pr_url": pr_url,
    }
    _write_audit(
        db,
        actor="api",
        action="fix_pr_created",
        target=pr_url,
        after={"pr_url": pr_url, "branch": branch_name},
    )
    await db.flush()

    return {"fix_id": str(fix_id), "status": "pr_opened", "pr_url": pr_url}


def _apply_diff_in_memory(original: str, diff: str) -> str:
    """Apply a unified diff to original content using subprocess patch.

    Writes to temp files, runs patch -p0, returns patched content.
    Raises HTTPException(422) if patch fails.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = os.path.join(tmpdir, "original")
        patch_path = os.path.join(tmpdir, "changes.patch")

        with open(orig_path, "w") as f:
            f.write(original)

        # Rewrite diff paths to point at our temp file (strip a/ b/ prefixes)
        lines = []
        for line in diff.splitlines(keepends=True):
            if line.startswith("--- a/"):
                lines.append(f"--- {orig_path}\n")
            elif line.startswith("+++ b/"):
                lines.append(f"+++ {orig_path}\n")
            else:
                lines.append(line)
        with open(patch_path, "w") as f:
            f.writelines(lines)

        proc = subprocess.run(
            ["patch", "--no-backup-if-mismatch", orig_path, patch_path],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to apply diff in memory: {proc.stderr}",
            )

        with open(orig_path) as f:
            return f.read()
```

- [ ] **Step 4: Register fixes router in `core/api/app.py` and remove old stub**

Replace the full content of `/Users/rajat.a.ahuja/Dev/Argus/core/api/app.py` with:

```python
# core/api/app.py
from __future__ import annotations
from uuid import UUID
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.api.routers.scans import router as scans_router
from core.api.routers.findings import router as findings_router
from core.api.routers.cost import router as cost_router
from core.api.routers.authorizations import router as authorizations_router
from core.api.routers.fixes import router as fixes_router
from core.api.sse import scan_event_stream
from core.governance.events import ScanEventBus, event_bus as _default_bus


def create_app(event_bus: ScanEventBus | None = None) -> FastAPI:
    bus = event_bus or _default_bus
    app = FastAPI(title="Argus Security Platform", version="0.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router, prefix="/api/v1")
    app.include_router(findings_router, prefix="/api/v1")
    app.include_router(cost_router, prefix="/api/v1")
    app.include_router(authorizations_router, prefix="/api/v1")
    app.include_router(fixes_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/scans/{scan_id}/events")
    async def scan_events(scan_id: UUID):
        return scan_event_stream(scan_id, bus)

    @app.get("/api/v1/pipelines")
    async def list_pipelines():
        return []

    @app.get("/api/v1/skills")
    async def list_skills():
        return []

    return app


# Module-level instance for uvicorn
app = create_app()
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/api/test_fixes.py -v
```

Expected:
```
tests/core/api/test_fixes.py::test_apply_local_sets_status_applied PASSED
tests/core/api/test_fixes.py::test_apply_local_returns_404_when_fix_missing PASSED
tests/core/api/test_fixes.py::test_apply_local_writes_audit_log_entry PASSED
tests/core/api/test_fixes.py::test_apply_pr_sets_status_pr_opened PASSED
tests/core/api/test_fixes.py::test_apply_pr_returns_403_when_no_authorization PASSED
tests/core/api/test_fixes.py::test_apply_pr_requires_vcs_token PASSED
tests/core/api/test_fixes.py::test_apply_pr_writes_three_audit_log_entries PASSED
7 passed
```

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/ -v --ignore=tests/e2e 2>&1 | tail -20
```

Expected: all tests pass (no regressions from removing the `/api/v1/fixes/{fix_id}` stub).

- [ ] **Step 7: Commit**

```bash
git add core/api/routers/fixes.py core/api/app.py tests/core/api/test_fixes.py
git commit -m "feat(api): wire PR creation into POST /fixes/{id}/apply with authorization gate"
```

---

### Task 6: Add `respx` to pyproject.toml dev dependencies

**Files:**
- Modify: `pyproject.toml` — add `respx>=0.21.0` to `[project.optional-dependencies] dev`

This is a bookkeeping step — `respx` was installed in Task 2 Step 1 but must be declared in the project manifest so future `uv sync --dev` installs pick it up.

- [ ] **Step 1: Verify respx is importable**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -c "import respx; print(respx.__version__)"
```

Expected: prints a version string like `0.21.1`

- [ ] **Step 2: Check if respx is already in pyproject.toml**

```bash
grep respx /Users/rajat.a.ahuja/Dev/Argus/pyproject.toml
```

If output is empty, proceed to Step 3. If it already appears, skip to Step 4.

- [ ] **Step 3: Add respx to pyproject.toml dev dependencies**

Open `/Users/rajat.a.ahuja/Dev/Argus/pyproject.toml`. In the `[project.optional-dependencies]` section, add `"respx>=0.21.0",` after the existing `pytest-httpx` line so the section reads:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.30.0",
    "respx>=0.21.0",
    "httpx>=0.27.0",
    "factory-boy>=3.3.0",
]
```

- [ ] **Step 4: Run all VCS tests one final time**

```bash
cd /Users/rajat.a.ahuja/Dev/Argus && python -m pytest tests/core/vcs/ tests/core/api/test_fixes.py tests/core/api/test_authorizations.py -v
```

Expected: all 39 tests pass (27 VCS + 7 fixes + 5 authorizations).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "chore: declare respx dev dependency in pyproject.toml"
```
