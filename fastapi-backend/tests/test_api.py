"""HTTP API tests against the stub model, so no Ollama is needed."""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from gitscribe.api.app import create_app
from gitscribe.llm import factory


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def start(client, repo, tmp_path, **body):
    resp = client.post("/api/runs", json={"repo": str(repo.path), "out_dir": str(tmp_path / "out"), **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def wait_for(client, run_id, *statuses, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}: {run}")


def read_events(client, run_id):
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        kind = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                kind = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[len("data: ") :])))
    return events


def test_run_to_changelog(client, small_repo, stub, tmp_path):
    assert client.get("/api/health").json() == {"status": "ok"}
    run = start(client, small_repo, tmp_path)
    assert run["status"] == "running"
    assert run["repo_name"] == "repo"

    assert wait_for(client, run["run_id"], "done", "failed")["status"] == "done"
    result = client.get(f"/api/runs/{run['run_id']}/result").json()
    assert result["finished"] is True
    assert result["commit_count"] == 2
    assert (result["files_total"], result["batches_total"]) == (3, 2)
    assert sorted(s["label"] for s in result["changelog_sections"]) == ["Unreleased", "v1.0"]
    assert all("diff" not in a for a in result["analyses"])
    assert result["markdown"].startswith("# Changelog")

    md = client.get(f"/api/runs/{run['run_id']}/changelog.md")
    assert md.text.startswith("# Changelog")
    assert "attachment" in md.headers["content-disposition"]

    assert [r["run_id"] for r in client.get("/api/runs").json()] == [run["run_id"]]
    assert client.get("/api/runs/nope").status_code == 404


def test_bad_repo_path(client, tmp_path):
    resp = client.post("/api/runs", json={"repo": str(tmp_path / "missing")})
    assert resp.status_code == 400
    assert "not a git repository" in resp.json()["detail"]


def test_second_concurrent_run_conflicts(client, small_repo, stub, monkeypatch, tmp_path):
    release = threading.Event()

    def blocking(kind, schema):
        inner = stub(kind, schema)
        return RunnableLambda(lambda messages: release.wait(10) and inner.invoke(messages))

    monkeypatch.setattr(factory, "get_structured_model", blocking)
    run = start(client, small_repo, tmp_path)
    try:
        resp = client.post("/api/runs", json={"repo": str(small_repo.path)})
        assert resp.status_code == 409
    finally:
        release.set()
    assert wait_for(client, run["run_id"], "done", "failed")["status"] == "done"


def test_event_stream(client, small_repo, stub, tmp_path):
    run = start(client, small_repo, tmp_path)
    events = read_events(client, run["run_id"])
    kinds = [k for k, _ in events]

    assert kinds[0] == "status"
    assert kinds.count("file_analyzed") == 3
    assert "commits" in kinds and "batches" in kinds and "written" in kinds
    assert events[-1] == ("status", {"status": "done", "error": None})
    assert all("diff" not in data for _, data in events)

    # A run that is no longer live reports its status once and closes.
    replay = read_events(TestClient(create_app()), run["run_id"])
    assert replay == [("status", {"status": "done", "error": None})]


def test_resume_failed_run(client, small_repo, stub, tmp_path):
    stub.fail_next = {"BatchSummary"}
    run = start(client, small_repo, tmp_path)
    failed = wait_for(client, run["run_id"], "done", "failed")
    assert failed["status"] == "failed"
    assert "simulated crash" in failed["error"]
    assert client.get(f"/api/runs/{run['run_id']}/result").json()["finished"] is False

    resp = client.post(f"/api/runs/{run['run_id']}/resume")
    assert resp.status_code == 200, resp.text
    assert wait_for(client, run["run_id"], "done", "failed")["status"] == "done"
    assert stub.calls["FileChange"] == 3  # layer 1 not re-run

    resp = client.post(f"/api/runs/{run['run_id']}/resume")
    assert resp.status_code == 400  # done runs cannot resume
