"""Request and response models for the HTTP API."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from gitscribe.git import github

RunStatus = Literal["running", "done", "failed", "interrupted"]


def _utc_iso(value: str | None) -> str | None:
    """SQLite's `datetime('now')` (UTC, no zone) as ISO 8601 that browsers parse as UTC."""
    return f"{value.replace(' ', 'T')}Z" if value and " " in value else value


class RunCreate(BaseModel):
    repo: str = Field(description="A local repository path or a GitHub repository link")
    # Which history to document; defaults to HEAD (local) or the default branch (GitHub).
    # A GitHub link to .../tree/<branch> or .../pull/<n> selects that ref when neither is given.
    branch: str | None = None
    pr: int | None = Field(None, gt=0, description="GitHub pull request number: documents only its commits")
    batch_by: Literal["pr", "tag", "week"] = "pr"
    output: Literal["changelog"] = "changelog"
    out_dir: str | None = None

    @model_validator(mode="after")
    def _one_ref(self) -> "RunCreate":
        if self.branch and self.pr:
            raise ValueError("choose a branch or a pull request, not both")
        return self


class PullRef(BaseModel):
    number: int
    title: str
    base: str
    head: str
    author: str
    state: str
    draft: bool


class RepoRefs(BaseModel):
    """Refs a run can document, and which one the link (if any) pointed at."""

    kind: Literal["local", "github"]
    repo_name: str
    source: str | None
    default_branch: str | None
    branches: list[str]
    pulls: list[PullRef]
    branch: str | None = None
    pr: int | None = None


def repo_name(repo_path: str, source: str | None) -> str:
    gh = github.parse_url(source) if source else None
    return gh.full_name if gh else Path(repo_path).name


class RunInfo(BaseModel):
    run_id: str
    repo_path: str
    repo_name: str
    source: str | None = None
    ref: str | None = None
    ref_title: str | None = None
    output: str
    batch_by: str
    out_dir: str
    status: RunStatus
    error: str | None = None
    started_at: str
    finished_at: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "RunInfo":
        times = {k: _utc_iso(row[k]) for k in ("started_at", "finished_at")}
        return cls(**{**row, **times}, repo_name=repo_name(row["repo_path"], row.get("source")))


class ConfigInfo(BaseModel):
    provider: str
    base_url: str
    model_fast: str
    model_strong: str
    think_strong: bool
    num_ctx: int
    max_concurrency: int


class RunResult(BaseModel):
    """Whatever a run has checkpointed so far; partial for running or failed runs.

    Counts are None until the stage that produces them has been checkpointed.
    """

    run: RunInfo
    finished: bool
    commit_count: int | None
    files_total: int | None
    batches_total: int | None
    sections: list[dict]
    changelog_sections: list[dict]
    summaries: list[dict]
    analyses: list[dict]  # layer-1 results, never the diffs themselves
    skipped: list[dict]
    written: list[str] | None
    markdown: str
