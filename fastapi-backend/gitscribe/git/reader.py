"""Read commits, per-file diffs and batch groupings from a git repository."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import git

BatchBy = Literal["pr", "tag", "week"]

UNRELEASED = "Unreleased"

# Consecutive direct (non-merge) commits on the main line are grouped into one
# batch of at most this many commits when batching by PR.
MAX_DIRECT_COMMITS_PER_BATCH = 10


@dataclass
class CommitInfo:
    sha: str
    author: str
    date: str  # ISO 8601, UTC
    message: str
    parents: list[str]

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def subject(self) -> str:
        return self.message.splitlines()[0] if self.message else ""


@dataclass
class FileDiff:
    commit_sha: str
    path: str
    old_path: str | None
    change_type: Literal["A", "M", "D", "R"]
    diff: str
    is_binary: bool
    additions: int
    deletions: int


@dataclass
class Batch:
    id: str
    label: str
    commit_shas: list[str]
    section: str = UNRELEASED  # release (tag) the batch belongs to
    date: str = ""  # date of the newest commit in the batch


@dataclass
class Section:
    label: str
    date: str
    order: int  # 0 = oldest
    commit_shas: set[str] = field(default_factory=set)


def open_repo(path: str) -> git.Repo:
    return git.Repo(path, search_parent_directories=False)


def _to_info(c: git.Commit) -> CommitInfo:
    return CommitInfo(
        sha=c.hexsha,
        author=c.author.name or "",
        date=c.committed_datetime.astimezone(timezone.utc).isoformat(),
        message=c.message.strip() if isinstance(c.message, str) else c.message.decode(errors="replace").strip(),
        parents=[p.hexsha for p in c.parents],
    )


def read_commits(repo: git.Repo, since_sha: str | None = None, rev: str = "HEAD") -> list[CommitInfo]:
    """Commits reachable from `rev` (excluding those reachable from `since_sha`), oldest first."""
    rev_range = f"{since_sha}..{rev}" if since_sha else rev
    commits = list(repo.iter_commits(rev_range, topo_order=True, reverse=True))
    return [_to_info(c) for c in commits]


def _empty_tree(repo: git.Repo) -> git.Tree:
    return repo.tree(repo.git.hash_object("-t", "tree", "/dev/null"))


def _count_lines(patch: str) -> tuple[int, int]:
    adds = dels = 0
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            adds += 1
        elif line.startswith("-") and not line.startswith("---"):
            dels += 1
    return adds, dels


def file_diffs(repo: git.Repo, sha: str) -> list[FileDiff]:
    """Per-file diffs of a commit against its first parent.

    Merge commits return an empty list: their changes are already covered by
    the commits on the merged branch.
    """
    commit = repo.commit(sha)
    if len(commit.parents) > 1:
        return []
    base = commit.parents[0] if commit.parents else _empty_tree(repo)
    out: list[FileDiff] = []
    for d in base.diff(commit, create_patch=True, M=True):
        raw = d.diff if isinstance(d.diff, bytes) else (d.diff or "").encode()
        is_binary = raw.startswith(b"Binary files") or b"\x00" in raw
        patch = "" if is_binary else raw.decode("utf-8", errors="replace")
        if d.new_file:
            change_type = "A"
        elif d.deleted_file:
            change_type = "D"
        elif d.renamed_file:
            change_type = "R"
        else:
            change_type = "M"
        adds, dels = _count_lines(patch)
        out.append(
            FileDiff(
                commit_sha=commit.hexsha,
                path=d.b_path or d.a_path,
                old_path=d.a_path if change_type == "R" else None,
                change_type=change_type,
                diff=patch,
                is_binary=is_binary,
                additions=adds,
                deletions=dels,
            )
        )
    return out


# --- sections (releases) ----------------------------------------------------


def tag_sections(repo: git.Repo, commits: list[CommitInfo]) -> tuple[dict[str, str], list[Section]]:
    """Assign each commit to the earliest tag that contains it, or UNRELEASED.

    Returns (sha -> section label, sections ordered oldest first).
    """
    wanted = {c.sha for c in commits}
    by_sha = {c.sha: c for c in commits}
    tags = sorted(
        (t for t in repo.tags if isinstance(t.commit, git.Commit)),
        key=lambda t: t.commit.committed_datetime,
    )
    section_of: dict[str, str] = {}
    sections: list[Section] = []
    for tag in tags:
        reachable = {c.hexsha for c in repo.iter_commits(tag.commit)}
        members = {s for s in (reachable & wanted) if s not in section_of}
        if not members:
            continue
        for s in members:
            section_of[s] = tag.name
        sections.append(
            Section(
                label=tag.name,
                date=tag.commit.committed_datetime.astimezone(timezone.utc).date().isoformat(),
                order=len(sections),
                commit_shas=members,
            )
        )
    rest = {s for s in wanted if s not in section_of}
    if rest:
        for s in rest:
            section_of[s] = UNRELEASED
        newest = max(by_sha[s].date for s in rest)
        sections.append(Section(label=UNRELEASED, date=newest[:10], order=len(sections), commit_shas=rest))
    return section_of, sections


# --- batching ---------------------------------------------------------------


def _first_parent_line(repo: git.Repo, commits: list[CommitInfo], rev: str) -> list[str]:
    wanted = {c.sha for c in commits}
    line = [c.hexsha for c in repo.iter_commits(rev, first_parent=True)]
    return [s for s in reversed(line) if s in wanted]


def _batches_by_pr(repo: git.Repo, commits: list[CommitInfo], rev: str, section_of: dict[str, str]) -> list[Batch]:
    by_sha = {c.sha: c for c in commits}
    batches: list[Batch] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        first, last = by_sha[pending[0]], by_sha[pending[-1]]
        label = first.subject if len(pending) == 1 else f"{len(pending)} commits: {first.subject} … {last.subject}"
        batches.append(Batch(id=f"direct-{pending[0][:12]}", label=label, commit_shas=list(pending)))
        pending.clear()

    for sha in _first_parent_line(repo, commits, rev):
        info = by_sha[sha]
        if not info.is_merge:
            # Direct commits are grouped, but never across a release boundary.
            if pending and section_of[pending[-1]] != section_of[sha]:
                flush()
            pending.append(sha)
            if len(pending) >= MAX_DIRECT_COMMITS_PER_BATCH:
                flush()
            continue
        flush()
        # Commits brought in by the merge: reachable from the merged branch tip
        # but not from the main line before the merge.
        merged = [
            c.hexsha
            for c in repo.iter_commits(f"{info.parents[0]}..{info.parents[1]}", topo_order=True, reverse=True)
            if c.hexsha in by_sha
        ]
        batches.append(Batch(id=f"merge-{sha[:12]}", label=info.subject, commit_shas=merged + [sha]))
    flush()
    return batches


def _batches_by_week(commits: list[CommitInfo]) -> list[Batch]:
    groups: dict[str, list[str]] = {}
    for c in commits:
        year, week, _ = datetime.fromisoformat(c.date).isocalendar()
        groups.setdefault(f"{year}-W{week:02d}", []).append(c.sha)
    return [Batch(id=f"week-{k}", label=f"Week {k}", commit_shas=v) for k, v in sorted(groups.items())]


def _batches_by_tag(sections: list[Section], commits: list[CommitInfo]) -> list[Batch]:
    order = {c.sha: i for i, c in enumerate(commits)}
    return [
        Batch(id=f"tag-{s.label}", label=s.label, commit_shas=sorted(s.commit_shas, key=order.__getitem__))
        for s in sections
    ]


def make_batches(
    repo: git.Repo,
    commits: list[CommitInfo],
    batch_by: BatchBy = "pr",
    rev: str = "HEAD",
) -> tuple[list[Batch], list[Section]]:
    """Group commits into batches and tag each batch with its release section."""
    if not commits:
        return [], []
    section_of, sections = tag_sections(repo, commits)
    if batch_by == "pr":
        batches = _batches_by_pr(repo, commits, rev, section_of)
    elif batch_by == "week":
        batches = _batches_by_week(commits)
    elif batch_by == "tag":
        batches = _batches_by_tag(sections, commits)
    else:
        raise ValueError(f"unknown batch_by: {batch_by}")

    by_sha = {c.sha: c for c in commits}
    section_order = {s.label: s.order for s in sections}
    for b in batches:
        # A batch belongs to the latest release any of its commits landed in.
        b.section = max((section_of[s] for s in b.commit_shas), key=section_order.__getitem__)
        b.date = max(by_sha[s].date for s in b.commit_shas)
    return batches, sections
