"""
run_pipeline.py — Non-interactive pipeline runner with auto-approve and run persistence.

Usage:
    python run_pipeline.py "your research topic"
    python run_pipeline.py "your topic" --mode live --format executive_brief
    python run_pipeline.py "your topic" --max-loops 3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from config import AppConfig
from graph import compile_graph
from state import GraphStatus, ReportFormat, ResearchState, RunMetadata, RunMode

RUNS_DIR = Path(__file__).parent / "runs"


def save_run(state: dict, runs_dir: Path | None = None) -> Path:
    """Persist a completed ResearchState dict as JSON.

    Saves: topic, mode, model, timings, token usage, final report,
    source list, errors, loop count, and limitations.

    Returns the path to the saved file.
    """
    out_dir = runs_dir or RUNS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "_", state["topic"][:40].lower()).strip("_")
    short_id = uuid.uuid4().hex[:6]
    filename = f"{ts}_{slug}_{short_id}.json"

    # Extract report data
    report = state.get("final_report")
    report_data = None
    if report:
        r = report if isinstance(report, dict) else report
        report_data = {
            "title": _attr(r, "title"),
            "executive_summary": _attr(r, "executive_summary"),
            "body": _attr(r, "body"),
            "format": _attr(r, "format").value if hasattr(_attr(r, "format"), "value") else str(_attr(r, "format")),
            "word_count": _attr(r, "word_count"),
            "sources": [
                {"url": _attr(s, "url"), "title": _attr(s, "title"), "snippet": _attr(s, "snippet")}
                for s in _attr(r, "sources")
            ],
        }

    # Extract token usage (per-node totals + input/output breakdown for cost)
    token_usage = state.get("token_usage")
    token_data = {
        "search_agent": _attr(token_usage, "search_agent"),
        "synthesis_agent": _attr(token_usage, "synthesis_agent"),
        "report_agent": _attr(token_usage, "report_agent"),
        "total": _attr(token_usage, "total"),
        "search_agent_input": _attr(token_usage, "search_agent_input"),
        "search_agent_output": _attr(token_usage, "search_agent_output"),
        "synthesis_agent_input": _attr(token_usage, "synthesis_agent_input"),
        "synthesis_agent_output": _attr(token_usage, "synthesis_agent_output"),
        "report_agent_input": _attr(token_usage, "report_agent_input"),
        "report_agent_output": _attr(token_usage, "report_agent_output"),
        "total_input": _attr(token_usage, "total_input"),
        "total_output": _attr(token_usage, "total_output"),
    } if token_usage else {}

    # Extract node timings
    node_timings = state.get("node_timings")
    timing_data = {
        "search_agent": _attr(node_timings, "search_agent"),
        "synthesis_agent": _attr(node_timings, "synthesis_agent"),
        "report_agent": _attr(node_timings, "report_agent"),
        "human_review": _attr(node_timings, "human_review"),
        "total": _attr(node_timings, "total"),
    } if node_timings else {}

    # Extract run metadata
    run_meta = state.get("run_metadata")
    meta_data = {
        "model_name": _attr(run_meta, "model_name"),
        "search_provider": _attr(run_meta, "search_provider"),
        "thread_id": _attr(run_meta, "thread_id"),
    } if run_meta else {}

    # Extract limitations from synthesis draft
    synthesis = state.get("synthesis_draft")
    limitations = _attr(synthesis, "limitations") if synthesis else []

    run_data = {
        "saved_at": ts,
        "topic": state["topic"],
        "mode": state.get("mode", "dev").value if hasattr(state.get("mode", "dev"), "value") else str(state.get("mode", "dev")),
        "status": state.get("status", "unknown").value if hasattr(state.get("status", "unknown"), "value") else str(state.get("status", "unknown")),
        "loop_count": state.get("loop_count", 0),
        "max_loops": state.get("max_loops", 0),
        "errors": state.get("errors", []),
        "limitations": limitations,
        "token_usage": token_data,
        "node_timings": timing_data,
        "run_metadata": meta_data,
        "final_report": report_data,
    }

    out_path = out_dir / filename
    out_path.write_text(json.dumps(run_data, indent=2, default=str))
    return out_path


def _attr(obj, key):
    """Read attribute from dict or object."""
    if obj is None:
        return None
    return obj[key] if isinstance(obj, dict) else getattr(obj, key, None)


def run_pipeline(
    topic: str,
    mode: RunMode = RunMode.DEV,
    report_format: ReportFormat = ReportFormat.DEEP_DIVE,
    max_loops: int = 2,
    save: bool = True,
) -> dict:
    """Run the full research pipeline with auto-approve.

    Returns the final state dict.
    """
    cfg = AppConfig.from_env(
        mode=mode,
        report_format=report_format,
        max_loops=max_loops,
    )

    graph = compile_graph(checkpointer=MemorySaver())
    thread_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = ResearchState(
        topic=topic,
        mode=cfg.mode,
        report_format=cfg.report_format,
        max_loops=cfg.max_loops,
        run_metadata=RunMetadata(
            model_name=cfg.model_name,
            search_provider=cfg.search_provider,
            thread_id=thread_id,
        ),
    )

    # Run until interrupt (human review) or completion
    result = graph.invoke(initial_state, config=config)

    # Auto-approve if interrupted at human review
    state = graph.get_state(config)
    while state.next:
        print("\n[run_pipeline] auto-approving human review")
        result = graph.invoke(Command(resume={"action": "approve"}), config=config)
        state = graph.get_state(config)

    print("\n" + "=" * 60)
    print(f"Status:       {result['status']}")
    print(f"Search loops: {result['loop_count']}")
    print(f"Findings:     {sum(len(r.findings) for r in result['search_results'])}")
    print(f"Sources:      {len(result['final_report'].sources) if result.get('final_report') else 0}")
    print(f"Tokens used:  {result['token_usage'].total}")
    print(f"Errors:       {', '.join(result['errors']) if result['errors'] else 'none'}")

    # Cost summary
    from evals.eval import format_cost_summary
    print()
    print(format_cost_summary(
        token_usage=result["token_usage"],
        node_timings=result["node_timings"],
        model_name=cfg.model_name,
    ))

    if save:
        path = save_run(result)
        print(f"Run saved:    {path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Run the research pipeline")
    parser.add_argument("topic", help="Research topic")
    parser.add_argument("--mode", choices=["dev", "live", "eval"], default="dev")
    parser.add_argument("--format", choices=["executive_brief", "deep_dive"], default="deep_dive")
    parser.add_argument("--max-loops", type=int, default=2)
    parser.add_argument("--no-save", action="store_true", help="Skip saving run artifacts")

    args = parser.parse_args()

    run_pipeline(
        topic=args.topic,
        mode=RunMode(args.mode),
        report_format=ReportFormat(args.format),
        max_loops=args.max_loops,
        save=not args.no_save,
    )


if __name__ == "__main__":
    main()
