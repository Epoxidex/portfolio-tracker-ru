"""Private Git repository backups for the local SQLite database."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .. import config
from ..dataio import (
    DATABASE_MAINTENANCE_LOCK,
    backup_database,
    restore_database,
    validate_backup_database,
)


_BACKUP_NAME = re.compile(r"^portfolio-(\d{8})-(\d{6})(?:-\d+)?\.db$")
_REPOSITORY_LOCK = threading.RLock()

_VAULT_README = """# Portfolio Tracker RU Vault

Приватное хранилище резервных копий SQLite для Portfolio Tracker RU.

Файлы `portfolio-*.db` содержат полный портфель и хранятся без шифрования.
Репозиторий должен всегда оставаться приватным. Не добавляйте сюда `.env`,
токен Т-Инвестиций и другие секреты.

Восстанавливайте данные через раздел «Бэкапы» в интерфейсе приложения.
"""

_VAULT_GITIGNORE = """# Разрешены только документация и SQLite-бэкапы.
*
!.gitignore
!README.md
!portfolio-*.db
"""


class GitBackupError(RuntimeError):
    """A safe, user-facing Git backup error."""


def git_available() -> bool:
    return shutil.which("git") is not None


def _configured_repository() -> str:
    repository = config.BACKUP_GIT_REPOSITORY.strip()
    if not repository:
        raise GitBackupError("Добавьте BACKUP_GIT_REPOSITORY в .env и перезапустите приложение")
    if any(char in repository for char in "\r\n\0"):
        raise GitBackupError("BACKUP_GIT_REPOSITORY содержит недопустимые символы")
    if repository.startswith("-"):
        raise GitBackupError("BACKUP_GIT_REPOSITORY не может начинаться с дефиса")
    if repository.startswith(("http://", "https://")):
        parsed = urlsplit(repository)
        if parsed.username or parsed.password:
            raise GitBackupError("Не храните логин или токен в BACKUP_GIT_REPOSITORY")
    token_file = os.getenv("PORTFOLIO_GITHUB_TOKEN_FILE", "").strip()
    if token_file:
        parsed = urlsplit(repository)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise GitBackupError(
                "Docker secret GitHub поддерживает только HTTPS-адрес github.com без логина"
            )
        secret = Path(token_file)
        if not secret.is_file() or not os.access(secret, os.R_OK):
            raise GitBackupError("Docker secret с GitHub-токеном недоступен контейнеру")
    return repository


def _friendly_git_error(output: str, action: str) -> str:
    text = output.lower()
    if os.getenv("PORTFOLIO_GITHUB_TOKEN_FILE", "").strip() and (
        "authentication failed" in text
        or "could not read username" in text
        or "permission denied" in text
        or "403" in text
    ):
        return (
            "GitHub не принял Docker secret. Проверьте срок токена, доступ к нужному "
            "репозиторию и разрешение Contents"
        )
    if "authentication failed" in text or "could not read username" in text:
        return "GitHub не принял авторизацию. Сначала выполните обычный git push из терминала"
    if "repository not found" in text or "not found" in text:
        return "Приватный репозиторий не найден или у текущего пользователя нет доступа"
    if "dubious ownership" in text:
        return "Git не доверяет владельцу локального каталога бэкапов"
    if "fast-forward" in text or "diverg" in text or "non-fast-forward" in text:
        return "Локальная и удалённая истории бэкапов разошлись; требуется ручная сверка"
    if "permission denied" in text:
        return "Git не получил доступ к приватному репозиторию или локальному каталогу"
    return f"Git не выполнил действие «{action}»"


def _git(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    action: str = "операция",
) -> subprocess.CompletedProcess[str]:
    if not git_available():
        raise GitBackupError("Git не установлен или недоступен в PATH")
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitBackupError(f"Git слишком долго выполнял действие «{action}»") from exc
    except OSError as exc:
        raise GitBackupError("Не удалось запустить Git") from exc
    if check and result.returncode != 0:
        raise GitBackupError(_friendly_git_error(result.stdout + result.stderr, action))
    return result


def _same_remote(actual: str, expected: str) -> bool:
    return actual.rstrip("/\n\r") == expected.rstrip("/\n\r")


def _ref_exists(directory: Path, ref: str) -> bool:
    return _git(
        ["show-ref", "--verify", "--quiet", ref],
        cwd=directory,
        check=False,
    ).returncode == 0


def _sync_checkout() -> Path:
    repository = _configured_repository()
    directory = config.BACKUP_GIT_DIRECTORY
    directory.parent.mkdir(parents=True, exist_ok=True)

    if not (directory / ".git").is_dir():
        if directory.exists():
            if any(directory.iterdir()):
                raise GitBackupError("Локальный каталог Git-бэкапов занят посторонними файлами")
            directory.rmdir()
        _git(
            ["clone", repository, str(directory)],
            action="клонирование приватного репозитория",
        )

    actual_remote = _git(
        ["remote", "get-url", "origin"],
        cwd=directory,
        action="проверка адреса репозитория",
    ).stdout.strip()
    if not _same_remote(actual_remote, repository):
        raise GitBackupError("Локальный vault связан с другим удалённым репозиторием")

    branch = config.BACKUP_GIT_BRANCH
    _git(["fetch", "--prune", "origin"], cwd=directory, action="получение списка бэкапов")
    local_ref = f"refs/heads/{branch}"
    remote_ref = f"refs/remotes/origin/{branch}"
    local_exists = _ref_exists(directory, local_ref)
    remote_exists = _ref_exists(directory, remote_ref)

    if local_exists:
        _git(["checkout", branch], cwd=directory, action="выбор ветки бэкапов")
    elif remote_exists:
        _git(
            ["checkout", "-b", branch, "--track", f"origin/{branch}"],
            cwd=directory,
            action="создание локальной ветки бэкапов",
        )
    else:
        _git(["checkout", "-B", branch], cwd=directory, action="создание ветки бэкапов")

    if remote_exists:
        _git(
            ["pull", "--ff-only", "origin", branch],
            cwd=directory,
            action="обновление списка бэкапов",
        )
    return directory


def _ensure_clean(directory: Path) -> None:
    status = _git(["status", "--porcelain"], cwd=directory, action="проверка vault").stdout
    if status.strip():
        raise GitBackupError("В локальном vault есть незавершённые изменения; требуется ручная проверка")


def _ensure_identity(directory: Path) -> None:
    name = _git(["config", "--get", "user.name"], cwd=directory, check=False).stdout.strip()
    email = _git(["config", "--get", "user.email"], cwd=directory, check=False).stdout.strip()
    if not name:
        _git(["config", "user.name", "Portfolio Tracker"], cwd=directory)
    if not email:
        _git(["config", "user.email", "portfolio-tracker@localhost"], cwd=directory)


def _write_scaffold(directory: Path) -> None:
    readme = directory / "README.md"
    ignore = directory / ".gitignore"
    if not readme.exists():
        readme.write_text(_VAULT_README, encoding="utf-8")
    if not ignore.exists():
        ignore.write_text(_VAULT_GITIGNORE, encoding="utf-8")


def _backup_metadata(path: Path) -> dict:
    match = _BACKUP_NAME.fullmatch(path.name)
    created_at = None
    if match:
        created_at = datetime.strptime("".join(match.groups()[:2]), "%Y%m%d%H%M%S").isoformat()
    return {
        "name": path.name,
        "created_at": created_at,
        "size_bytes": path.stat().st_size,
    }


def _backup_files(directory: Path) -> list[Path]:
    return sorted(
        [path for path in directory.glob("portfolio-*.db") if _BACKUP_NAME.fullmatch(path.name)],
        key=lambda path: path.name,
        reverse=True,
    )


def backup_status() -> dict:
    directory = config.BACKUP_GIT_DIRECTORY
    local_files = _backup_files(directory) if directory.is_dir() else []
    latest = _backup_metadata(local_files[0]) if local_files else None
    return {
        "configured": bool(config.BACKUP_GIT_REPOSITORY.strip()),
        "git_available": git_available(),
        "local_count": len(local_files),
        "latest_local": latest,
    }


def list_repository_backups() -> list[dict]:
    with _REPOSITORY_LOCK:
        directory = _sync_checkout()
        return [_backup_metadata(path) for path in _backup_files(directory)]


def create_repository_backup() -> dict:
    with _REPOSITORY_LOCK:
        directory = _sync_checkout()
        _ensure_clean(directory)
        try:
            backup = backup_database(directory, prefix="portfolio")
        except Exception as exc:
            raise GitBackupError("Не удалось создать целостную копию SQLite") from exc
        _write_scaffold(directory)
        _ensure_identity(directory)
        _git(["add", "README.md", ".gitignore"], cwd=directory, action="подготовка описания vault")
        _git(["add", "-f", backup.name], cwd=directory, action="подготовка файла бэкапа")
        message = "backup " + datetime.now().strftime("%Y-%m-%d %H:%M")
        _git(["commit", "-m", message], cwd=directory, action="создание коммита бэкапа")
        try:
            _git(
                ["push", "-u", "origin", config.BACKUP_GIT_BRANCH],
                cwd=directory,
                action="отправка бэкапа",
            )
        except GitBackupError as exc:
            raise GitBackupError(
                "Бэкап сохранён локально, но не отправлен в приватный репозиторий. " + str(exc)
            ) from exc
        return _backup_metadata(backup)


def restore_repository_backup(filename: str) -> dict:
    if Path(filename).name != filename or not _BACKUP_NAME.fullmatch(filename):
        raise GitBackupError("Выбран недопустимый файл резервной копии")
    with _REPOSITORY_LOCK:
        directory = _sync_checkout()
        backup = (directory / filename).resolve()
        if backup.parent != directory.resolve() or not backup.is_file():
            raise GitBackupError("Резервная копия не найдена")
        try:
            validate_backup_database(backup)
        except Exception as exc:
            raise GitBackupError("Выбранный файл не прошёл проверку SQLite") from exc

        from ..db import engine, init_db

        try:
            with DATABASE_MAINTENANCE_LOCK:
                engine.dispose()
                _, safety_copy = restore_database(backup)
                init_db()
        except Exception as exc:
            raise GitBackupError("Не удалось восстановить базу из выбранной копии") from exc
        return {
            "restored": _backup_metadata(backup),
            "safety_backup": safety_copy.name if safety_copy else None,
        }
