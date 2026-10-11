"""Deterministic offline stand-in for an LLM (`LLM_PROVIDER=fake`).

For UI development without Ollama: every call sleeps briefly so progress is
visible, then returns a canned instance of the requested schema.
"""

from __future__ import annotations

import re
import time

from langchain_core.runnables import Runnable, RunnableLambda

from gitscribe.schemas import BatchSummary, ChangelogEntry, ChangeNote, FileChange

DELAY_SECONDS = 0.3


def _line(text: str, pattern: str, default: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(1).strip() if m else default


def structured_model(schema: type) -> Runnable:
    def invoke(messages):
        time.sleep(DELAY_SECONDS)
        text = messages[-1][1]
        if schema is FileChange:
            path = _line(text, r"^File: (\S+)", "this file")
            return FileChange(summary=f"Updates {path}.", change_type="feature", breaking=False)
        if schema is BatchSummary:
            label = _line(text, r"^Batch: (.+)$", "changes")[:60]
            return BatchSummary(
                title=label,
                narrative=f"Placeholder narrative for {label!r} from the fake provider.",
                notes=[ChangeNote(category="changed", description=f"{label}.")],
            )
        if schema is ChangelogEntry:
            titles = re.findall(r"^### (.+?) \(\d{4}-\d{2}-\d{2}\)$", text, re.M)
            return ChangelogEntry.empty().model_copy(update={"changed": [f"{t}." for t in titles]})
        raise ValueError(f"fake provider has no canned {schema.__name__}")

    return RunnableLambda(invoke)
