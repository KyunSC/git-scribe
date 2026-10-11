"""GitHub links and branch/PR selection, with a local repo standing in for github.com."""

import time

import pytest
from fastapi.testclient import TestClient

from gitscribe.api.app import create_app
from gitscribe.git import github


@pytest.mark.parametrize(
    "text, expected",
    [
        ("https://github.com/acme/widgets", ("acme", "widgets", None, None)),
        ("github.com/acme/widgets.git", ("acme", "widgets", None, None)),
        ("git@github.com:acme/widgets.git", ("acme", "widgets", None, None)),
        ("https://github.com/acme/widgets.js/", ("acme", "widgets.js", None, None)),
        ("https://github.com/acme/widgets/tree/feature/login", ("acme", "widgets", "feature/login", None)),
        ("https://github.com/acme/widgets/pull/42/files?w=1", ("acme", "widgets", None, 42)),
        ("https://github.com/acme/widgets?tab=readme", ("acme", "widgets", None, None)),
    ],
)
def test_parse_url(text, expected):
    gh = github.parse_url(text)
    assert (gh.owner, gh.name, gh.branch_hint, gh.pr_hint) == expected


@pytest.mark.parametrize("text", ["/home/me/repo", "~/code/widgets", "https://gitlab.com/acme/widgets", "acme/widgets"])
def test_parse_url_rejects_non_github(text):
    assert github.parse_url(text) is None


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def remote(small_repo, monkeypatch):
    """small_repo as github.com/acme/repo: main, a `feature` branch, and PR #3 from it."""
    fork = small_repo.head()
    small_repo.git("checkout", "-q", "-b", "feature")
    small_repo.write("app/feature.py", "def feature():\n    return 3\n")
    small_repo.commit("Add feature", "2026-01-07T10:00:00+00:00")
    small_repo.git("update-ref", "refs/pull/3/head", "feature")
    small_repo.git("checkout", "-q", "main")
    small_repo.write("app/later.py", "X = 1\n")
    small_repo.commit("Later main work", "2026-01-08T10:00:00+00:00")

    monkeypatch.setattr(github, "clone_url", lambda repo: str(small_repo.path))
    pull = github.PullInfo(number=3, title="Add feature", base="main", head="acme:feature", author="dev", state="open")
    monkeypatch.setattr(github, "get_pull", lambda repo, n: pull)
    monkeypatch.setattr(
        github,
        "list_refs",
        lambda repo: github.RepoRefs(default_branch="main", branches=["main", "feature"], pulls=[pull]),
    )
    small_repo.fork = fork
    return small_repo


def run_to_end(client, tmp_path, **body):
    resp = client.post("/api/runs", json={"out_dir": str(tmp_path / "out"), **body})
    assert resp.status_code == 201, resp.text
    run = resp.json()
    deadline = time.monotonic() + 15
    while client.get(f"/api/runs/{run['run_id']}").json()["status"] == "running":
        assert time.monotonic() < deadline
        time.sleep(0.05)
    result = client.get(f"/api/runs/{run['run_id']}/result").json()
    assert result["run"]["status"] == "done", result["run"]["error"]
    return run, result


def test_github_refs(client, remote):
    refs = client.get("/api/refs", params={"repo": "https://github.com/acme/repo"}).json()
    assert refs["kind"] == "github"
    assert refs["repo_name"] == "acme/repo"
    assert refs["branches"] == ["main", "feature"]
    assert [p["number"] for p in refs["pulls"]] == [3]
    assert (refs["branch"], refs["pr"]) == ("main", None)

    linked = client.get("/api/refs", params={"repo": "https://github.com/acme/repo/tree/feature/app"}).json()
    assert linked["branch"] == "feature"

    linked = client.get("/api/refs", params={"repo": "https://github.com/acme/repo/pull/3"}).json()
    assert (linked["branch"], linked["pr"]) == (None, 3)


def test_github_default_branch_run(client, remote, stub, tmp_path):
    run, result = run_to_end(client, tmp_path, repo="https://github.com/acme/repo")
    assert (run["repo_name"], run["ref"], run["source"]) == ("acme/repo", "main", "https://github.com/acme/repo")
    assert run["repo_path"].startswith(str(tmp_path / "repos"))
    assert result["commit_count"] == 3  # main only: not the feature commit


def test_github_branch_run(client, remote, stub, tmp_path):
    run, result = run_to_end(client, tmp_path, repo="https://github.com/acme/repo", branch="feature")
    assert run["ref"] == "feature"
    assert result["commit_count"] == 3  # Initial commit, Add helper, Add feature


def test_github_pr_run_covers_only_its_commits(client, remote, stub, tmp_path):
    run, result = run_to_end(client, tmp_path, repo="https://github.com/acme/repo/pull/3")
    assert (run["ref"], run["ref_title"]) == ("#3", "Add feature")
    assert result["commit_count"] == 1
    assert [a["path"] for a in result["analyses"]] == ["app/feature.py"]


def test_github_missing_branch(client, remote):
    resp = client.post("/api/runs", json={"repo": "https://github.com/acme/repo", "branch": "nope"})
    assert resp.status_code == 400
    assert "branch 'nope' not found" in resp.json()["detail"]


def test_branch_and_pr_are_exclusive(client):
    resp = client.post("/api/runs", json={"repo": "https://github.com/acme/repo", "branch": "main", "pr": 1})
    assert resp.status_code == 422


def test_local_refs_and_branch_run(client, remote, stub, tmp_path):
    refs = client.get("/api/refs", params={"repo": str(remote.path)}).json()
    assert refs["kind"] == "local"
    assert refs["branches"] == ["main", "feature"]
    assert (refs["branch"], refs["pulls"]) == ("main", [])

    run, result = run_to_end(client, tmp_path, repo=str(remote.path), branch="feature")
    assert (run["ref"], run["source"], run["repo_name"]) == ("feature", None, "repo")
    assert result["commit_count"] == 3

    resp = client.post("/api/runs", json={"repo": str(remote.path), "pr": 3})
    assert resp.status_code == 400
    resp = client.post("/api/runs", json={"repo": str(remote.path), "branch": "nope"})
    assert resp.status_code == 400
