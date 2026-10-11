"""GitHub repositories: parse links, list branches and pull requests, fetch into a local cache.

Remote repos are kept as bare clones under `REPOS_DIR/<owner>/<name>`. Each run
fetches only what it needs (one branch, or a PR's head plus its base branch);
tags pointing into that history come along automatically.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

import git
import httpx

from gitscribe.config import get_settings

API_URL = "https://api.github.com"
MAX_BRANCH_PAGES = 5  # 100 branches per page
MAX_PULLS = 100
GIT_TIMEOUT_SECONDS = 600

_URL_RE = re.compile(
    r"""^(?:
        (?:https?://)?(?:www\.)?github\.com/  # https://github.com/owner/name
        | git@github\.com:                     # git@github.com:owner/name.git
    )
    (?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?
    (?:/(?P<rest>.*))?$""",
    re.VERBOSE,
)


class GitHubError(Exception):
    """A GitHub API or fetch failure, with a message fit to show the user."""


@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    name: str
    # Optional ref named by the link itself: .../tree/<branch> or .../pull/<n>
    branch_hint: str | None = None
    pr_hint: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.full_name}"


@dataclass
class PullInfo:
    number: int
    title: str
    base: str
    head: str
    author: str
    state: str  # open | closed | merged
    draft: bool = False


@dataclass
class RepoRefs:
    default_branch: str
    branches: list[str]
    pulls: list[PullInfo] = field(default_factory=list)


@dataclass
class Checkout:
    """A fetched revision range, ready for the pipeline."""

    path: str  # local bare clone
    rev: str  # sha to read history from
    since_sha: str | None  # exclude history reachable from here (a PR's fork point)
    ref: str  # branch name or "#<n>"
    ref_title: str | None = None  # PR title


def parse_url(text: str) -> GitHubRepo | None:
    """A GitHub repo link, or None if `text` is not one."""
    m = _URL_RE.match(re.split(r"[?#]", text.strip(), maxsplit=1)[0])
    if not m:
        return None
    rest = (m["rest"] or "").strip("/")
    branch = pr = None
    if rest.startswith("tree/"):
        branch = rest[len("tree/") :] or None
    elif pm := re.match(r"pulls?/(\d+)", rest):
        pr = int(pm[1])
    return GitHubRepo(m["owner"], m["name"], branch_hint=branch, pr_hint=pr)


# --- API --------------------------------------------------------------------


def _client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token := get_settings().github_token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_URL, headers=headers, timeout=20, follow_redirects=True)


def _check(resp: httpx.Response, what: str) -> None:
    if resp.is_success:
        return
    if resp.status_code == 404:
        hint = "" if get_settings().github_token else " (set GITHUB_TOKEN for private repositories)"
        raise GitHubError(f"{what} not found on GitHub{hint}")
    if resp.status_code in (403, 429) and resp.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubError("GitHub API rate limit reached; set GITHUB_TOKEN to raise it")
    try:
        message = resp.json().get("message", resp.reason_phrase)
    except ValueError:
        message = resp.reason_phrase
    raise GitHubError(f"GitHub API error for {what}: {resp.status_code} {message}")


def _pull_info(p: dict) -> PullInfo:
    state = "merged" if p.get("merged_at") else p["state"]
    return PullInfo(
        number=p["number"],
        title=p["title"],
        base=p["base"]["ref"],
        head=p["head"]["label"],
        author=(p.get("user") or {}).get("login", ""),
        state=state,
        draft=bool(p.get("draft")),
    )


def list_refs(repo: GitHubRepo) -> RepoRefs:
    """Default branch, branches (default first) and open pull requests, newest first."""
    try:
        with _client() as c:
            resp = c.get(f"/repos/{repo.full_name}")
            _check(resp, repo.full_name)
            default = resp.json()["default_branch"]

            branches: list[str] = []
            url: str | None = f"/repos/{repo.full_name}/branches?per_page=100"
            for _ in range(MAX_BRANCH_PAGES):
                if url is None:
                    break
                resp = c.get(url)
                _check(resp, f"branches of {repo.full_name}")
                branches += [b["name"] for b in resp.json()]
                url = resp.links.get("next", {}).get("url")

            resp = c.get(f"/repos/{repo.full_name}/pulls", params={"state": "open", "per_page": MAX_PULLS})
            _check(resp, f"pull requests of {repo.full_name}")
            pulls = [_pull_info(p) for p in resp.json()]
    except httpx.HTTPError as e:
        raise GitHubError(f"could not reach GitHub: {e}") from e
    branches = [default] + sorted((b for b in branches if b != default), key=str.lower)
    return RepoRefs(default_branch=default, branches=branches, pulls=pulls)


def get_pull(repo: GitHubRepo, number: int) -> PullInfo:
    try:
        with _client() as c:
            resp = c.get(f"/repos/{repo.full_name}/pulls/{number}")
    except httpx.HTTPError as e:
        raise GitHubError(f"could not reach GitHub: {e}") from e
    _check(resp, f"pull request #{number} of {repo.full_name}")
    return _pull_info(resp.json())


# --- fetching ---------------------------------------------------------------

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(path), threading.Lock())


def clone_url(repo: GitHubRepo) -> str:
    return f"https://github.com/{repo.full_name}.git"


def cache_path(repo: GitHubRepo) -> Path:
    # GitHub names are case-insensitive: one clone per repo however it was typed.
    return (Path(get_settings().repos_dir).expanduser() / repo.owner.lower() / repo.name.lower()).resolve()


def _git_env() -> dict[str, str]:
    """Never prompt for credentials; pass a token as a header so it is not stored in the clone's config."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token := get_settings().github_token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env |= {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        }
    return env


def _git(cwd: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise GitHubError(f"git {args[0]} timed out") from e
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}"
        raise GitHubError(f"git {args[0]} failed: {detail}")
    return proc.stdout


def _ensure_clone(repo: GitHubRepo) -> Path:
    path = cache_path(repo)
    if not (path / "HEAD").exists():
        path.mkdir(parents=True, exist_ok=True)
        _git(path, "init", "-q", "--bare")
        _git(path, "remote", "add", "origin", clone_url(repo))
    return path


def _fetch(path: Path, *refs: str) -> None:
    """Fetch remote refs to the same names locally, e.g. refs/heads/main."""
    _git(path, "fetch", "-q", "--no-write-fetch-head", "origin", *(f"+{r}:{r}" for r in refs))


def _remote_default_branch(path: Path) -> str:
    out = _git(path, "ls-remote", "--symref", "origin", "HEAD")
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split()[1][len("refs/heads/") :]
    raise GitHubError("could not determine the repository's default branch")


def checkout(repo: GitHubRepo, branch: str | None = None, pr: int | None = None) -> Checkout:
    """Fetch a branch (default: the default branch) or a pull request into the local cache.

    A PR's range is its own commits: from its fork point off the base branch to its head.
    """
    if branch and pr:
        raise ValueError("choose a branch or a pull request, not both")
    path = cache_path(repo)
    with _lock_for(path):
        _ensure_clone(repo)
        bare = git.Repo(path)
        if pr is not None:
            info = get_pull(repo, pr)
            head_ref, base_ref = f"refs/pull/{pr}/head", f"refs/heads/{info.base}"
            _fetch(path, head_ref, base_ref)
            head, base = bare.commit(head_ref), bare.commit(base_ref)
            fork = bare.merge_base(base, head)
            return Checkout(
                path=str(path),
                rev=head.hexsha,
                since_sha=fork[0].hexsha if fork else None,
                ref=f"#{pr}",
                ref_title=info.title,
            )
        branch = branch or _remote_default_branch(path)
        try:
            _fetch(path, f"refs/heads/{branch}")
        except GitHubError as e:
            raise GitHubError(f"branch {branch!r} not found in {repo.full_name}: {e}") from e
        return Checkout(path=str(path), rev=bare.commit(f"refs/heads/{branch}").hexsha, since_sha=None, ref=branch)
