"""Graph wiring tests with a stub model, so no Ollama is needed."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

from gitscribe.llm import factory
from gitscribe.pipeline import graph
from gitscribe.schemas import ChangelogEntry


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
