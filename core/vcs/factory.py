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
