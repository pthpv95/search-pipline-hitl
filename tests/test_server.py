from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import api_runtime
import server
from state import GraphStatus, SynthesisDraft


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_runtime, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(server, "RUNS_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("TRIAL_LIMIT", "999")
    monkeypatch.delenv("API_KEYS", raising=False)
    # Clean up trial tracking file created during tests
    trial_file = tmp_path / ".trials.json"
    monkeypatch.setenv("TRIAL_DATA_FILE", str(trial_file))
    server.REGISTRY._sessions.clear()
    with TestClient(server.app) as test_client:
        yield test_client
    server.REGISTRY._sessions.clear()


def wait_for(client: TestClient, run_id: str, predicate, timeout: float = 5.0):
    start = time.time()
    while time.time() - start < timeout:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        detail = response.json()
        if predicate(detail):
            return detail
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for run {run_id}")


def create_paused_run(client: TestClient, *, max_loops: int = 1) -> dict:
    response = client.post(
        "/api/runs",
        json={
            "topic": "web console integration test",
            "mode": "dev",
            "report_format": "deep_dive",
            "max_loops": max_loops,
        },
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    return wait_for(client, run_id, lambda detail: detail["review"]["is_pending"])


def test_create_run_reaches_review_and_detail_is_complete(client: TestClient):
    detail = create_paused_run(client)

    assert detail["summary"]["phase"] == "paused_interrupt"
    assert detail["pipeline"]["current_node"] == "human_review"
    assert detail["review"]["payload"]["topic"] == "web console integration test"
    assert detail["draft"]["source_kind"] == "synthesis_draft"


def test_approve_review_completes_and_saves_artifact(client: TestClient):
    detail = create_paused_run(client)
    run_id = detail["summary"]["id"]

    review = client.post(f"/api/runs/{run_id}/review", json={"action": "approve"})
    assert review.status_code == 200

    completed = wait_for(client, run_id, lambda item: item["summary"]["phase"] == "done" and item["summary"]["artifact_available"])
    assert completed["draft"]["source_kind"] == "final_report"
    assert completed["summary"]["artifact_available"] is True

    artifact_response = client.get(f"/api/runs/{run_id}/artifact")
    assert artifact_response.status_code == 200
    assert "web console integration test" in artifact_response.text


def test_edit_review_flows_into_final_report(client: TestClient):
    detail = create_paused_run(client)
    run_id = detail["summary"]["id"]

    edited = "Edited reviewer draft for browser integration."
    review = client.post(
        f"/api/runs/{run_id}/review",
        json={"action": "edit", "edited_draft": edited},
    )
    assert review.status_code == 200

    completed = wait_for(client, run_id, lambda item: item["summary"]["phase"] == "done")
    assert edited in completed["draft"]["text"]


def test_reject_review_terminates_run(client: TestClient):
    detail = create_paused_run(client)
    run_id = detail["summary"]["id"]

    review = client.post(
        f"/api/runs/{run_id}/review",
        json={"action": "reject", "rejection_reason": "Off-topic"},
    )
    assert review.status_code == 200

    rejected = wait_for(client, run_id, lambda item: item["summary"]["phase"] == "rejected")
    assert rejected["raw_state_meta"]["error"] == "Off-topic"
    assert rejected["draft"]["source_kind"] == "synthesis_draft"


def test_additional_queries_resume_and_pause_again(client: TestClient, monkeypatch):
    def fake_synthesis(state, config=None):
        return {
            "synthesis_draft": SynthesisDraft(
                draft=f"Draft after loop {state.loop_count}",
                remaining_gaps=[],
                confidence=0.8,
                needs_more_search=False,
                follow_up_queries=[],
                limitations=[],
            ),
            "current_queries": [],
            "status": GraphStatus.AWAITING_HUMAN,
            "token_usage": state.token_usage,
            "node_timings": state.node_timings,
        }

    monkeypatch.setattr(api_runtime, "run_synthesis_agent", fake_synthesis)

    detail = create_paused_run(client, max_loops=3)
    run_id = detail["summary"]["id"]

    review = client.post(
        f"/api/runs/{run_id}/review",
        json={"action": "approve", "additional_queries": ["extra angle"]},
    )
    assert review.status_code == 200

    paused_again = wait_for(
        client,
        run_id,
        lambda item: item["summary"]["phase"] == "paused_interrupt" and item["pipeline"]["loop_count"] == 2,
    )
    assert paused_again["review"]["payload"]["loop_count"] == 2


def test_runs_list_merges_sessions_and_artifacts(client: TestClient):
    paused = create_paused_run(client)
    active_id = paused["summary"]["id"]

    complete = client.post(f"/api/runs/{active_id}/review", json={"action": "approve"})
    assert complete.status_code == 200
    wait_for(client, active_id, lambda item: item["summary"]["phase"] == "done")

    second = create_paused_run(client)
    second_id = second["summary"]["id"]

    response = client.get("/api/runs")
    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload}
    assert active_id in ids
    assert second_id in ids


def test_sse_endpoint_replays_snapshot_and_journal(client: TestClient):
    detail = create_paused_run(client)
    run_id = detail["summary"]["id"]

    response = server.stream_run_events(run_id)
    iterator = response.body_iterator
    chunks = asyncio.run(_take_async_chunks(iterator, 3))
    joined = "".join(chunks)
    assert "event: run.phase_changed" in joined
    assert "event: run.created" in joined or "event: review.required" in joined


# ---------------------------------------------------------------------------
# Trial gating
# ---------------------------------------------------------------------------

@pytest.fixture
def trial_client(tmp_path, monkeypatch):
    """TestClient with TRIAL_LIMIT=2 and fresh trial data."""
    monkeypatch.setattr(api_runtime, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(server, "RUNS_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("TRIAL_LIMIT", "2")
    trial_file = tmp_path / ".trials.json"
    monkeypatch.setenv("TRIAL_DATA_FILE", str(trial_file))
    server.REGISTRY._sessions.clear()
    with TestClient(server.app) as test_client:
        yield test_client
    server.REGISTRY._sessions.clear()


def _create(tc: TestClient, max_loops: int = 1):
    return tc.post(
        "/api/runs",
        json={"topic": "trial test", "mode": "dev", "report_format": "deep_dive", "max_loops": max_loops},
    )


def test_health_reports_trial_remaining(trial_client: TestClient):
    resp = trial_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False
    assert data["trial_remaining"] == 2


def test_can_create_run_within_trial_limit(trial_client: TestClient):
    r1 = _create(trial_client)
    assert r1.status_code == 200
    assert r1.json()["trial_remaining"] == 1

    r2 = _create(trial_client)
    assert r2.status_code == 200
    assert r2.json()["trial_remaining"] == 0


def test_trial_exhausted_returns_403(trial_client: TestClient):
    _create(trial_client)  # trial 1
    _create(trial_client)  # trial 2

    r3 = _create(trial_client)  # should be blocked
    assert r3.status_code == 403
    detail = r3.json()
    assert detail["code"] == "trial_exhausted"
    assert detail["trial_remaining"] == 0


def test_valid_api_key_bypasses_trials(trial_client: TestClient, monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret-key")
    # Exhaust trials first
    _create(trial_client)
    _create(trial_client)

    # With valid API key — should pass
    resp = trial_client.post(
        "/api/runs",
        json={"topic": "with key", "mode": "dev", "report_format": "deep_dive", "max_loops": 1},
        headers={"X-API-Key": "secret-key"},
    )
    assert resp.status_code == 200
    assert resp.json().get("trial_remaining") is None  # no trial consumed

    # Invalid API key with no trials left — blocked
    resp2 = trial_client.post(
        "/api/runs",
        json={"topic": "bad key", "mode": "dev", "report_format": "deep_dive", "max_loops": 1},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp2.status_code == 403


async def _take_async_chunks(iterator, count: int) -> list[str]:
    chunks = []
    for _ in range(count):
        chunks.append(await anext(iterator))
    return chunks
