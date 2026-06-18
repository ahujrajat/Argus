# tests/core/understanding/test_diff.py
from __future__ import annotations
import subprocess
from unittest.mock import patch, MagicMock
from core.understanding.diff import compute_diff_files


def test_returns_absolute_paths_for_changed_files():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "src/app.py\nsrc/utils.py\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        files = compute_diff_files("/repo", "HEAD~1")

    assert len(files) == 2
    assert all(f.endswith(".py") for f in files)
    assert all(f.startswith("/") for f in files)


def test_returns_empty_list_on_git_failure():
    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stdout = ""
    mock_result.stderr = "not a git repository"

    with patch("subprocess.run", return_value=mock_result):
        files = compute_diff_files("/not-a-repo", "HEAD~1")

    assert files == []


def test_returns_empty_list_when_git_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
        files = compute_diff_files("/repo", "HEAD~1")

    assert files == []


def test_filters_blank_lines():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "src/app.py\n\n\nsrc/utils.py\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        files = compute_diff_files("/repo", "HEAD~1")

    assert len(files) == 2
