import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import config
from app.dataio import backup_database
from app.db import SessionLocal
from app.main import app
from app.models import Instrument
from app.services import git_backup


def test_default_backup_directory_follows_private_database(db):
    backup = backup_database()
    assert backup.parent == config.DB_PATH.parent / "backups"
    assert backup.is_file()


def test_github_secret_requires_github_https_repository(tmp_path, monkeypatch):
    secret = tmp_path / "github-token"
    secret.write_text("placeholder-token", encoding="utf-8")
    monkeypatch.setenv("PORTFOLIO_GITHUB_TOKEN_FILE", str(secret))
    monkeypatch.setattr(config, "BACKUP_GIT_REPOSITORY", "https://example.com/private/vault.git")

    with pytest.raises(git_backup.GitBackupError, match="только HTTPS-адрес github.com"):
        git_backup._configured_repository()


def test_github_secret_must_be_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_GITHUB_TOKEN_FILE", str(tmp_path / "missing"))
    monkeypatch.setattr(
        config,
        "BACKUP_GIT_REPOSITORY",
        "https://github.com/example/private-vault.git",
    )

    with pytest.raises(git_backup.GitBackupError, match="недоступен контейнеру"):
        git_backup._configured_repository()


def test_github_secret_accepts_scoped_https_repository(tmp_path, monkeypatch):
    secret = tmp_path / "github-token"
    secret.write_text("placeholder-token", encoding="utf-8")
    repository = "https://github.com/example/private-vault.git"
    monkeypatch.setenv("PORTFOLIO_GITHUB_TOKEN_FILE", str(secret))
    monkeypatch.setattr(config, "BACKUP_GIT_REPOSITORY", repository)

    assert git_backup._configured_repository() == repository


def _git(*args, cwd=None):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_private_git_backup_and_restore(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    _git("init", "--bare", str(remote))
    monkeypatch.setattr(config, "BACKUP_GIT_REPOSITORY", str(remote))
    monkeypatch.setattr(config, "BACKUP_GIT_DIRECTORY", checkout)
    monkeypatch.setattr(config, "BACKUP_GIT_BRANCH", "main")

    with SessionLocal() as db:
        db.add(Instrument(kind="share", name="Сохранённая позиция", ticker="SAVE"))
        db.commit()

    with TestClient(app) as client:
        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["backups"]["configured"] is True
        assert str(remote) not in str(status.json())

        created = client.post("/api/backups")
        assert created.status_code == 200
        filename = created.json()["backup"]["name"]

        listed = client.get("/api/backups")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()["items"]] == [filename]

        with SessionLocal() as db:
            db.add(Instrument(kind="share", name="Лишняя позиция", ticker="EXTRA"))
            db.commit()

        restored = client.post(
            "/api/backups/restore",
            json={"filename": filename, "confirm": True},
        )
        assert restored.status_code == 200
        assert restored.json()["safety_backup"].startswith("before-restore-")

    with SessionLocal() as db:
        names = {item.name for item in db.query(Instrument).all()}
    assert names == {"Сохранённая позиция"}
    assert int(_git("--git-dir", str(remote), "rev-list", "--count", "--all").stdout) == 1


def test_backup_restore_rejects_unlisted_filename():
    with TestClient(app) as client:
        response = client.post(
            "/api/backups/restore",
            json={"filename": "../portfolio-20260714-120000.db", "confirm": True},
        )
    assert response.status_code == 422
