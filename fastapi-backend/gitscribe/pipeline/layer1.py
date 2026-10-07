"""Layer 1: analyze one file's diff (fast model, cached across runs)."""

from __future__ import annotations

from gitscribe.db import store
from gitscribe.llm import factory
from gitscribe.pipeline.state import AnalyzeFileInput
from gitscribe.prompts import load_prompt
from gitscribe.schemas import FileChange

CHANGE_KINDS = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed"}


def analyze_file(inp: AnalyzeFileInput) -> dict:
    fd = inp["file"]
    prompt = load_prompt("analyze_file")
    model = factory.model_name("fast")

    cached = store.get_cached_analysis(fd["commit_sha"], fd["path"], prompt.id, model)
    if cached is not None:
        change, from_cache = FileChange.model_validate(cached), True
    else:
        kind = CHANGE_KINDS[fd["change_type"]]
        if fd["change_type"] == "R":
            kind += f" from {fd['old_path']}"
        messages = prompt.messages(
            commit_message=inp["commit_message"],
            path=fd["path"],
            change_kind=kind,
            additions=fd["additions"],
            deletions=fd["deletions"],
            diff=fd["diff"] or "(no content changes)",
        )
        change = factory.get_structured_model("fast", FileChange).invoke(messages)
        store.put_cached_analysis(fd["commit_sha"], fd["path"], prompt.id, model, change.model_dump())
        from_cache = False

    return {
        "analyses": [
            {
                "commit_sha": fd["commit_sha"],
                "path": fd["path"],
                "cached": from_cache,
                **change.model_dump(),
            }
        ]
    }
