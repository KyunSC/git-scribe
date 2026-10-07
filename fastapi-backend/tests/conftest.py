import os
import subprocess
from pathlib import Path

import pytest

from gitscribe.config import get_settings


def _git(cwd: Path, *args: str, extra_env: dict[str, str] | None = None) -> str:
    env = {
        **os.environ,
        **(extra_env or {}),
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


class RepoBuilder:
    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True)
        _git(path, "init", "-q", "-b", "main")
        _git(path, "config", "commit.gpgsign", "false")
        _git(path, "config", "tag.gpgsign", "false")

    def write(self, rel: str, content: str | bytes) -> None:
        f = self.path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            f.write_bytes(content)
        else:
            f.write_text(content)

    def commit(self, message: str, date: str = "2026-01-05T12:00:00+00:00") -> str:
        _git(self.path, "add", "-A")
        dates = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        _git(self.path, "commit", "-q", "--allow-empty", "-m", message, extra_env=dates)
        return self.head()

    def head(self) -> str:
        return _git(self.path, "rev-parse", "HEAD")

    def git(self, *args: str, date: str | None = None) -> str:
        dates = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else None
        return _git(self.path, *args, extra_env=dates)


@pytest.fixture
def repo(tmp_path: Path) -> RepoBuilder:
    return RepoBuilder(tmp_path / "repo")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
