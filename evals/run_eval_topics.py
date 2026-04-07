"""
evals/run_eval_topics.py — Run the 5 suggested eval topics through the pipeline.

Each topic is run in eval mode (real Claude + Tavily, no mock fallback) and the
resulting state is persisted to runs/. After this finishes, run
`python -m evals.eval` to score the saved runs.

Requirements:
    - ANTHROPIC_API_KEY and TAVILY_API_KEY must be set
    - Network access for Tavily and Anthropic APIs
    - Costs real API tokens (~tens of cents per topic at default model)

Usage:
    python -m evals.run_eval_topics
    python -m evals.run_eval_topics --max-loops 1
    python -m evals.run_eval_topics --topics "topic 1" "topic 2"
"""

from __future__ import annotations

import argparse
import sys
import traceback

from run_pipeline import run_pipeline
from state import ReportFormat, RunMode

EVAL_TOPICS: list[str] = [
    "impact of LLMs on software developer productivity",
    "state of multi-agent AI systems in 2025",
    "LangGraph vs CrewAI vs AutoGen comparison",
    "prompt engineering techniques for structured output",
    "AI agent memory architectures",
]


def run_topics(
    topics: list[str],
    max_loops: int = 2,
    report_format: ReportFormat = ReportFormat.DEEP_DIVE,
) -> None:
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    for i, topic in enumerate(topics, start=1):
        print(f"\n{'#' * 60}")
        print(f"# [{i}/{len(topics)}] {topic}")
        print("#" * 60)
        try:
            run_pipeline(
                topic=topic,
                mode=RunMode.EVAL,
                report_format=report_format,
                max_loops=max_loops,
                save=True,
            )
            succeeded.append(topic)
        except Exception as e:  # noqa: BLE001 — capture all so the batch keeps going
            failed.append((topic, str(e)))
            print(f"\n[run_eval_topics] FAILED: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Topics succeeded: {len(succeeded)}/{len(topics)}")
    if failed:
        print("\nFailed topics:")
        for topic, err in failed:
            print(f"  - {topic}: {err}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval-mode runs for the suggested topics")
    parser.add_argument("--max-loops", type=int, default=2)
    parser.add_argument(
        "--format",
        choices=["executive_brief", "deep_dive"],
        default="deep_dive",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        default=None,
        help="Override the default 5 eval topics",
    )
    args = parser.parse_args()

    topics = args.topics or EVAL_TOPICS
    run_topics(
        topics=topics,
        max_loops=args.max_loops,
        report_format=ReportFormat(args.format),
    )


if __name__ == "__main__":
    main()
