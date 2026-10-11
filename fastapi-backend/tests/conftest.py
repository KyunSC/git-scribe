import os
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

from gitscribe.config import get_settings
from gitscribe.llm import factory
from gitscribe.schemas import BatchSummary, ChangelogEntry, ChangeNote, FileChange


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
    monkeypatch.setenv("REPOS_DIR", str(tmp_path / "repos"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class StubModels:
    def __init__(self):
        self.calls = Counter()
        self.fail_next = set()

    def __call__(self, kind, schema):
        def invoke(messages):
            self.calls[schema.__name__] += 1
            if schema.__name__ in self.fail_next:
                self.fail_next.discard(schema.__name__)
                raise RuntimeError("simulated crash")
            user = messages[-1][1]
            if schema is FileChange:
                return FileChange(summary=f"changed ({len(user)} chars)", change_type="feature", breaking=False)
            if schema is BatchSummary:
                return BatchSummary(
                    title="Add helper",
                    narrative="Adds a helper.",
                    notes=[ChangeNote(category="added", description="A helper function.")],
                )
            if schema is ChangelogEntry:
                return ChangelogEntry.empty().model_copy(update={"added": ["A helper function."]})
            raise AssertionError(schema)

        return RunnableLambda(invoke)


@pytest.fixture
def stub(monkeypatch):
    s = StubModels()
    monkeypatch.setattr(factory, "get_structured_model", s)
    return s


@pytest.fixture
def small_repo(repo):
    repo.write("app/main.py", "def main():\n    return 1\n")
    repo.write("yarn.lock", "# lock\n")
    repo.commit("Initial commit", "2026-01-05T10:00:00+00:00")
    repo.git("tag", "v1.0")
    repo.write("app/util.py", "def helper(x):\n    return x * 2\n")
    repo.write("app/main.py", "from app.util import helper\n\ndef main():\n    return helper(1)\n")
    repo.commit("Add helper", "2026-01-06T10:00:00+00:00")
    return repo
