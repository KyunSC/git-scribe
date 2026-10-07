"""Layer 2: synthesize the file analyses of one batch into a coherent summary (strong model)."""

from __future__ import annotations

from gitscribe.config import get_settings
from gitscribe.llm import factory
from gitscribe.pipeline.state import SynthesizeBatchInput
from gitscribe.prompts import load_prompt
from gitscribe.schemas import BatchSummary


def _format_analysis(a: dict) -> str:
    flags = [a["change_type"]] + (["BREAKING"] if a["breaking"] else [])
    line = f"- [{a['commit_sha'][:8]}] {a['path']} ({', '.join(flags)}): {a['summary']}"
    if a["public_api_changes"]:
        line += "\n  API: " + "; ".join(a["public_api_changes"])
    return line


def _fit(lines: list[str], budget: int) -> str:
    """Join lines until the budget is used up, noting how many were dropped."""
    out, size = [], 0
    for i, line in enumerate(lines):
        if size + len(line) > budget:
            out.append(f"[... {len(lines) - i} more file analyses omitted for length ...]")
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out)


def synthesize_batch(inp: SynthesizeBatchInput) -> dict:
    batch = inp["batch"]
    prompt = load_prompt("synthesize_batch")
    budget = get_settings().max_prompt_chars

    commits = "\n".join(f"- [{c['sha'][:8]}] {c['date'][:10]} {c['message'].splitlines()[0]}" for c in inp["commits"])
    # Breaking and API-changing analyses first, so they survive truncation.
    ranked = sorted(inp["analyses"], key=lambda a: (not a["breaking"], not a["public_api_changes"]))
    analyses = _fit([_format_analysis(a) for a in ranked], budget - len(commits) - len(prompt.system))

    summary = factory.get_structured_model("strong", BatchSummary).invoke(
        prompt.messages(label=batch["label"], commits=commits, analyses=analyses)
    )
    return {
        "summaries": [
            {
                "batch_id": batch["id"],
                "label": batch["label"],
                "section": batch["section"],
                "date": batch["date"],
                **summary.model_dump(),
            }
        ]
    }
