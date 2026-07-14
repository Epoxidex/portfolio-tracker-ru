"""Safe, restorable SQLite backups for the local portfolio database."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .config import BASE_DIR, DB_PATH


def _copy_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            result = dst.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"backup integrity check failed: {result}")


def backup_database(output_dir: str | Path | None = None, *, prefix: str = "portfolio") -> Path:
    source = Path(DB_PATH)
    if not source.exists():
        raise FileNotFoundError(f"database does not exist: {source}")
    directory = Path(output_dir) if output_dir else BASE_DIR / "backups"
    if not directory.is_absolute():
        directory = BASE_DIR / directory
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = directory / f"{prefix}-{stamp}.db"
    counter = 1
    while destination.exists():
        destination = directory / f"{prefix}-{stamp}-{counter}.db"
        counter += 1
    _copy_sqlite(source, destination)
    return destination.resolve()


def restore_database(backup_path: str | Path) -> tuple[Path, Path | None]:
    source = Path(backup_path).expanduser().resolve()
    target = Path(DB_PATH).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"backup does not exist: {source}")
    if source == target:
        raise ValueError("backup and active database are the same file")

    # Validate the source before touching the active database.
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as con:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"source integrity check failed: {result}")

    safety_copy = (
        backup_database(target.parent / "backups", prefix="before-restore")
        if target.exists() else None
    )
    temp = target.with_name(f".{target.name}.restore-{os.getpid()}.tmp")
    try:
        if temp.exists():
            temp.unlink()
        _copy_sqlite(source, temp)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return target, safety_copy
