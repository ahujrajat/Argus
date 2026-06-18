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
