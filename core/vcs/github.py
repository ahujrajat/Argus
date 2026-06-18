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
            resp = await client.get(
                f"{_API_BASE}/repos/{owner}/{name}/git/refs/heads/{from_branch}",
                headers=self._headers(),
            )
            self._raise_for_status(resp)
            sha = resp.json()["object"]["sha"]

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
