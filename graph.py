"""
graph.py — Week 1 graph skeleton with deterministic stub agents.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from config import DEFAULT_CONFIG
from state import (
    FinalReport,
    Finding,
    GraphStatus,
    HumanReview,
    ReportFormat,
    ResearchState,
    RunMetadata,
    SearchResult,
    Source,
    SynthesisDraft,
)


def search_agent(state: ResearchState) -> dict:
    print(f"\n[search_agent] topic={state.topic}")
    print(f"[search_agent] loop={state.loop_count + 1}/{state.max_loops}")

    query_seed = state.current_queries or [state.topic]
    query_label = ", ".join(query_seed)

    fake_result = SearchResult(
        findings=[
            Finding(
                content=f"Stub finding about {state.topic} based on query {query_label}.",
                source_url="https://example.com/article-1",
                confidence=0.86,
            ),
            Finding(
                content=f"Stub comparison signal for {state.topic}.",
                source_url="https://example.com/article-2",
                confidence=0.74,
            ),
        ],
        gaps=[
            f"What are the long-term implications of {state.topic}?",
            f"How does {state.topic} compare with common alternatives?",
        ],
        follow_up_queries=[
            f"{state.topic} long-term implications",
            f"{state.topic} comparison alternatives",
        ],
        sources=[
            Source(
                url="https://example.com/article-1",
                title="Example Article 1",
                snippet="A stub source used for local graph validation.",
            ),
            Source(
                url="https://example.com/article-2",
                title="Example Article 2",
                snippet="A second stub source used for local graph validation.",
            ),
        ],
        reasoning="Stub search result for Week 1 graph validation.",
        tokens_used=1200,
    )

    return {
        "search_results": state.search_results + [fake_result],
        "loop_count": state.loop_count + 1,
        "status": GraphStatus.SYNTHESIZING,
        "token_usage": state.token_usage.add(search_agent=fake_result.tokens_used),
        "node_timings": state.node_timings.add(search_agent=0.11),
    }


def synthesis_agent(state: ResearchState) -> dict:
    print(f"\n[synthesis_agent] findings={len(state.all_findings)}")

    needs_more = state.loop_count < state.max_loops
    remaining_gaps = state.search_results[-1].gaps if needs_more and state.search_results else []
    limitations = [] if needs_more else ["Loop cap reached; proceeding with available evidence."]

    draft = SynthesisDraft(
        draft=(
            f"## Synthesis of {state.topic}\n\n"
            f"Search rounds: {len(state.search_results)}\n"
            f"Findings collected: {len(state.all_findings)}\n\n"
            f"- {state.all_findings[0].content if state.all_findings else 'No findings available.'}\n"
        ),
        remaining_gaps=remaining_gaps,
        confidence=0.78,
        needs_more_search=needs_more,
        limitations=limitations,
    )

    return {
        "synthesis_draft": draft,
        "current_queries": remaining_gaps,
        "status": GraphStatus.SEARCHING if needs_more else GraphStatus.AWAITING_HUMAN,
        "token_usage": state.token_usage.add(synthesis_agent=400),
        "node_timings": state.node_timings.add(synthesis_agent=0.07),
    }


def human_review_node(state: ResearchState) -> dict:
    print("\n[human_review] auto-approving stub draft")
    return {
        "human_review": HumanReview(approved=True),
        "status": GraphStatus.WRITING_REPORT,
        "node_timings": state.node_timings.add(human_review=0.01),
    }


def report_agent(state: ResearchState) -> dict:
    print(f"\n[report_agent] format={state.report_format}")

    approved_draft = (
        state.human_review.edited_draft
        if state.human_review and state.human_review.edited_draft
        else (state.synthesis_draft.draft if state.synthesis_draft else "")
    )

    if state.report_format == ReportFormat.EXECUTIVE_BRIEF:
        body = (
            f"# {state.topic}\n\n"
            f"## Executive Summary\n\n"
            f"Research covered {len(state.all_findings)} findings across {len(state.search_results)} search rounds.\n\n"
            f"## Draft\n\n{approved_draft}\n"
        )
    else:
        body = (
            f"# {state.topic}\n\n"
            f"## Overview\n\n{approved_draft}\n\n"
            "## Sources\n\n"
            + "\n".join(f"- [{source.title}]({source.url})" for source in state.all_sources)
        )

    report = FinalReport(
        title=state.topic,
        executive_summary=f"Research on {state.topic} with {len(state.all_findings)} findings.",
        body=body,
        sources=state.all_sources,
        format=state.report_format,
        word_count=len(body.split()),
    )

    return {
        "final_report": report,
        "status": GraphStatus.COMPLETE,
        "token_usage": state.token_usage.add(report_agent=800),
        "node_timings": state.node_timings.add(report_agent=0.09),
    }


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
