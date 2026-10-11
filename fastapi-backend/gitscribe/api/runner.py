"""In-process run manager: one pipeline run at a time, on a background thread.

Each live run has a `RunHandle` that turns LangGraph node updates into compact
progress events (no diffs) for the SSE endpoint to replay and tail.
"""

from __future__ import annotations

import threading
from typing import Any

from gitscribe.db import store
from gitscribe.pipeline import graph


class RunBusy(Exception):
    """Another run is already active (there is a single local LLM to share)."""


def synthesis_total(batches: list[dict], analyzed_shas: set[str]) -> int:
    """Batches layer 2 will summarize: those with at least one analyzed file."""
    return sum(1 for b in batches if analyzed_shas.intersection(b["commit_shas"]))


class RunHandle:
    def __init__(self, run_id: str, kept_shas: set[str] | None = None):
        self.run_id = run_id
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._done = False
        # Commits with files left after noise filtering; on resume, seeded from the checkpoint.
        self._kept_shas = kept_shas or set()

    def emit(self, type_: str, data: dict) -> None:
        with self._lock:
            self._events.append({"id": len(self._events) + 1, "type": type_, "data": data})

    def finish(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self._events.append(
                {"id": len(self._events) + 1, "type": "status", "data": {"status": status, "error": error}}
            )
            self._done = True

    def events_after(self, last_id: int) -> tuple[list[dict], bool]:
        """Events with an id above `last_id`, and whether the run has ended."""
        with self._lock:
            return self._events[last_id:], self._done

    def on_update(self, node: str, update: Any) -> None:
        update = update or {}
        if node == "load_commits":
            self.emit("commits", {"count": len(update["commits"])})
        elif node == "filter_changes":
            self._kept_shas = {fd["commit_sha"] for fd in update["file_diffs"]}
            self.emit("filtered", {"files_total": len(update["file_diffs"]), "skipped": update["skipped"]})
        elif node == "analyze_file":
            a = update["analyses"][0]
            keys = ("commit_sha", "path", "cached", "change_type", "breaking", "summary")
            self.emit("file_analyzed", {k: a[k] for k in keys})
        elif node == "group_batches":
            self.emit(
                "batches",
                {
                    "batches_total": synthesis_total(update["batches"], self._kept_shas),
                    "sections": update["sections"],
                },
            )
        elif node == "synthesize_batch":
            s = update["summaries"][0]
            self.emit(
                "batch_summarized",
                {
                    "batch_id": s["batch_id"],
                    "title": s["title"],
                    "section": s["section"],
                    "note_count": len(s["notes"]),
                    "breaking_count": len(s["breaking_changes"]),
                },
            )
        elif node == "gen_changelog":
            c = update["changelog_sections"][0]
            self.emit("changelog_section", {"label": c["label"], "date": c["date"]})
        elif node == "write_output":
            self.emit("written", {"paths": update["written"]})


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handles: dict[str, RunHandle] = {}
        self._active: str | None = None

    def get(self, run_id: str) -> RunHandle | None:
        return self._handles.get(run_id)

    @property
    def active(self) -> str | None:
        return self._active

    def start(
        self,
        run_id: str,
        repo_path: str,
        out_dir: str,
        output: str = "changelog",
        batch_by: str = "pr",
        resume: bool = False,
        rev: str = "HEAD",
        since_sha: str | None = None,
        source: str | None = None,
        ref: str | None = None,
        ref_title: str | None = None,
    ) -> RunHandle:
        """Record the run as running and start it on a background thread.

        `rev`, `since_sha` and the ref metadata only apply to new runs; a
        resumed run continues from its checkpoint. Raises `RunBusy` if another
        run is active.
        """
        with self._lock:
            if self._active is not None:
                raise RunBusy(f"run {self._active} is still running")
            self._active = run_id
            try:
                kept: set[str] = set()
                if resume:
                    values, _ = graph.get_run_state(repo_path, run_id)
                    kept = {fd["commit_sha"] for fd in values.get("file_diffs", [])}
                    store.set_run_status(run_id, "running")
                else:
                    store.create_run(run_id, repo_path, output, batch_by, out_dir, source, ref, ref_title)
            except Exception:
                self._active = None
                raise
            handle = self._handles[run_id] = RunHandle(run_id, kept)
        handle.emit("status", {"status": "running", "error": None})

        def work() -> None:
            try:
                graph.run_pipeline(
                    repo_path,
                    out_dir,
                    output=output,
                    batch_by=batch_by,
                    run_id=run_id,
                    resume=resume,
                    on_update=handle.on_update,
                    rev=rev,
                    since_sha=since_sha,
                )
                status, error = "done", None
            except Exception as exc:
                status, error = "failed", str(exc) or type(exc).__name__
            # Free the slot first, so a client that sees the terminal status can start another run.
            with self._lock:
                self._active = None
            store.set_run_status(run_id, status, error)
            handle.finish(status, error)

        threading.Thread(target=work, name=f"gitscribe-run-{run_id}", daemon=True).start()
        return handle
