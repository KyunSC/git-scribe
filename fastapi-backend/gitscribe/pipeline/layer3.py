"""Layer 3: turn batch summaries into output documents (strong model)."""

from __future__ import annotations

from gitscribe.config import get_settings
from gitscribe.llm import factory
from gitscribe.pipeline.state import ChangelogInput
from gitscribe.prompts import load_prompt
from gitscribe.schemas import ChangelogEntry


def _format_summary(s: dict) -> str:
    lines = [f"### {s['title']} ({s['date'][:10]})", s["narrative"]]
    lines += [f"- {n['category']}: {n['description']}" for n in s["notes"]]
    lines += [f"- BREAKING: {b}" for b in s["breaking_changes"]]
    return "\n".join(lines)


def _chunks(blocks: list[str], budget: int) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    size = 0
    for b in blocks:
        if chunks[-1] and size + len(b) > budget:
            chunks.append([])
            size = 0
        chunks[-1].append(b)
        size += len(b) + 2
    return chunks


def _merge(entries: list[ChangelogEntry]) -> ChangelogEntry:
    merged = ChangelogEntry.empty()
    for e in entries:
        for field in ChangelogEntry.model_fields:
            for item in getattr(e, field):
                if item not in getattr(merged, field):
                    getattr(merged, field).append(item)
    return merged


def _from_notes(summaries: list[dict]) -> ChangelogEntry:
    """Deterministic entry built straight from layer-2 notes."""
    entry = ChangelogEntry.empty()
    for s in summaries:
        for n in s["notes"]:
            getattr(entry, n["category"]).append(n["description"])
        entry.breaking.extend(s["breaking_changes"])
    return _merge([entry])


def gen_changelog(inp: ChangelogInput) -> dict:
    section = inp["section"]
    prompt = load_prompt("changelog")
    budget = get_settings().max_prompt_chars - len(prompt.system)
    blocks = [_format_summary(s) for s in sorted(inp["summaries"], key=lambda s: s["date"])]

    # Large releases are summarized in chunks and the results concatenated.
    model = factory.get_structured_model("strong", ChangelogEntry)
    entries = [
        model.invoke(prompt.messages(section=section["label"], summaries="\n\n".join(chunk)))
        for chunk in _chunks(blocks, budget)
    ]
    entry = _merge(entries)
    if entry.is_empty():
        # Small local models occasionally return all-empty lists; don't lose layer 2's work.
        entry = _from_notes(inp["summaries"])
    return {"changelog_sections": [{**section, "entry": entry.model_dump()}]}
