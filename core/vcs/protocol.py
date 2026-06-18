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

    async def get_file_content(
        self, repo: str, path: str, ref: str = "main"
    ) -> str: ...
