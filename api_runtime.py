"""
In-memory runtime for browser-managed research runs.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.human_review import build_review_payload, parse_review_input
from agents.report import run_report_agent
from agents.search import run_search_agent
from agents.synthesis import run_synthesis_agent
from config import AppConfig
from evals.eval import evaluate_run
from run_pipeline import RUNS_DIR, save_run
from state import GraphStatus, ResearchState, RunMetadata

NODE_ORDER = ["search_agent", "synthesis_agent", "human_review", "report_agent"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_state_update(state: ResearchState, update: dict[str, Any]) -> ResearchState:
    return state.model_copy(update=update)


def is_terminal_phase(phase: str) -> bool:
    return phase in {"done", "rejected", "failed"}


@dataclass
class RunSession:
    run_id: str
    thread_id: str
    input_payload: dict[str, Any]
    state: ResearchState
    config: AppConfig
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    phase: str = "initializing"
    current_node: str | None = None
    review_payload: dict[str, Any] | None = None
    artifact_path: Path | None = None
    error: str | None = None
    snapshot_version: int = 0
    event_seq: int = 0
    event_journal: list[dict[str, Any]] = field(default_factory=list)
    log_entries: list[dict[str, Any]] = field(default_factory=list)
    loop_history: list[str] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def add_log(self, level: str, message: str, node: str | None = None) -> None:
        with self.lock:
            self.log_entries.append(
                {
                    "id": f"log-{len(self.log_entries) + 1}",
                    "t": utc_now(),
                    "node": node,
                    "level": level,
                    "msg": message,
                }
            )
            self.updated_at = utc_now()

    def append_event(self, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock:
            self.event_seq += 1
            self.snapshot_version += 1
            event = {
                "event_id": f"{self.run_id}:{self.event_seq}",
                "run_id": self.run_id,
                "ts": utc_now(),
                "type": event_type,
                "snapshot_version": self.snapshot_version,
                "data": data or {},
            }
            self.event_journal.append(event)
            self.updated_at = event["ts"]  # type: ignore[assignment]
            return event

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "run_id": self.run_id,
                "thread_id": self.thread_id,
                "phase": self.phase,
                "current_node": self.current_node,
                "status": self.state.status.value if hasattr(self.state.status, "value") else str(self.state.status),
                "loop_count": self.state.loop_count,
                "max_loops": self.state.max_loops,
                "updated_at": self.updated_at,
                "review_required": self.review_payload is not None,
                "artifact_path": str(self.artifact_path) if self.artifact_path else None,
                "error": self.error,
            }


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, RunSession] = {}
        self._lock = threading.RLock()

    def add(self, session: RunSession) -> None:
        with self._lock:
            self._sessions[session.run_id] = session

    def get(self, run_id: str) -> RunSession | None:
        with self._lock:
            return self._sessions.get(run_id)

    def all(self) -> list[RunSession]:
        with self._lock:
            return list(self._sessions.values())

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for session in self._sessions.values() if not is_terminal_phase(session.phase))


def create_session(request_payload: dict[str, Any], config: AppConfig) -> RunSession:
    run_id = uuid.uuid4().hex
    thread_id = f"web-{run_id[:12]}"
    initial_state = ResearchState(
        topic=request_payload["topic"],
        mode=config.mode,
        report_format=config.report_format,
        max_loops=config.max_loops,
        run_metadata=RunMetadata(
            model_name=config.effective_model_name,
            search_provider=config.search_provider,
            thread_id=thread_id,
        ),
    )
    session = RunSession(
        run_id=run_id,
        thread_id=thread_id,
        input_payload=request_payload,
        state=initial_state,
        config=config,
    )
    session.add_log("info", "Run created", None)
    session.append_event("run.created", session.snapshot())
    return session


def run_session_in_background(session: RunSession) -> threading.Thread:
    thread = threading.Thread(target=advance_run, args=(session,), daemon=True)
    thread.start()
    return thread


def run_report_in_background(session: RunSession) -> threading.Thread:
    thread = threading.Thread(target=finish_after_review, args=(session,), daemon=True)
    thread.start()
    return thread


def advance_run(session: RunSession) -> None:
    try:
        _advance_run(session)
    except Exception as exc:  # pragma: no cover - defensive runtime path
        with session.lock:
            session.error = str(exc)
            session.phase = "failed"
            session.current_node = session.current_node or "report_agent"
            session.state = session.state.with_error(str(exc))
        session.add_log("err", f"Run failed: {exc}", session.current_node)
        session.append_event("run.failed", session.snapshot())


def _advance_run(session: RunSession) -> None:
    while True:
        if session.review_payload is not None or is_terminal_phase(session.phase):
            return

        _run_node(session, "search_agent", run_search_agent, "searching")
        _run_node(session, "synthesis_agent", run_synthesis_agent, "synthesizing")

        if session.state.should_search_again:
            session.loop_history.append(f"loop-{session.state.loop_count}")
            session.add_log("warn", "Synthesis requested another search loop", "synthesis_agent")
            session.phase = "searching"
            session.current_node = "search_agent"
            session.append_event("run.phase_changed", session.snapshot())
            continue

        session.phase = "paused_interrupt"
        session.current_node = "human_review"
        session.review_payload = build_review_payload(session.state)
        session.add_log("halt", "Human review required", "human_review")
        session.append_event(
            "review.required",
            {
                "snapshot": session.snapshot(),
                "review": session.review_payload,
            },
        )
        return


def _run_node(
    session: RunSession,
    node_name: str,
    node_fn,
    phase: str,
) -> None:
    session.phase = phase
    session.current_node = node_name
    session.add_log("info", f"{node_name} started", node_name)
    session.append_event("node.started", {"node": node_name, "snapshot": session.snapshot()})
    update = node_fn(session.state, config=session.config)
    with session.lock:
        session.state = apply_state_update(session.state, update)
    session.add_log("ok", f"{node_name} completed", node_name)
    session.append_event("node.completed", {"node": node_name, "snapshot": session.snapshot()})


def resume_after_review(session: RunSession, human_input: dict[str, Any]) -> None:
    t0 = time.perf_counter()
    with session.lock:
        if session.review_payload is None or session.phase != "paused_interrupt":
            raise RuntimeError("run is not awaiting review")

        review = parse_review_input(human_input)
        prior_review = session.state.human_review
        if not review.edited_draft and prior_review and prior_review.edited_draft:
            review = review.model_copy(update={"edited_draft": prior_review.edited_draft})

        update: dict[str, Any] = {
            "human_review": review,
            "status": GraphStatus.FAILED if review.rejected else GraphStatus.WRITING_REPORT,
            "node_timings": session.state.node_timings.add(human_review=time.perf_counter() - t0),
        }
        if review.additional_queries:
            update["current_queries"] = review.additional_queries
        if review.rejected:
            update["errors"] = list(session.state.errors) + [f"Rejected by reviewer: {review.rejection_reason or 'Rejected by reviewer'}"]
        session.state = apply_state_update(session.state, update)
        session.review_payload = None

    session.add_log("info", f"Review resolved via {human_input.get('action', 'approve')}", "human_review")
    session.append_event("review.resolved", {"snapshot": session.snapshot()})

    if session.state.human_review and session.state.human_review.rejected:
        session.phase = "rejected"
        session.current_node = "human_review"
        session.error = session.state.human_review.rejection_reason or "Rejected by reviewer"
        _persist_terminal_state(session)
        session.append_event("run.failed", session.snapshot())
        return

    if session.state.human_review and session.state.human_review.additional_queries and session.state.loop_count < session.state.max_loops:
        session.phase = "resuming"
        session.current_node = "search_agent"
        session.append_event("run.phase_changed", session.snapshot())
        run_session_in_background(session)
        return

    session.phase = "resuming"
    session.current_node = "report_agent"
    session.append_event("run.phase_changed", session.snapshot())
    run_report_in_background(session)


def finish_after_review(session: RunSession) -> None:
    try:
        _run_node(session, "report_agent", run_report_agent, "writing_report")
        session.phase = "done"
        session.current_node = "report_agent"
        _persist_terminal_state(session)
        session.append_event("run.completed", session.snapshot())
    except Exception as exc:  # pragma: no cover - defensive runtime path
        with session.lock:
            session.error = str(exc)
            session.phase = "failed"
            session.state = session.state.with_error(str(exc))
        session.add_log("err", f"Report failed: {exc}", "report_agent")
        _persist_terminal_state(session)
        session.append_event("run.failed", session.snapshot())


def _persist_terminal_state(session: RunSession) -> None:
    state_dict = session.state.model_dump()
    state_dict["token_usage"] = session.state.token_usage
    state_dict["node_timings"] = session.state.node_timings
    state_dict["run_metadata"] = session.state.run_metadata
    state_dict["synthesis_draft"] = session.state.synthesis_draft
    state_dict["human_review"] = session.state.human_review
    state_dict["final_report"] = session.state.final_report
    path = save_run(state_dict, runs_dir=RUNS_DIR)
    session.artifact_path = path
    session.add_log("ok", f"Run artifact saved: {path.name}", session.current_node)
    eval_report = evaluate_run(json.loads(path.read_text()), path=path)
    session.add_log("info", f"Evaluation computed: overall={eval_report.scores.overall:.2f}", None)


def find_artifact_path(run_id: str, runs_dir: Path = RUNS_DIR) -> Path | None:
    for path in runs_dir.glob("*.json"):
        if path.stem == run_id:
            return path
    return None
