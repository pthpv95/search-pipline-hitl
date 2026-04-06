"""
cli_review.py — Interactive CLI for human-in-the-loop research pipeline.

Usage:
    python cli_review.py "your research topic"
    python cli_review.py "your topic" --mode live --format executive_brief
    python cli_review.py "your topic" --max-loops 3
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from config import AppConfig
from graph import compile_graph
from run_pipeline import save_run
from state import GraphStatus, ReportFormat, ResearchState, RunMetadata, RunMode


def display_review_payload(payload: dict) -> None:
    """Display the review payload in a readable format."""
    print("\n" + "=" * 60)
    print("  HUMAN REVIEW")
    print("=" * 60)

    print(f"\nTopic: {payload['topic']}")
    print(f"Confidence: {payload['confidence']:.0%}")
    print(f"Loop: {payload['loop_count']}/{payload['max_loops']}")

    print(f"\n--- Draft ({len(payload['draft'])} chars) ---")
    # Show first 1000 chars of draft
    draft_preview = payload["draft"][:1000]
    if len(payload["draft"]) > 1000:
        draft_preview += "\n... (truncated)"
    print(draft_preview)

    if payload["findings"]:
        print(f"\n--- Key Findings ({len(payload['findings'])}) ---")
        for i, f in enumerate(payload["findings"][:5], 1):
            content = textwrap.shorten(f["content"], width=100, placeholder="...")
            print(f"  {i}. [{f['confidence']:.0%}] {content}")
        if len(payload["findings"]) > 5:
            print(f"  ... and {len(payload['findings']) - 5} more")

    if payload["sources"]:
        print(f"\n--- Sources ({len(payload['sources'])}) ---")
        for i, s in enumerate(payload["sources"], 1):
            print(f"  {i}. {s['title']}")
            print(f"     {s['url']}")

    if payload["unresolved_gaps"]:
        print(f"\n--- Unresolved Gaps ({len(payload['unresolved_gaps'])}) ---")
        for gap in payload["unresolved_gaps"]:
            print(f"  - {gap}")

    if payload["limitations"]:
        print(f"\n--- Limitations ---")
        for lim in payload["limitations"]:
            print(f"  - {lim}")

    print()


def prompt_review_action() -> dict:
    """Interactively prompt the user for their review decision."""
    print("Actions:")
    print("  [a] Approve — proceed to report generation")
    print("  [e] Edit   — provide an edited draft")
    print("  [q] Query  — request additional search queries")
    print("  [r] Reject — stop the pipeline")
    print()

    while True:
        choice = input("Your choice [a/e/q/r]: ").strip().lower()

        if choice == "a":
            notes = input("Notes (optional, press Enter to skip): ").strip()
            return {"action": "approve", "notes": notes}

        elif choice == "e":
            print("Enter your edited draft (end with a line containing only '---'):")
            lines = []
            while True:
                line = input()
                if line.strip() == "---":
                    break
                lines.append(line)
            edited = "\n".join(lines)
            notes = input("Notes (optional): ").strip()

            # Optionally add queries
            queries = _prompt_optional_queries()
            return {
                "action": "edit",
                "edited_draft": edited,
                "additional_queries": queries,
                "notes": notes,
            }

        elif choice == "q":
            queries = _prompt_queries()
            if not queries:
                print("No queries provided. Try again.")
                continue
            notes = input("Notes (optional): ").strip()
            return {
                "action": "approve",
                "additional_queries": queries,
                "notes": notes,
            }

        elif choice == "r":
            reason = input("Rejection reason: ").strip() or "Rejected by reviewer"
            return {"action": "reject", "rejection_reason": reason}

        else:
            print(f"Invalid choice: {choice!r}. Please enter a, e, q, or r.")


def _prompt_queries() -> list[str]:
    """Prompt for additional search queries."""
    print("Enter additional search queries (one per line, empty line to finish):")
    queries = []
    while True:
        q = input("  > ").strip()
        if not q:
            break
        queries.append(q)
    return queries


def _prompt_optional_queries() -> list[str]:
    """Optionally add search queries after editing."""
    add = input("Add search queries? [y/N]: ").strip().lower()
    if add == "y":
        return _prompt_queries()
    return []


def run_interactive(
    topic: str,
    mode: RunMode = RunMode.DEV,
    report_format: ReportFormat = ReportFormat.DEEP_DIVE,
    max_loops: int = 2,
    save: bool = True,
) -> dict:
    """Run the research pipeline with interactive human review."""
    cfg = AppConfig.from_env(
        mode=mode,
        report_format=report_format,
        max_loops=max_loops,
    )

    graph = compile_graph(checkpointer=MemorySaver())
    thread_id = f"cli-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
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

    print(f"Starting research pipeline for: {topic}")
    print(f"Mode: {cfg.mode.value} | Format: {cfg.report_format.value} | Max loops: {cfg.max_loops}")

    # Run until first interrupt
    result = graph.invoke(initial_state, config=config)

    # Handle interrupt loop
    state = graph.get_state(config)
    while state.next:
        # Extract interrupt payload
        tasks = state.tasks
        payload = None
        for task in tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                payload = task.interrupts[0].value
                break

        if payload:
            display_review_payload(payload)
            human_input = prompt_review_action()
        else:
            # Fallback: auto-approve if no payload found
            print("\n[cli] No interrupt payload found, auto-approving")
            human_input = {"action": "approve"}

        result = graph.invoke(Command(resume=human_input), config=config)
        state = graph.get_state(config)

    # Print summary
    print("\n" + "=" * 60)
    print(f"Status:       {result['status']}")
    print(f"Search loops: {result['loop_count']}")
    print(f"Findings:     {sum(len(r.findings) for r in result['search_results'])}")
    print(f"Sources:      {len(result['final_report'].sources) if result.get('final_report') else 0}")
    print(f"Tokens used:  {result['token_usage'].total}")
    print(f"Errors:       {', '.join(result['errors']) if result['errors'] else 'none'}")

    if result.get("final_report"):
        print(f"\n--- Report Preview ---")
        print(f"Title: {result['final_report'].title}")
        print(f"Words: {result['final_report'].word_count}")
        body_preview = result["final_report"].body[:500]
        if len(result["final_report"].body) > 500:
            body_preview += "\n... (truncated)"
        print(body_preview)

    if save:
        path = save_run(result)
        print(f"\nRun saved: {path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Interactive research pipeline with human review")
    parser.add_argument("topic", help="Research topic")
    parser.add_argument("--mode", choices=["dev", "live", "eval"], default="dev")
    parser.add_argument("--format", choices=["executive_brief", "deep_dive"], default="deep_dive")
    parser.add_argument("--max-loops", type=int, default=2)
    parser.add_argument("--no-save", action="store_true", help="Skip saving run artifacts")

    args = parser.parse_args()

    run_interactive(
        topic=args.topic,
        mode=RunMode(args.mode),
        report_format=ReportFormat(args.format),
        max_loops=args.max_loops,
        save=not args.no_save,
    )


if __name__ == "__main__":
    main()
