from langgraph.checkpoint.memory import MemorySaver

from graph import build_graph, compile_graph
from state import GraphStatus, ReportFormat, ResearchState, RunMetadata


def attr(obj, key):
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def test_graph_compiles():
    graph = compile_graph()
    assert graph is not None


def test_graph_has_expected_nodes():
    graph = build_graph().compile()
    node_names = set(graph.nodes.keys())
    assert "search_agent" in node_names
    assert "synthesis_agent" in node_names
    assert "human_review" in node_names
    assert "report_agent" in node_names


def test_graph_loops_only_until_max_loops():
    graph = compile_graph(checkpointer=MemorySaver())
    state = ResearchState(topic="edge test", max_loops=2)
    config = {"configurable": {"thread_id": "edge-test"}}
    result = graph.invoke(state, config=config)
    assert result["loop_count"] == 2


def test_full_graph_completes():
    graph = compile_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "complete-test"}}
    state = ResearchState(
        topic="test topic",
        report_format=ReportFormat.DEEP_DIVE,
        max_loops=2,
        run_metadata=RunMetadata(thread_id="complete-test"),
    )
    result = graph.invoke(state, config=config)
    assert result["status"] == GraphStatus.COMPLETE
    assert result["errors"] == []
    assert result["loop_count"] <= state.max_loops


def test_final_report_is_populated():
    graph = compile_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "report-test"}}
    state = ResearchState(topic="report topic", max_loops=1)
    result = graph.invoke(state, config=config)
    report = result["final_report"]
    assert report is not None
    assert attr(report, "title") == state.topic
    assert attr(report, "word_count") > 0
    assert len(attr(report, "sources")) >= 1


def test_human_review_auto_approved():
    graph = compile_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "review-test"}}
    result = graph.invoke(ResearchState(topic="review topic", max_loops=1), config=config)
    review = result["human_review"]
    assert review is not None
    assert attr(review, "approved") is True


def test_token_usage_and_timings_are_tracked():
    graph = compile_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "usage-test"}}
    result = graph.invoke(ResearchState(topic="usage topic", max_loops=1), config=config)
    # In dev mode (no LLM), token usage is 0 — that's correct
    assert attr(result["token_usage"], "total") >= 0
    # Timings should always be tracked (perf_counter based)
    assert attr(result["node_timings"], "total") > 0


def test_checkpoint_state_is_available_after_run():
    checkpointer = MemorySaver()
    graph = compile_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "persist-test"}}
    graph.invoke(ResearchState(topic="persistence test", max_loops=1), config=config)
    saved = graph.get_state(config)
    assert saved is not None
    assert saved.values["topic"] == "persistence test"
    assert saved.values["status"] == GraphStatus.COMPLETE
