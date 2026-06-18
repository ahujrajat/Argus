from __future__ import annotations
import pytest
from core.vcs.factory import get_vcs_provider
from core.vcs.github import GitHubAdapter
from core.vcs.gitlab import GitLabAdapter
from core.vcs.protocol import VCSNotSupported


def test_github_target_returns_github_adapter():
    provider = get_vcs_provider("github.com/acme/myrepo@main", token="ghp_test")
    assert isinstance(provider, GitHubAdapter)


def test_gitlab_com_target_returns_gitlab_adapter():
    provider = get_vcs_provider("gitlab.com/acme/myrepo@main", token="glpat_test")
    assert isinstance(provider, GitLabAdapter)


def test_gitlab_selfhosted_target_returns_gitlab_adapter():
    provider = get_vcs_provider(
        "gitlab.mycompany.com/team/svc@develop", token="tok"
    )
    assert isinstance(provider, GitLabAdapter)


def test_local_path_raises_vcs_not_supported():
    with pytest.raises(VCSNotSupported, match="local paths"):
        get_vcs_provider("/home/user/myrepo@main", token="irrelevant")


def test_unknown_host_raises_vcs_not_supported():
    with pytest.raises(VCSNotSupported):
        get_vcs_provider("bitbucket.org/acme/myrepo@main", token="tok")


def test_github_adapter_carries_correct_token():
    provider = get_vcs_provider("github.com/acme/myrepo@main", token="ghp_secret")
    assert provider._token == "ghp_secret"


def test_gitlab_adapter_carries_correct_base_url():
    provider = get_vcs_provider("gitlab.mycompany.com/team/svc@develop", token="tok")
    assert provider._base_url == "https://gitlab.mycompany.com/api/v4"
