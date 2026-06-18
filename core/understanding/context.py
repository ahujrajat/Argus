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
