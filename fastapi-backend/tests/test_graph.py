"""Graph wiring tests with a stub model, so no Ollama is needed."""

from collections import Counter
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

from gitscribe.llm import factory
from gitscribe.pipeline import graph
from gitscribe.schemas import BatchSummary, ChangelogEntry, ChangeNote, FileChange


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


def test_end_to_end_changelog(small_repo, stub, tmp_path):
    out = tmp_path / "out"
    state = graph.run_pipeline(str(small_repo.path), str(out))

    assert len(state["analyses"]) == 3  # yarn.lock filtered
    assert {s["reason"] for s in state["skipped"]} == {"lockfile"}
    assert [s["label"] for s in state["sections"]] == ["v1.0", "Unreleased"]
    assert stub.calls == {"FileChange": 3, "BatchSummary": 2, "ChangelogEntry": 2}

    text = (out / "CHANGELOG.md").read_text()
    assert text.index("## [Unreleased]") < text.index("## [v1.0] - 2026-01-05")
    assert "### Added\n\n- A helper function." in text

    # A second run reuses every layer-1 analysis from the cache.
    graph.run_pipeline(str(small_repo.path), str(out))
    assert stub.calls["FileChange"] == 3


def test_resume_skips_finished_tasks(small_repo, stub, tmp_path):
    stub.fail_next.add("BatchSummary")
    with pytest.raises(RuntimeError, match="simulated crash"):
        graph.run_pipeline(str(small_repo.path), str(tmp_path / "out"), run_id="r1")
    assert stub.calls["FileChange"] == 3

    with pytest.raises(graph.RunNotFound):
        graph.run_pipeline(str(small_repo.path), str(tmp_path / "out"), run_id="nope", resume=True)

    state = graph.run_pipeline(str(small_repo.path), str(tmp_path / "out"), run_id="r1", resume=True)
    assert stub.calls["FileChange"] == 3  # layer 1 not re-run
    assert Path(state["written"][0]).exists()


def test_repo_with_only_noise(repo, stub, tmp_path):
    repo.write(".DS_Store", b"\x00junk")
    repo.commit("junk")
    state = graph.run_pipeline(str(repo.path), str(tmp_path / "out"))
    assert sum(stub.calls.values()) == 0
    assert "## [" not in (tmp_path / "out" / "CHANGELOG.md").read_text()


def test_empty_changelog_falls_back_to_batch_notes(small_repo, stub, monkeypatch, tmp_path):
    real = stub.__call__

    def empty_changelog(kind, schema):
        if schema is ChangelogEntry:
            return RunnableLambda(lambda _: ChangelogEntry.empty())
        return real(kind, schema)

    monkeypatch.setattr(factory, "get_structured_model", empty_changelog)
    graph.run_pipeline(str(small_repo.path), str(tmp_path / "out"))
    assert "- A helper function." in (tmp_path / "out" / "CHANGELOG.md").read_text()
