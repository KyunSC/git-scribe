"""Drop noisy file changes before they reach the LLM, and fit the rest into the context window."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from gitscribe.git.reader import FileDiff

LOCKFILES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
    "flake.lock",
    "Podfile.lock",
}

JUNK_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

GENERATED_SUFFIXES = (
    ".pb.go",
    "_pb2.py",
    "_pb2_grpc.py",
    ".min.js",
    ".min.css",
    ".map",
    ".snap",
)

GENERATED_PATTERNS = (re.compile(r"\.generated\.[^/]+$"), re.compile(r"(^|/)generated/"))

VENDORED_DIRS = {"node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "venv", "site-packages"}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".so", ".dylib",
    ".dll", ".exe", ".class", ".jar", ".pyc", ".db", ".sqlite",
}  # fmt: skip

# Migrations whose only change is a regenerated timestamp header.
_TIMESTAMP_LINE = re.compile(r"^[+-].*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|generated (on|at)|auto-generated)", re.I)


@dataclass
class Skipped:
    commit_sha: str
    path: str
    reason: str


@dataclass
class FilterResult:
    kept: list[FileDiff]
    skipped: list[Skipped]


def path_skip_reason(path: str) -> str | None:
    p = PurePosixPath(path)
    if p.name in LOCKFILES:
        return "lockfile"
    if p.name in JUNK_FILES:
        return "os-junk"
    if any(part in VENDORED_DIRS for part in p.parts[:-1]):
        return "vendored/build output"
    if path.endswith(GENERATED_SUFFIXES) or any(rx.search(path) for rx in GENERATED_PATTERNS):
        return "generated"
    if p.suffix.lower() in BINARY_SUFFIXES:
        return "binary"
    return None


def _changed_lines(patch: str) -> tuple[list[str], list[str]]:
    removed, added = [], []
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    return removed, added


def is_whitespace_only(patch: str) -> bool:
    """True if the patch only changes whitespace (including re-wrapping lines)."""
    removed, added = _changed_lines(patch)
    if not removed and not added:
        return False
    squash = lambda lines: re.sub(r"\s+", "", "".join(lines))  # noqa: E731
    return squash(removed) == squash(added)


def is_timestamp_only(patch: str) -> bool:
    lines = [ln for ln in patch.splitlines() if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    return bool(lines) and all(_TIMESTAMP_LINE.match(ln) for ln in lines)


def skip_reason(fd: FileDiff) -> str | None:
    if reason := path_skip_reason(fd.path):
        return reason
    if fd.is_binary:
        return "binary"
    if fd.change_type == "R" and not fd.diff.strip():
        return None  # pure rename: keep, it is meaningful and cheap
    if not fd.diff.strip():
        return "empty diff"
    if is_whitespace_only(fd.diff):
        return "whitespace-only"
    if "migration" in fd.path.lower() and is_timestamp_only(fd.diff):
        return "timestamp-only"
    return None


def truncate_diff(patch: str, max_chars: int) -> str:
    """Keep whole hunks from the start of the patch until `max_chars` is reached."""
    if len(patch) <= max_chars:
        return patch
    hunks = re.split(r"(?m)^(?=@@ )", patch)
    kept, size = [], 0
    for hunk in hunks:
        if size + len(hunk) > max_chars:
            break
        kept.append(hunk)
        size += len(hunk)
    if not kept:  # a single hunk larger than the budget: hard cut on a line boundary
        cut = patch[:max_chars]
        kept = [cut[: cut.rfind("\n") + 1] or cut]
        size = len(kept[0])
    dropped_lines = patch[size:].count("\n")
    return "".join(kept) + f"\n[... diff truncated: {dropped_lines} more lines not shown ...]\n"


def filter_diffs(diffs: list[FileDiff], max_diff_chars: int) -> FilterResult:
    kept: list[FileDiff] = []
    skipped: list[Skipped] = []
    for fd in diffs:
        if reason := skip_reason(fd):
            skipped.append(Skipped(fd.commit_sha, fd.path, reason))
        else:
            kept.append(replace(fd, diff=truncate_diff(fd.diff, max_diff_chars)))
    return FilterResult(kept=kept, skipped=skipped)
