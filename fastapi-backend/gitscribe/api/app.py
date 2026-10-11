"""HTTP API over the pipeline: start, resume and inspect runs, with SSE progress.

    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import git
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from gitscribe.api.models import ConfigInfo, PullRef, RepoRefs, RunCreate, RunInfo, RunResult
from gitscribe.api.runner import RunBusy, RunManager, synthesis_total
from gitscribe.config import get_settings
from gitscribe.db import store
from gitscribe.git import github, reader
from gitscribe.output import writers
from gitscribe.pipeline import graph

POLL_SECONDS = 0.25
PING_SECONDS = 15.0
RESUMABLE = {"failed", "interrupted"}


def _sse(event_id: int, type_: str, data: dict) -> str:
    return f"id: {event_id}\nevent: {type_}\ndata: {json.dumps(data)}\n\n"


def _open_local(repo: str) -> tuple[Path, git.Repo]:
    path = Path(repo).expanduser().resolve()
    try:
        r = reader.open_repo(str(path))
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        raise HTTPException(400, f"not a git repository: {path}")
    if not r.head.is_valid():
        raise HTTPException(400, f"repository has no commits: {path}")
    return path, r


def _local_refs(repo: str) -> RepoRefs:
    path, r = _open_local(repo)
    current = None if r.head.is_detached else r.active_branch.name
    branches = sorted((h.name for h in r.heads if h.name != current), key=str.lower)
    return RepoRefs(
        kind="local",
        repo_name=path.name,
        source=None,
        default_branch=current,
        branches=[current, *branches] if current else branches,
        pulls=[],
        branch=current,
    )


def _github_refs(gh: github.GitHubRepo) -> RepoRefs:
    refs = github.list_refs(gh)
    pulls = refs.pulls
    if gh.pr_hint and all(p.number != gh.pr_hint for p in pulls):
        pulls = [github.get_pull(gh, gh.pr_hint), *pulls]  # linked PR is closed or merged
    branch = None
    if gh.branch_hint:
        # tree/<branch>/<dir> links: the longest prefix that names a branch
        parts = gh.branch_hint.split("/")
        known = set(refs.branches)
        branch = next(("/".join(parts[:i]) for i in range(len(parts), 0, -1) if "/".join(parts[:i]) in known), None)
    if not gh.pr_hint and not branch:
        branch = refs.default_branch
    return RepoRefs(
        kind="github",
        repo_name=gh.full_name,
        source=gh.web_url,
        default_branch=refs.default_branch,
        branches=refs.branches,
        pulls=[PullRef(**vars(p)) for p in pulls],
        branch=branch,
        pr=gh.pr_hint,
    )


def create_app() -> FastAPI:
    manager = RunManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Runs that were live when the server last stopped can only be resumed now.
        store.mark_stale_runs_interrupted()
        yield

    app = FastAPI(title="GitScribe", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(get_settings().cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    def get_run_or_404(run_id: str) -> dict:
        row = store.get_run(run_id)
        if row is None:
            raise HTTPException(404, f"no run {run_id!r}")
        return row

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/config", response_model=ConfigInfo)
    def config() -> ConfigInfo:
        s = get_settings()
        return ConfigInfo(
            provider=s.llm_provider,
            base_url=s.llm_base_url,
            model_fast=s.llm_model_fast,
            model_strong=s.llm_model_strong,
            think_strong=s.llm_think_strong,
            num_ctx=s.num_ctx,
            max_concurrency=s.max_concurrency,
        )

    @app.get("/api/refs", response_model=RepoRefs)
    def list_refs(repo: str) -> RepoRefs:
        """Branches (and, for GitHub, pull requests) of a local path or GitHub link."""
        gh = github.parse_url(repo)
        if gh is None:
            return _local_refs(repo)
        try:
            return _github_refs(gh)
        except github.GitHubError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/runs", response_model=RunInfo, status_code=201)
    def create_run(body: RunCreate) -> RunInfo:
        gh = github.parse_url(body.repo)
        if gh is None:
            if body.pr:
                raise HTTPException(400, "pull requests need a GitHub repository link")
            path, repo = _open_local(body.repo)
            if body.branch:
                try:
                    repo.commit(body.branch)
                except (git.BadName, ValueError):
                    raise HTTPException(400, f"no branch or revision {body.branch!r} in {path}")
            ref = body.branch or (None if repo.head.is_detached else repo.active_branch.name)
            target = {"rev": body.branch or "HEAD", "ref": ref}
            name = path.name
        else:
            # Fetching can take a while; fail fast rather than fetch for a run that cannot start.
            if manager.active is not None:
                raise HTTPException(409, f"run {manager.active} is still running")
            branch, pr = (body.branch, body.pr) if body.branch or body.pr else (gh.branch_hint, gh.pr_hint)
            try:
                co = github.checkout(gh, branch=branch, pr=pr)
            except github.GitHubError as e:
                raise HTTPException(400, str(e))
            path = Path(co.path)
            target = {
                "rev": co.rev,
                "since_sha": co.since_sha,
                "source": gh.web_url,
                "ref": co.ref,
                "ref_title": co.ref_title,
            }
            name = gh.name
        out_dir = Path(body.out_dir).expanduser() if body.out_dir else Path("output") / name
        run_id = graph.new_run_id()
        try:
            manager.start(
                run_id, str(path), str(out_dir.resolve()), output=body.output, batch_by=body.batch_by, **target
            )
        except RunBusy as e:
            raise HTTPException(409, str(e))
        return RunInfo.from_row(get_run_or_404(run_id))

    @app.get("/api/runs", response_model=list[RunInfo])
    def list_runs(limit: int = 50) -> list[RunInfo]:
        return [RunInfo.from_row(r) for r in store.list_runs(limit)]

    @app.get("/api/runs/{run_id}", response_model=RunInfo)
    def get_run(run_id: str) -> RunInfo:
        return RunInfo.from_row(get_run_or_404(run_id))

    @app.post("/api/runs/{run_id}/resume", response_model=RunInfo)
    def resume_run(run_id: str) -> RunInfo:
        row = get_run_or_404(run_id)
        if row["status"] not in RESUMABLE:
            raise HTTPException(400, f"run {run_id} is {row['status']}; only failed or interrupted runs can resume")
        try:
            manager.start(
                run_id, row["repo_path"], row["out_dir"], output=row["output"], batch_by=row["batch_by"], resume=True
            )
        except RunBusy as e:
            raise HTTPException(409, str(e))
        return RunInfo.from_row(get_run_or_404(run_id))

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str, last_event_id: int = Header(0)) -> StreamingResponse:
        row = get_run_or_404(run_id)
        handle = manager.get(run_id)

        async def stream() -> AsyncIterator[str]:
            if handle is None:
                # Not live in this process: report where it stands and close.
                yield _sse(1, "status", {"status": row["status"], "error": row["error"]})
                return
            last, idle = last_event_id, 0.0
            while True:
                events, done = handle.events_after(last)
                for e in events:
                    yield _sse(e["id"], e["type"], e["data"])
                    last = e["id"]
                if done:
                    return
                await asyncio.sleep(POLL_SECONDS)
                idle = 0.0 if events else idle + POLL_SECONDS
                if idle >= PING_SECONDS:
                    yield ": ping\n\n"
                    idle = 0.0

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/result", response_model=RunResult)
    def run_result(run_id: str) -> RunResult:
        row = get_run_or_404(run_id)
        values, finished = graph.get_run_state(row["repo_path"], run_id)
        file_diffs = values.get("file_diffs")
        batches = values.get("batches")
        changelog_sections = values.get("changelog_sections", [])
        return RunResult(
            run=RunInfo.from_row(row),
            finished=finished,
            commit_count=len(values["commits"]) if "commits" in values else None,
            files_total=len(file_diffs) if file_diffs is not None else None,
            batches_total=(
                synthesis_total(batches, {fd["commit_sha"] for fd in file_diffs or []}) if batches is not None else None
            ),
            sections=values.get("sections", []),
            changelog_sections=changelog_sections,
            summaries=values.get("summaries", []),
            analyses=values.get("analyses", []),
            skipped=values.get("skipped", []),
            written=values.get("written"),
            markdown=writers.render_changelog(changelog_sections),
        )

    @app.get("/api/runs/{run_id}/changelog.md", response_class=PlainTextResponse)
    def run_changelog(run_id: str) -> PlainTextResponse:
        row = get_run_or_404(run_id)
        values, _ = graph.get_run_state(row["repo_path"], run_id)
        return PlainTextResponse(
            writers.render_changelog(values.get("changelog_sections", [])),
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=CHANGELOG.md"},
        )

    return app
