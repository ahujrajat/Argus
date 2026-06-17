# core/understanding/ingest.py
from __future__ import annotations
from pathlib import Path
import os
from core.understanding.context import CodeContext

_LANG_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".tf": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".dockerfile": "dockerfile",
}

_FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "django": ["django", "manage.py"],
    "flask": ["flask", "Flask"],
    "express": ["express"],
    "spring": ["springframework"],
    "react": ["react", "ReactDOM"],
    "fastapi": ["fastapi", "FastAPI"],
}

_ENTRY_POINT_NAMES = {"main.py", "app.py", "server.py", "index.py", "manage.py", "wsgi.py", "asgi.py"}


def build_code_context(root: str, max_files: int = 500) -> CodeContext:
    root_path = Path(root).resolve()
    lang_counts: dict[str, int] = {}
    files: list[Path] = []
    total_bytes = 0

    for fp in root_path.rglob("*"):
        if fp.is_file() and not _is_ignored(fp):
            ext = fp.suffix.lower()
            lang = _LANG_EXTENSIONS.get(ext)
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
            files.append(fp)
            total_bytes += fp.stat().st_size
            if len(files) >= max_files:
                break

    frameworks = _detect_frameworks(root_path, files)
    repo_map = _build_repo_map(root_path, files)
    entry_points = [
        str(f.relative_to(root_path))
        for f in files
        if f.name in _ENTRY_POINT_NAMES
    ]

    return CodeContext(
        root=str(root_path),
        languages=lang_counts,
        frameworks=frameworks,
        file_count=len(files),
        repo_map=repo_map,
        entry_points=entry_points,
        size_bytes=total_bytes,
    )


def _is_ignored(fp: Path) -> bool:
    ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".pytest_cache"}
    return any(part in ignored_dirs for part in fp.parts)


def _detect_frameworks(root: Path, files: list[Path]) -> list[str]:
    detected = []
    all_text = ""
    for fp in files[:50]:
        try:
            all_text += fp.read_text(errors="ignore")[:2000]
        except OSError:
            pass
    for framework, signals in _FRAMEWORK_SIGNALS.items():
        if any(s in all_text for s in signals):
            detected.append(framework)
    req_files = list(root.glob("*requirements*.txt")) + list(root.glob("package.json"))
    for rf in req_files:
        try:
            content = rf.read_text(errors="ignore")
            for framework, signals in _FRAMEWORK_SIGNALS.items():
                if framework not in detected and any(s.lower() in content.lower() for s in signals):
                    detected.append(framework)
        except OSError:
            pass
    return detected


def _build_repo_map(root: Path, files: list[Path]) -> str:
    lines = []
    for fp in sorted(files):
        rel = fp.relative_to(root)
        lines.append(str(rel))
    return "\n".join(lines)
