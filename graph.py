"""
graph.py — The graph skeleton.

All three agents are stubs that return realistic state updates
but don't call any LLM yet. The flow, edges, and HITL interrupt
are all wired and working. You'll replace the stubs week by week.

Run this file directly to see the graph execute end-to-end:
    python graph.py
"""

from __future__ import annotations

import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import (
    ResearchState,
    GraphStatus,
    ReportFormat,
    SearchResult,
    Finding,
    Source,
    SynthesisDraft,
    FinalReport,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# Node: search_agent
# Owned fields: search_results, current_queries, loop_count, token_usage, status
# ---------------------------------------------------------------------------

def search_agent(state: ResearchState) -> dict:
    """
    STUB — will call Claude with web_search and fetch_page tools in Week 2.

    For now: returns one fake search result so the rest of the graph
    can run end-to-end without any API calls.
    """
    print(f"\n[search_agent] Searching for: {state.topic}")
    print(f"  Loop: {state.loop_count + 1} / {state.max_loops}")
    print(f"  Queries: {state.current_queries or ['initial search']}")

    # --- STUB DATA --- replace this block entirely in Week 2 ---
    fake_result = SearchResult(
        findings=[
            Finding(
                content=f"Key insight about {state.topic} from stub search.",
                source_url="https://example.com/article-1",
                confidence=0.85,
            ),
            Finding(
                content=f"Secondary finding about {state.topic} implications.",
                source_url="https://example.com/article-2",
                confidence=0.72,
            ),
        ],
        gaps=["What are the long-term effects?", "How does this compare to alternatives?"],
        follow_up_queries=[f"{state.topic} long term effects", f"{state.topic} vs alternatives"],
        sources=[
            Source(url="https://example.com/article-1", title="Article 1", snippet="...", relevance_score=0.9),
            Source(url="https://example.com/article-2", title="Article 2", snippet="...", relevance_score=0.75),
        ],
        tokens_used=1200,
    )
    # --- END STUB ---

    return {
        "search_results": state.search_results + [fake_result],
        "loop_count": state.loop_count + 1,
        "status": GraphStatus.SYNTHESIZING,
        "token_usage": TokenUsage(
            search_agent=state.token_usage.search_agent + fake_result.tokens_used,
            synthesis_agent=state.token_usage.synthesis_agent,
            report_agent=state.token_usage.report_agent,
        ),
    }


# ---------------------------------------------------------------------------
# Node: synthesis_agent
# Owned fields: synthesis_draft, status
# ---------------------------------------------------------------------------

def synthesis_agent(state: ResearchState) -> dict:
    """
    STUB — will call Claude for multi-turn synthesis in Week 3.

    Returns a draft that signals another search loop is needed
    on the first run, so the loop logic gets exercised.
    """
    print(f"\n[synthesis_agent] Synthesizing {len(state.all_findings)} findings...")

    # First loop: signal we need more — exercises the conditional edge
    needs_more = state.loop_count < state.max_loops

    # --- STUB DATA --- replace this block entirely in Week 3 ---
    draft = SynthesisDraft(
        draft=f"## Synthesis of {state.topic}\n\nBased on {len(state.all_findings)} findings across {len(state.search_results)} search round(s):\n\n- Finding 1: {state.all_findings[0].content if state.all_findings else 'None yet'}\n\n*[Stub synthesis — replace in Week 3]*",
        remaining_gaps=state.latest_gaps if needs_more else [],
        confidence=0.75,
        needs_more_search=needs_more,
    )
    # --- END STUB ---

    return {
        "synthesis_draft": draft,
        "current_queries": draft.remaining_gaps,
        "status": GraphStatus.AWAITING_HUMAN if not needs_more else GraphStatus.SEARCHING,
    }


# ---------------------------------------------------------------------------
# Node: human_review
# Owned fields: human_review, status
# This node is where the HITL interrupt fires. In Week 4 you'll add
# langgraph.interrupt() here. For now it auto-approves.
# ---------------------------------------------------------------------------

def human_review_node(state: ResearchState) -> dict:
    """
    STUB — will use interrupt() for real human input in Week 4.

    For now: auto-approves the synthesis so the graph completes.
    """
    print(f"\n[human_review] Draft ready for review.")
    print(f"  Draft length: {len(state.synthesis_draft.draft)} chars")
    print(f"  Auto-approving (HITL coming in Week 4)...")

    from state import HumanReview
    return {
        "human_review": HumanReview(approved=True),
        "status": GraphStatus.WRITING_REPORT,
    }


# ---------------------------------------------------------------------------
# Node: report_agent
# Owned fields: final_report, status
# ---------------------------------------------------------------------------

def report_agent(state: ResearchState) -> dict:
    """
    STUB — will call Claude to write the polished report in Week 5.
    """
    print(f"\n[report_agent] Writing {state.report_format} report...")

    synthesis = state.synthesis_draft.draft if state.synthesis_draft else ""
    approved_draft = (
        state.human_review.edited_draft
        if state.human_review and state.human_review.edited_draft
        else synthesis
    )

    # --- STUB DATA --- replace this block entirely in Week 5 ---
    if state.report_format == ReportFormat.EXECUTIVE_BRIEF:
        body = f"# {state.topic}\n\n**Executive Brief**\n\n{approved_draft[:500]}...\n\n*[Stub report — replace in Week 5]*"
    else:
        body = f"# {state.topic}\n\n## Overview\n\n{approved_draft}\n\n## Sources\n\n" + "\n".join(
            f"- [{s.title}]({s.url})" for s in state.all_sources
        ) + "\n\n*[Stub report — replace in Week 5]*"

    report = FinalReport(
        title=state.topic,
        executive_summary=f"Research on {state.topic} covering {len(state.all_findings)} findings.",
        body=body,
        sources=state.all_sources,
        format=state.report_format,
        word_count=len(body.split()),
    )
    # --- END STUB ---

    return {
        "final_report": report,
        "status": GraphStatus.COMPLETE,
    }


# ---------------------------------------------------------------------------
# Conditional edge: should we search again or go to human review?
# ---------------------------------------------------------------------------

def route_after_synthesis(state: ResearchState) -> str:
    """
    Called after synthesis_agent runs.
    Returns the name of the next node to visit.
    """
    if state.should_search_again:
        print(f"\n[router] Gaps remain — looping back to search_agent")
        return "search_agent"
    print(f"\n[router] Synthesis complete — routing to human review")
    return "human_review"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    builder = StateGraph(ResearchState)

    # Register nodes
    builder.add_node("search_agent",    search_agent)
    builder.add_node("synthesis_agent", synthesis_agent)
    builder.add_node("human_review",    human_review_node)
    builder.add_node("report_agent",    report_agent)

    # Entry point
    builder.set_entry_point("search_agent")

    # Fixed edges
    builder.add_edge("search_agent",    "synthesis_agent")
    builder.add_edge("human_review",    "report_agent")
    builder.add_edge("report_agent",    END)

    # Conditional edge: loop back or proceed
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
    """
    Compile with an optional checkpointer.
    Pass MemorySaver() to enable persistent state (Week 4).
    """
    builder = build_graph()
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Quick smoke test — run the full graph and print a summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    graph = compile_graph(checkpointer=MemorySaver())

    initial_state = ResearchState(
        topic="impact of LLMs on software development productivity",
        report_format=ReportFormat.DEEP_DIVE,
        max_loops=2,
    )

    config = {"configurable": {"thread_id": "test-run-001"}}

    print("=" * 60)
    print(f"Starting research: {initial_state.topic}")
    print("=" * 60)

    final = graph.invoke(initial_state, config=config)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    # LangGraph returns Pydantic models — use getattr with dict fallback
    def get(obj, key):
        return obj[key] if isinstance(obj, dict) else getattr(obj, key)

    search_results = final['search_results']
    token_usage    = final['token_usage']
    final_report   = final['final_report']

    total_findings = sum(len(get(r, 'findings')) for r in search_results)
    all_urls = set(get(s, 'url') for r in search_results for s in get(r, 'sources'))
    total_tokens = get(token_usage, 'search_agent') + get(token_usage, 'synthesis_agent') + get(token_usage, 'report_agent')

    print(f"Status:       {final['status']}")
    print(f"Search loops: {final['loop_count']}")
    print(f"Findings:     {total_findings}")
    print(f"Sources:      {len(all_urls)}")
    print(f"Tokens used:  {total_tokens}")
    print(f"Report words: {get(final_report, 'word_count')}")
    print(f"Errors:       {final['errors'] or 'none'}")
