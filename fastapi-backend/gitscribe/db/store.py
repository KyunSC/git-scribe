"""SQLite-backed cache of layer-1 analyses, plus the API's run registry.

Lives in the same file as the LangGraph checkpointer. Each call opens its own
short-lived connection, since layer-1 nodes run concurrently in threads.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from gitscribe.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_cache (
    commit_sha  TEXT NOT NULL,
    path        TEXT NOT NULL,
    prompt_id   TEXT NOT NULL,
    model       TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (commit_sha, path, prompt_id, model)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    repo_path   TEXT NOT NULL,
    output      TEXT NOT NULL,
    batch_by    TEXT NOT NULL,
    out_dir     TEXT NOT NULL,
    status      TEXT NOT NULL,          -- running | done | failed | interrupted
    error       TEXT,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    source      TEXT,                   -- GitHub URL when the repo was cloned from one
    ref         TEXT,                   -- branch name or "#<pr number>"
    ref_title   TEXT                    -- pull request title
);
"""

# Columns added to `runs` after it first shipped; older databases get them on connect.
_RUN_COLUMNS = ("source", "ref", "ref_title")

TERMINAL_STATUSES = {"done", "failed", "interrupted"}


@contextmanager
def _connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or get_settings().db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    have = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    for col in _RUN_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} TEXT")


def get_cached_analysis(commit_sha: str, path: str, prompt_id: str, model: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM analysis_cache WHERE commit_sha=? AND path=? AND prompt_id=? AND model=?",
            (commit_sha, path, prompt_id, model),
        ).fetchone()
    return json.loads(row[0]) if row else None


def put_cached_analysis(commit_sha: str, path: str, prompt_id: str, model: str, result: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_cache (commit_sha, path, prompt_id, model, result_json) VALUES (?,?,?,?,?)",
            (commit_sha, path, prompt_id, model, json.dumps(result)),
        )


# --- runs -------------------------------------------------------------------


def _run_row(cur: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: value for col, value in zip(cur.description, row)}


def create_run(
    run_id: str,
    repo_path: str,
    output: str,
    batch_by: str,
    out_dir: str,
    source: str | None = None,
    ref: str | None = None,
    ref_title: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, repo_path, output, batch_by, out_dir, status, source, ref, ref_title)"
            " VALUES (?,?,?,?,?,'running',?,?,?)",
            (run_id, repo_path, output, batch_by, out_dir, source, ref, ref_title),
        )


def set_run_status(run_id: str, status: str, error: str | None = None) -> None:
    """Update a run's status; terminal statuses also stamp `finished_at`."""
    finished = "datetime('now')" if status in TERMINAL_STATUSES else "NULL"
    with _connect() as conn:
        conn.execute(
            f"UPDATE runs SET status=?, error=?, finished_at={finished} WHERE run_id=?",
            (status, error, run_id),
        )


def get_run(run_id: str) -> dict | None:
    with _connect() as conn:
        conn.row_factory = _run_row
        return conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()


def list_runs(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        conn.row_factory = _run_row
        return conn.execute("SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()


def mark_stale_runs_interrupted() -> int:
    """Runs left `running` by a server that stopped mid-run can only be resumed."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE runs SET status='interrupted', finished_at=datetime('now') WHERE status='running'"
        )
        return cur.rowcount
