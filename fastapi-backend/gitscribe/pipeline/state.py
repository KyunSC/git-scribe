"""Graph state. Everything in here is plain JSON-able data so it checkpoints cleanly."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class PipelineState(TypedDict, total=False):
    # inputs
    repo_path: str
    since_sha: str | None
    batch_by: str  # "pr" | "tag" | "week"
    output: str  # "changelog"
    out_dir: str

    # load_commits
    head_sha: str
    commits: list[dict]  # reader.CommitInfo as dict

    # filter_changes
    file_diffs: list[dict]  # reader.FileDiff (kept, truncated) as dict
    skipped: list[dict]  # filters.Skipped as dict

    # layer 1 (fan-out; reducer merges parallel results)
    analyses: Annotated[list[dict], operator.add]

    # group_batches
    batches: list[dict]  # reader.Batch as dict
    sections: list[dict]  # {label, date, order}

    # layer 2
    summaries: Annotated[list[dict], operator.add]

    # layer 3
    changelog_sections: Annotated[list[dict], operator.add]

    # write_output
    written: list[str]


class AnalyzeFileInput(TypedDict):
    file: dict
    commit_message: str


class SynthesizeBatchInput(TypedDict):
    batch: dict
    commits: list[dict]
    analyses: list[dict]


class ChangelogInput(TypedDict):
    section: dict
    summaries: list[dict]
