"""LangGraph pipeline: git history -> per-file analyses -> batch summaries -> docs.

    START → load_commits → filter_changes
          → [Send per file]  analyze_file       (layer 1)
          → group_batches
          → [Send per batch] synthesize_batch   (layer 2)
          → route_outputs
          → [Send per release] gen_changelog    (layer 3)
          → write_output → END
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from gitscribe.config import get_settings
from gitscribe.git import filters, reader
from gitscribe.llm import factory
from gitscribe.output import writers
from gitscribe.pipeline.layer1 import analyze_file
from gitscribe.pipeline.layer2 import synthesize_batch
from gitscribe.pipeline.layer3 import gen_changelog
from gitscribe.pipeline.state import PipelineState

LLM_RETRY = RetryPolicy(max_attempts=3, retry_on=factory.is_retryable)


class RunNotFound(Exception):
    pass


# --- deterministic nodes ----------------------------------------------------


def load_commits(state: PipelineState) -> dict:
    repo = reader.open_repo(state["repo_path"])
    commits = reader.read_commits(repo, since_sha=state.get("since_sha"))
    return {"head_sha": repo.head.commit.hexsha, "commits": [asdict(c) for c in commits]}


def filter_changes(state: PipelineState) -> dict:
    repo = reader.open_repo(state["repo_path"])
    diffs = [d for c in state["commits"] for d in reader.file_diffs(repo, c["sha"])]
    result = filters.filter_diffs(diffs, get_settings().max_diff_chars)
    return {
        "file_diffs": [asdict(d) for d in result.kept],
        "skipped": [asdict(s) for s in result.skipped],
    }


def group_batches(state: PipelineState) -> dict:
    repo = reader.open_repo(state["repo_path"])
    commits = [reader.CommitInfo(**c) for c in state["commits"]]
    batches, sections = reader.make_batches(repo, commits, state.get("batch_by", "pr"), rev=state["head_sha"])
    return {
        "batches": [asdict(b) for b in batches],
        "sections": [{"label": s.label, "date": s.date, "order": s.order} for s in sections],
    }


def route_outputs(state: PipelineState) -> dict:
    """Join point after layer 2, so layer-3 fan-out happens exactly once."""
    return {}


def write_output(state: PipelineState) -> dict:
    written = []
    if state.get("output", "changelog") == "changelog":
        written.append(writers.write_changelog(state["out_dir"], state.get("changelog_sections", [])))
    return {"written": written}


# --- fan-out edges ----------------------------------------------------------


def fan_out_files(state: PipelineState) -> list[Send] | str:
    messages = {c["sha"]: c["message"] for c in state["commits"]}
    sends = [
        Send("analyze_file", {"file": fd, "commit_message": messages[fd["commit_sha"]]})
        for fd in state["file_diffs"]
    ]
    return sends or "group_batches"


def fan_out_batches(state: PipelineState) -> list[Send] | str:
    commits = {c["sha"]: c for c in state["commits"]}
    by_commit: dict[str, list[dict]] = {}
    for a in state.get("analyses", []):
        by_commit.setdefault(a["commit_sha"], []).append(a)
    sends = []
    for b in state["batches"]:
        analyses = [a for sha in b["commit_shas"] for a in by_commit.get(sha, [])]
        if analyses:  # batches whose files were all filtered out produce nothing
            batch_commits = [commits[s] for s in b["commit_shas"]]
            sends.append(Send("synthesize_batch", {"batch": b, "commits": batch_commits, "analyses": analyses}))
    return sends or "route_outputs"


def fan_out_outputs(state: PipelineState) -> list[Send] | str:
    sends = []
    if state.get("output", "changelog") == "changelog":
        summaries = state.get("summaries", [])
        for section in state["sections"]:
            members = [s for s in summaries if s["section"] == section["label"]]
            if members:
                sends.append(Send("gen_changelog", {"section": section, "summaries": members}))
    return sends or "write_output"


# --- graph ------------------------------------------------------------------


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    g = StateGraph(PipelineState)
    g.add_node("load_commits", load_commits)
    g.add_node("filter_changes", filter_changes)
    g.add_node("analyze_file", analyze_file, retry_policy=LLM_RETRY)
    g.add_node("group_batches", group_batches)
    g.add_node("synthesize_batch", synthesize_batch, retry_policy=LLM_RETRY)
    g.add_node("route_outputs", route_outputs)
    g.add_node("gen_changelog", gen_changelog, retry_policy=LLM_RETRY)
    g.add_node("write_output", write_output)

    g.add_edge(START, "load_commits")
    g.add_edge("load_commits", "filter_changes")
    g.add_conditional_edges("filter_changes", fan_out_files, ["analyze_file", "group_batches"])
    g.add_edge("analyze_file", "group_batches")
    g.add_conditional_edges("group_batches", fan_out_batches, ["synthesize_batch", "route_outputs"])
    g.add_edge("synthesize_batch", "route_outputs")
    g.add_conditional_edges("route_outputs", fan_out_outputs, ["gen_changelog", "write_output"])
    g.add_edge("gen_changelog", "write_output")
    g.add_edge("write_output", END)
    return g.compile(checkpointer=checkpointer)


# --- running ----------------------------------------------------------------


def repo_id(repo_path: str) -> str:
    path = Path(repo_path).resolve()
    return f"{path.name}-{hashlib.sha1(str(path).encode()).hexdigest()[:8]}"


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


@contextmanager
def sqlite_checkpointer(db_path: str | None = None) -> Iterator[SqliteSaver]:
    conn = sqlite3.connect(db_path or get_settings().db_path, check_same_thread=False, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield SqliteSaver(conn)
    finally:
        conn.close()


def run_pipeline(
    repo_path: str,
    out_dir: str,
    output: str = "changelog",
    batch_by: str = "pr",
    run_id: str | None = None,
    resume: bool = False,
    on_update: Callable[[str, Any], None] | None = None,
) -> dict:
    """Run (or resume) the pipeline and return the final state.

    Each run is its own checkpoint thread `<repo_id>:<run_id>`; resuming a run
    re-executes only the tasks that had not finished. Layer-1 results are also
    cached across runs in the analysis cache.
    """
    run_id = run_id or new_run_id()
    config = {
        "configurable": {"thread_id": f"{repo_id(repo_path)}:{run_id}"},
        "max_concurrency": get_settings().max_concurrency,
        "recursion_limit": 50,
    }
    with sqlite_checkpointer() as saver:
        graph = build_graph(saver)
        if resume:
            snapshot = graph.get_state(config)
            if not snapshot.values:
                raise RunNotFound(f"no run {run_id!r} found for this repo")
            inputs = None  # continue from the last checkpoint
            if not snapshot.next:
                return snapshot.values  # already finished
        else:
            inputs = {
                "repo_path": str(Path(repo_path).resolve()),
                "since_sha": None,
                "batch_by": batch_by,
                "output": output,
                "out_dir": str(Path(out_dir).resolve()),
            }
        for chunk in graph.stream(inputs, config, stream_mode="updates"):
            for node, update in chunk.items():
                if on_update:
                    on_update(node, update)
        return graph.get_state(config).values
