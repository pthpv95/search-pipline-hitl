"""
graph.py — LangGraph research pipeline.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.report import run_report_agent
from agents.search import run_search_agent
from agents.synthesis import run_synthesis_agent
from config import DEFAULT_CONFIG
from state import (
    GraphStatus,
    HumanReview,
    ResearchState,
    RunMetadata,
)


def search_agent(state: ResearchState) -> dict:
    return run_search_agent(state, config=DEFAULT_CONFIG)


def synthesis_agent(state: ResearchState) -> dict:
    return run_synthesis_agent(state, config=DEFAULT_CONFIG)


def human_review_node(state: ResearchState) -> dict:
    print("\n[human_review] auto-approving stub draft")
    return {
        "human_review": HumanReview(approved=True),
        "status": GraphStatus.WRITING_REPORT,
        "node_timings": state.node_timings.add(human_review=0.01),
    }


def report_agent(state: ResearchState) -> dict:
    return run_report_agent(state, config=DEFAULT_CONFIG)


def route_after_synthesis(state: ResearchState) -> str:
    if state.should_search_again:
        print("\n[router] unresolved gaps remain; returning to search_agent")
        return "search_agent"
    print("\n[router] synthesis sufficient; continuing to human_review")
    return "human_review"


def build_graph() -> StateGraph:
    builder = StateGraph(ResearchState)
    builder.add_node("search_agent", search_agent)
    builder.add_node("synthesis_agent", synthesis_agent)
    builder.add_node("human_review", human_review_node)
    builder.add_node("report_agent", report_agent)

    builder.set_entry_point("search_agent")
    builder.add_edge("search_agent", "synthesis_agent")
    builder.add_edge("human_review", "report_agent")
    builder.add_edge("report_agent", END)
    builder.add_conditional_edges(
        "synthesis_agent",
        route_after_synthesis,
        {
            "search_agent": "search_agent",
            "human_review": "human_review",
        },
    )

    return builder


def compile_graph(checkpointer=None):
    return build_graph().compile(checkpointer=checkpointer)


if __name__ == "__main__":
    graph = compile_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "week1-smoke-test"}}
    initial_state = ResearchState(
        topic="impact of LLMs on software development productivity",
        mode=DEFAULT_CONFIG.mode,
        report_format=DEFAULT_CONFIG.report_format,
        max_loops=DEFAULT_CONFIG.max_loops,
        run_metadata=RunMetadata(
            model_name=DEFAULT_CONFIG.model_name,
            search_provider=DEFAULT_CONFIG.search_provider,
            thread_id=config["configurable"]["thread_id"],
        ),
    )

    final = graph.invoke(initial_state, config=config)
    print("\n" + "=" * 60)
    print(f"Status:       {final['status']}")
    print(f"Search loops: {final['loop_count']}")
    print(f"Findings:     {sum(len(r.findings) for r in final['search_results'])}")
    print(f"Sources:      {len(final['final_report'].sources) if final['final_report'] else 0}")
    print(f"Tokens used:  {final['token_usage'].total}")
    print(f"Errors:       {', '.join(final['errors']) if final['errors'] else 'none'}")
