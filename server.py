"""
FastAPI bridge for the browser-based research console.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from api_adapters import artifact_to_detail, artifact_to_summary, session_to_detail, session_to_summary
from api_models import CreateRunRequest, ErrorResponse, ReviewDecisionRequest
from api_runtime import (
    RUNS_DIR,
    SessionRegistry,
    create_session,
    find_artifact_path,
    resume_after_review,
    run_session_in_background,
)
from auth.trials import consume_trial, trials_remaining, validate_api_key
from config import AppConfig

app = FastAPI(title="Research Console API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REGISTRY = SessionRegistry()


def _check_trial_or_auth(request: Request, x_api_key: str | None = Header(default=None)) -> str | None:
    """FastAPI dependency.  Raises 403 if no valid API key and no trials left.

    Returns the client IP when using a trial (so the caller knows to consume it),
    or None when authenticated via API key.
    """
    if validate_api_key(x_api_key):
        return None  # authenticated

    ip = request.client.host if request.client else "unknown"
    remaining = trials_remaining(ip)
    if remaining <= 0:
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Trial limit reached — no free runs remaining. Set API_KEYS in your env and pass X-API-Key header to continue.",
                "code": "trial_exhausted",
                "retryable": False,
                "trial_remaining": 0,
                "setup_hint": "export API_KEYS=your-key-here",
            },
        )
    return ip  # on trial — caller must consume


def api_error(status_code: int, detail: str, code: str, retryable: bool = False) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "code": code,
            "retryable": retryable,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail), "code": "http_error", "retryable": False}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.get("/api/health")
def health(request: Request, x_api_key: str | None = Header(default=None)) -> dict:
    ip = request.client.host if request.client else "unknown"
    authenticated = validate_api_key(x_api_key)
    return {
        "ok": True,
        "active_run_count": REGISTRY.active_count(),
        "persistence": "runs_dir_only",
        "durable_resume": False,
        "authenticated": authenticated,
        "trial_remaining": trials_remaining(ip) if not authenticated else None,
    }


@app.get("/api/runs")
def list_runs(include: str = Query(default="active,completed"), limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    include_parts = {part.strip() for part in include.split(",") if part.strip()}
    results: list[dict] = []
    used_artifacts: set[str] = set()

    if "active" in include_parts:
        sessions = sorted(REGISTRY.all(), key=lambda session: session.updated_at, reverse=True)
        for session in sessions:
            results.append(session_to_summary(session))
            if session.artifact_path:
                used_artifacts.add(str(session.artifact_path.resolve()))

    if "completed" in include_parts:
        artifact_rows: list[dict] = []
        for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
            if str(path.resolve()) in used_artifacts:
                continue
            artifact_rows.append(artifact_to_summary(path))
        results.extend(artifact_rows)

    return results[:limit]


@app.post("/api/runs")
def create_run(payload: CreateRunRequest, request: Request, x_api_key: str | None = Header(default=None)) -> dict:
    ip = _check_trial_or_auth(request, x_api_key)

    cfg = AppConfig.from_env(
        mode=payload.mode,
        report_format=payload.report_format,
        max_loops=payload.max_loops,
    )
    session = create_session(payload.model_dump(mode="python"), cfg)
    REGISTRY.add(session)
    run_session_in_background(session)

    # Consume trial if not authenticated
    if ip is not None:
        consume_trial(ip)

    return {
        "run_id": session.run_id,
        "stream_url": f"/api/runs/{session.run_id}/events",
        "detail_url": f"/api/runs/{session.run_id}",
        "trial_remaining": trials_remaining(ip) if ip is not None else None,
    }


@app.get("/api/runs/{run_id}")
def get_run_detail(run_id: str) -> dict:
    session = REGISTRY.get(run_id)
    if session:
        return session_to_detail(session)

    path = find_artifact_path(run_id)
    if path:
        return artifact_to_detail(path)

    raise api_error(404, f"unknown run: {run_id}", "run_not_found")


@app.get("/api/runs/{run_id}/artifact")
def get_artifact(run_id: str):
    session = REGISTRY.get(run_id)
    if session and session.artifact_path:
        return FileResponse(session.artifact_path, media_type="application/json", filename=session.artifact_path.name)

    path = find_artifact_path(run_id)
    if path:
        return FileResponse(path, media_type="application/json", filename=path.name)

    raise api_error(404, f"artifact not found for run: {run_id}", "artifact_not_found")


@app.post("/api/runs/{run_id}/review")
def submit_review(run_id: str, payload: ReviewDecisionRequest) -> dict:
    session = REGISTRY.get(run_id)
    if not session:
        raise api_error(404, f"unknown run: {run_id}", "run_not_found")
    try:
        human_input = payload.to_human_input()
    except ValueError as exc:
        raise api_error(422, str(exc), "invalid_review_payload") from exc

    try:
        resume_after_review(session, human_input)
    except RuntimeError as exc:
        raise api_error(409, str(exc), "review_not_pending") from exc

    return {
        "accepted": True,
        "summary": session_to_summary(session),
    }


@app.get("/api/runs/{run_id}/events")
def stream_run_events(run_id: str):
    session = REGISTRY.get(run_id)
    if not session:
        raise api_error(404, f"unknown run: {run_id}", "run_not_found")

    def event_stream():
        index = 0
        first_snapshot = {
            "event_id": f"{session.run_id}:snapshot",
            "run_id": session.run_id,
            "ts": session.updated_at,
            "type": "run.phase_changed",
            "snapshot_version": session.snapshot_version,
            "data": {"snapshot": session.snapshot()},
        }
        yield _encode_sse(first_snapshot)
        heartbeat_at = time.monotonic()
        while True:
            journal = list(session.event_journal)
            while index < len(journal):
                yield _encode_sse(journal[index])
                index += 1

            now = time.monotonic()
            if now - heartbeat_at >= 15:
                heartbeat_at = now
                heartbeat = {
                    "event_id": f"{session.run_id}:heartbeat:{int(now)}",
                    "run_id": session.run_id,
                    "ts": session.updated_at,
                    "type": "heartbeat",
                    "snapshot_version": session.snapshot_version,
                    "data": {"snapshot": session.snapshot()},
                }
                yield _encode_sse(heartbeat)

            if session.artifact_path and session.phase in {"done", "rejected", "failed"} and index >= len(journal):
                return
            time.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _encode_sse(event: dict) -> str:
    return f"id: {event['event_id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
