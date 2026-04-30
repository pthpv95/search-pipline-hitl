"""
Adapters from internal runtime state and saved artifacts to web DTOs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from api_runtime import RunSession
from evals.eval import estimate_cost, evaluate_run
from state import GraphStatus, ResearchState


def map_phase(status: Any, human_review: Any = None) -> str:
    raw = status.value if hasattr(status, "value") else str(status)
    if raw == GraphStatus.INITIALIZING.value:
        return "initializing"
    if raw == GraphStatus.SEARCHING.value:
        return "searching"
    if raw == GraphStatus.SYNTHESIZING.value:
        return "synthesizing"
    if raw == GraphStatus.AWAITING_HUMAN.value:
        return "paused_interrupt"
    if raw == GraphStatus.WRITING_REPORT.value:
        return "writing_report"
    if raw == GraphStatus.COMPLETE.value:
        return "done"
    if raw == GraphStatus.FAILED.value and getattr(human_review, "rejected", False):
        return "rejected"
    if raw == GraphStatus.FAILED.value:
        return "failed"
    return "initializing"


def _get_costs(token_usage: Any, model_name: str) -> dict[str, float]:
    return estimate_cost(token_usage, model_name or "unknown")


def _node_rows(token_usage: Any, node_timings: Any, costs: dict[str, float]) -> list[dict[str, Any]]:
    def attr(obj: Any, key: str, default: float = 0.0) -> float:
        if obj is None:
            return default
        if isinstance(obj, dict):
            value = obj.get(key)
            return float(value) if value is not None else default
        return float(getattr(obj, key, default) or default)

    rows = []
    for node in ("search_agent", "synthesis_agent", "human_review", "report_agent"):
        tokens = int(attr(token_usage, node))
        seconds = attr(node_timings, node)
        rows.append(
            {
                "id": node,
                "label": node,
                "tokens": tokens,
                "secs": seconds,
                "cost": costs.get(node, 0.0),
            }
        )
    return rows


def _source_dtos(sources: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, source in enumerate(sources, start=1):
        url = source["url"] if isinstance(source, dict) else source.url
        parsed = urlparse(url)
        items.append(
            {
                "id": idx,
                "url": url,
                "domain": parsed.netloc,
                "path": parsed.path or "/",
                "title": source["title"] if isinstance(source, dict) else source.title,
                "snippet": source.get("snippet", "") if isinstance(source, dict) else source.snippet,
            }
        )
    return items


def _draft_view_from_state(state: ResearchState) -> dict[str, Any]:
    draft_text = ""
    source_kind = "none"
    confidence = 0.0
    limitations: list[str] = []
    if state.final_report:
        draft_text = state.final_report.body
        source_kind = "final_report"
    elif state.human_review and state.human_review.edited_draft:
        draft_text = state.human_review.edited_draft
        source_kind = "edited_draft"
    elif state.synthesis_draft:
        draft_text = state.synthesis_draft.draft
        source_kind = "synthesis_draft"

    if state.synthesis_draft:
        confidence = state.synthesis_draft.confidence
        limitations = list(state.synthesis_draft.limitations)

    report_sources = state.final_report.sources if state.final_report else state.all_sources
    return {
        "text": draft_text,
        "source_kind": source_kind,
        "confidence": confidence,
        "limitations": limitations,
        "sources": _source_dtos(report_sources),
        "title": state.final_report.title if state.final_report else state.topic,
        "executive_summary": state.final_report.executive_summary if state.final_report else "",
    }


def _evaluation_view(
    run_dict: dict[str, Any] | None,
    token_usage: Any,
    node_timings: Any,
    model_name: str,
    mode: str,
    search_provider: str,
    errors: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    costs = _get_costs(token_usage, model_name)
    eval_section = {
        "ready": False,
        "overall": None,
        "scores": {},
        "notes": [],
        "mode": mode,
        "model_name": model_name,
        "search_provider": search_provider,
        "token_usage": _token_usage_dict(token_usage),
        "node_timings": _timings_dict(node_timings),
        "costs": costs,
        "limitations": limitations,
        "errors": errors,
    }
    if run_dict:
        report = evaluate_run(run_dict)
        eval_section.update(
            {
                "ready": True,
                "overall": report.scores.overall,
                "scores": {
                    "citation_integrity": report.scores.citation_integrity,
                    "source_validity": report.scores.source_validity,
                    "topical_coverage": report.scores.topical_coverage,
                    "unsupported_claim_rate": report.scores.unsupported_claim_rate,
                    "loop_discipline": report.scores.loop_discipline,
                },
                "notes": report.notes,
            }
        )
    return eval_section


def _token_usage_dict(token_usage: Any) -> dict[str, int]:
    def attr(key: str) -> int:
        if token_usage is None:
            return 0
        if isinstance(token_usage, dict):
            return int(token_usage.get(key, 0) or 0)
        return int(getattr(token_usage, key, 0) or 0)

    return {
        "search_agent": attr("search_agent"),
        "search_agent_input": attr("search_agent_input"),
        "search_agent_output": attr("search_agent_output"),
        "synthesis_agent": attr("synthesis_agent"),
        "synthesis_agent_input": attr("synthesis_agent_input"),
        "synthesis_agent_output": attr("synthesis_agent_output"),
        "report_agent": attr("report_agent"),
        "report_agent_input": attr("report_agent_input"),
        "report_agent_output": attr("report_agent_output"),
        "total": attr("total"),
        "total_input": attr("total_input"),
        "total_output": attr("total_output"),
    }


def _timings_dict(node_timings: Any) -> dict[str, float]:
    def attr(key: str) -> float:
        if node_timings is None:
            return 0.0
        if isinstance(node_timings, dict):
            return float(node_timings.get(key, 0.0) or 0.0)
        return float(getattr(node_timings, key, 0.0) or 0.0)

    return {
        "search_agent": attr("search_agent"),
        "synthesis_agent": attr("synthesis_agent"),
        "human_review": attr("human_review"),
        "report_agent": attr("report_agent"),
        "total": attr("total"),
    }


def session_to_summary(session: RunSession) -> dict[str, Any]:
    model_name = session.state.run_metadata.model_name
    costs = _get_costs(session.state.token_usage, model_name)
    overall_score = None
    if session.artifact_path and session.artifact_path.exists():
        overall_score = evaluate_run(json.loads(session.artifact_path.read_text()), session.artifact_path).scores.overall
    return {
        "id": session.run_id,
        "topic": session.state.topic,
        "status": session.phase,
        "phase": session.phase,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "mode": session.state.mode.value,
        "report_format": session.state.report_format.value,
        "loop_count": session.state.loop_count,
        "max_loops": session.state.max_loops,
        "overall_score": overall_score,
        "token_total": session.state.token_usage.total,
        "cost_usd": costs["total"],
        "artifact_available": session.artifact_path is not None,
        "is_active_session": True,
    }


def artifact_to_summary(path: Path) -> dict[str, Any]:
    run = json.loads(path.read_text())
    model_name = (run.get("run_metadata") or {}).get("model_name", "unknown")
    costs = _get_costs(run.get("token_usage"), model_name)
    evaluation = evaluate_run(run, path)
    phase = "rejected" if run.get("status") == GraphStatus.FAILED.value else "done"
    return {
        "id": path.stem,
        "topic": run.get("topic", "<unknown>"),
        "status": phase,
        "phase": phase,
        "created_at": run.get("saved_at"),
        "updated_at": run.get("saved_at"),
        "mode": run.get("mode", "dev"),
        "report_format": (run.get("final_report") or {}).get("format", "deep_dive"),
        "loop_count": run.get("loop_count", 0),
        "max_loops": run.get("max_loops", 0),
        "overall_score": evaluation.scores.overall,
        "token_total": (run.get("token_usage") or {}).get("total", 0),
        "cost_usd": costs["total"],
        "artifact_available": True,
        "is_active_session": False,
    }


def session_to_detail(session: RunSession) -> dict[str, Any]:
    state = session.state
    model_name = state.run_metadata.model_name
    costs = _get_costs(state.token_usage, model_name)
    run_dict = None
    if session.artifact_path and session.artifact_path.exists():
        run_dict = json.loads(session.artifact_path.read_text())
    draft = _draft_view_from_state(state)
    review = {
        "is_pending": session.review_payload is not None,
        "payload": session.review_payload,
        "last_decision": (
            {
                "approved": state.human_review.approved,
                "rejected": state.human_review.rejected,
                "edited_draft": state.human_review.edited_draft,
                "additional_queries": state.human_review.additional_queries,
                "notes": state.human_review.notes,
                "rejection_reason": state.human_review.rejection_reason,
            }
            if state.human_review
            else None
        ),
    }
    return {
        "summary": session_to_summary(session),
        "pipeline": {
            "current_node": session.current_node,
            "phase": session.phase,
            "loop_count": state.loop_count,
            "max_loops": state.max_loops,
            "nodes": _node_rows(state.token_usage, state.node_timings, costs),
            "has_looped": bool(session.loop_history or state.loop_count > 1),
        },
        "review": review,
        "draft": draft,
        "evaluation": _evaluation_view(
            run_dict=run_dict,
            token_usage=state.token_usage,
            node_timings=state.node_timings,
            model_name=model_name,
            mode=state.mode.value,
            search_provider=state.run_metadata.search_provider,
            errors=list(state.errors),
            limitations=list(state.synthesis_draft.limitations) if state.synthesis_draft else [],
        ),
        "log": {"entries": list(session.log_entries)},
        "raw_state_meta": {
            "status": state.status.value,
            "thread_id": session.thread_id,
            "artifact_path": str(session.artifact_path) if session.artifact_path else None,
            "error": session.error,
        },
    }


def artifact_to_detail(path: Path) -> dict[str, Any]:
    run = json.loads(path.read_text())
    evaluation = evaluate_run(run, path)
    report = run.get("final_report") or {}
    token_usage = run.get("token_usage") or {}
    node_timings = run.get("node_timings") or {}
    model_name = (run.get("run_metadata") or {}).get("model_name", "unknown")
    costs = _get_costs(token_usage, model_name)
    phase = "rejected" if run.get("status") == GraphStatus.FAILED.value else "done"
    return {
        "summary": artifact_to_summary(path),
        "pipeline": {
            "current_node": "report_agent" if phase == "done" else "human_review",
            "phase": phase,
            "loop_count": run.get("loop_count", 0),
            "max_loops": run.get("max_loops", 0),
            "nodes": _node_rows(token_usage, node_timings, costs),
            "has_looped": run.get("loop_count", 0) > 1,
        },
        "review": {
            "is_pending": False,
            "payload": None,
            "last_decision": None,
        },
        "draft": {
            "text": report.get("body", ""),
            "source_kind": "final_report",
            "confidence": None,
            "limitations": run.get("limitations", []),
            "sources": _source_dtos(report.get("sources", [])),
            "title": report.get("title", run.get("topic", "<unknown>")),
            "executive_summary": report.get("executive_summary", ""),
        },
        "evaluation": _evaluation_view(
            run_dict=run,
            token_usage=token_usage,
            node_timings=node_timings,
            model_name=model_name,
            mode=run.get("mode", "dev"),
            search_provider=(run.get("run_metadata") or {}).get("search_provider", "unknown"),
            errors=run.get("errors", []),
            limitations=run.get("limitations", []),
        ),
        "log": {
            "entries": [
                {
                    "id": "artifact-1",
                    "t": run.get("saved_at"),
                    "node": None,
                    "level": "info",
                    "msg": f"Loaded persisted artifact {path.name}",
                }
            ]
        },
        "raw_state_meta": {
            "status": run.get("status", "unknown"),
            "thread_id": (run.get("run_metadata") or {}).get("thread_id"),
            "artifact_path": str(path),
            "error": ", ".join(run.get("errors", [])) if run.get("errors") else None,
        },
    }
