from __future__ import annotations
import subprocess
import structlog
from pathlib import Path

log = structlog.get_logger()


def compute_diff_files(repo_path: str, base_ref: str = "HEAD~1") -> list[str]:
    """Return absolute paths of files changed between base_ref and HEAD.

    Falls back to an empty list if the repo_path is not a git repo or base_ref
    cannot be resolved (e.g. initial commit with no parent).
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-only", base_ref, "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.warning(
                "git_diff_failed",
                repo=repo_path,
                base_ref=base_ref,
                stderr=result.stderr.strip(),
            )
            return []
        root = Path(repo_path).resolve()
        return [str(root / p) for p in result.stdout.splitlines() if p.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("git_diff_error", repo=repo_path, error=str(e))
        return []
