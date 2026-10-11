"""Render pipeline results to markdown files."""

from __future__ import annotations

from pathlib import Path

CHANGELOG_HEADINGS = [
    ("breaking", "Breaking"),
    ("added", "Added"),
    ("changed", "Changed"),
    ("deprecated", "Deprecated"),
    ("removed", "Removed"),
    ("fixed", "Fixed"),
    ("security", "Security"),
]


def render_changelog(sections: list[dict]) -> str:
    lines = [
        "# Changelog",
        "",
        "All notable changes to this project, generated from git history by GitScribe.",
        "",
    ]
    for s in sorted(sections, key=lambda s: s["order"], reverse=True):
        lines += [f"## [{s['label']}] - {s['date']}", ""]
        entry = s["entry"]
        if not any(entry.get(k) for k, _ in CHANGELOG_HEADINGS):
            lines += ["_No user-facing changes._", ""]
            continue
        for key, heading in CHANGELOG_HEADINGS:
            if items := entry.get(key):
                lines += [f"### {heading}", ""] + [f"- {item}" for item in items] + [""]
    return "\n".join(lines).rstrip() + "\n"


def write_changelog(out_dir: str, sections: list[dict]) -> str:
    path = Path(out_dir) / "CHANGELOG.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_changelog(sections))
    return str(path)
