"""CLI: python -m gitscribe run <repo> [--output changelog] [--out-dir DIR] [--resume RUN_ID]"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from gitscribe.config import get_settings
from gitscribe.pipeline import graph

app = typer.Typer(add_completion=False, help="Generate documentation from git history with a local LLM.")


class Output(str, Enum):
    changelog = "changelog"


@app.callback()
def main() -> None:
    """GitScribe."""


def _progress():
    total = {"files": 0, "batches": 0}
    done = {"files": 0, "cached": 0, "batches": 0}

    def on_update(node: str, update: Any) -> None:
        update = update or {}
        if node == "load_commits":
            typer.echo(f"• {len(update['commits'])} commits")
        elif node == "filter_changes":
            total["files"] = len(update["file_diffs"])
            typer.echo(f"• {total['files']} file changes to analyze, {len(update['skipped'])} skipped as noise")
        elif node == "analyze_file":
            a = update["analyses"][0]
            done["files"] += 1
            done["cached"] += a["cached"]
            tag = " (cached)" if a["cached"] else ""
            typer.echo(f"  [{done['files']}/{total['files']}] {a['commit_sha'][:8]} {a['path']}{tag}")
        elif node == "group_batches":
            total["batches"] = len(update["batches"])
            typer.echo(f"• {total['batches']} batches, {len(update['sections'])} release section(s)")
        elif node == "synthesize_batch":
            s = update["summaries"][0]
            done["batches"] += 1
            typer.echo(f"  [{done['batches']}/{total['batches']}] {s['title']}")
        elif node == "gen_changelog":
            typer.echo(f"• changelog section: {update['changelog_sections'][0]['label']}")
        elif node == "write_output":
            for path in update["written"]:
                typer.echo(f"• wrote {path}")

    return on_update, done


@app.command()
def run(
    repo: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Path to a local git repository.")],
    output: Annotated[Output, typer.Option(help="Which document to generate.")] = Output.changelog,
    out_dir: Annotated[
        Optional[Path], typer.Option(help="Where to write docs. Default: ./output/<repo name>")
    ] = None,
    resume: Annotated[Optional[str], typer.Option(help="Resume an interrupted run by its run id.")] = None,
) -> None:
    """Analyze a repository's history and write documentation."""
    s = get_settings()
    out = out_dir or Path("output") / repo.resolve().name
    run_id = resume or graph.new_run_id()
    typer.echo(f"run id: {run_id}   (resume with --resume {run_id})")
    typer.echo(f"models: fast={s.llm_model_fast} strong={s.llm_model_strong} num_ctx={s.num_ctx}  db={s.db_path}")

    on_update, done = _progress()
    try:
        state = graph.run_pipeline(
            str(repo), str(out), output=output.value, run_id=run_id, resume=bool(resume), on_update=on_update
        )
    except graph.RunNotFound as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(f"done: {done['files']} files analyzed this session ({done['cached']} from cache)")
    if not state.get("written"):
        typer.echo("nothing written")


if __name__ == "__main__":
    app()
