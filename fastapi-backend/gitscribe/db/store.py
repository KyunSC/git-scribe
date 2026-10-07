"""SQLite-backed cache of layer-1 analyses.

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
"""


@contextmanager
def _connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or get_settings().db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


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
