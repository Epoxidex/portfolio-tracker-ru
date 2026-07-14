"""Fail fast when files that must stay private could be published."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_NAMES = {".env", "portfolio.db"}
PRIVATE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".xlsx", ".xls"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "backups", ".claude", ".agents", ".codex"}
TEXT_SUFFIXES = {".py", ".js", ".css", ".html", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".sh", ".ps1"}
SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.I),
]
REQUIRED_IGNORE_RULES = {".env", ".env.*", "!.env.example", "*.db", "backups/", ".claude/"}


def _tracked_files() -> list[Path] | None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in listed if name]


def _source_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)
        and path.suffix.lower() in TEXT_SUFFIXES
        and path.name != ".env"
    ]


def main() -> int:
    tracked = _tracked_files()
    errors: list[str] = []
    ignore_rules = {
        line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing_rules = REQUIRED_IGNORE_RULES - ignore_rules
    if missing_rules:
        errors.append(".gitignore misses required rules: " + ", ".join(sorted(missing_rules)))
    if tracked is not None:
        for path in tracked:
            relative = path.relative_to(ROOT).as_posix()
            if path.name in PRIVATE_NAMES or path.suffix.lower() in PRIVATE_SUFFIXES:
                errors.append(f"private data is tracked: {relative}")

    for path in _source_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            errors.append(f"possible secret or local user path: {path.relative_to(ROOT).as_posix()}")

    if errors:
        print("Public-repository check failed:")
        for error in sorted(set(errors)):
            print(f"  - {error}")
        return 1
    mode = "tracked files" if tracked is not None else "source files and required ignore rules (Git is not initialized)"
    print(f"Public-repository check passed: {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
