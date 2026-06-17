"""
Root conftest — sets environment variables needed for scanner adapters.
"""
from __future__ import annotations
import os
from pathlib import Path

# Allow tests to find semgrep in the virtualenv
_venv_semgrep = Path(__file__).parent.parent / ".venv" / "bin" / "semgrep"
if _venv_semgrep.exists() and not os.environ.get("SEMGREP_BIN"):
    os.environ["SEMGREP_BIN"] = str(_venv_semgrep)
