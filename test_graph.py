"""
test_graph.py — Week 1 integration tests.

These tests verify the graph structure and state flow
without making any LLM calls. They should always pass,
even before you've implemented any real agent logic.

Run with:
    pytest test_graph.py -v
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from state import (
    ResearchState,
    GraphStatus,
    ReportFormat,
    SearchResult,
    Finding,
    Source,
    SynthesisDraft,
    TokenUsage,
)
from graph import compile_graph, build_graph


# ---------------------------------------------------------------------------
# Helper — LangGraph returns Pydantic models from invoke(), not plain dicts.
# Use this everywhere you need to read nested model fields in tests.
# ---------------------------------------------------------------------------

def attr(obj, key):
    """Get a field from either a Pydantic model or a plain dict."""
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def graph():
    return compile_graph(checkpointer=MemorySaver())


@pytest.fixture
def base_config():
    return {"configurable": {"thread_id": "test-001"}}


@pytest.fixture
def simple_topic():
    return ResearchState(
        topic="test topic",
        report_format=ReportFormat.DEEP_DIVE,
        max_loops=2,
    )


# ---------------------------------------------------------------------------
# State schema tests — catch shape regressions early
# ---------------------------------------------------------------------------

class TestStateSchema:
    def test_default_state_is_valid(self):
        state = ResearchState(topic="anything")
        assert state.status == GraphStatus.INITIALIZING
        assert state.loop_count == 0
        assert state.errors == []
        assert state.search_results == []

    def test_all_findings_flattens_across_rounds(self):
        f1 = Finding(content="a", source_url="http://a.com")
        f2 = Finding(content="b", source_url="http://b.com")
        r1 = SearchResult(findings=[f1], gaps=[], follow_up_queries=[], sources=[], tokens_used=0)
        r2 = SearchResult(findings=[f2], gaps=[], follow_up_queries=[], sources=[], tokens_used=0)
        state = ResearchState(topic="t", search_results=[r1, r2])
        assert len(state.all_findings) == 2

    def test_all_sources_deduplicates(self):
        s = Source(url="http://same.com", title="Same", snippet="...")
        r1 = SearchResult(findings=[], gaps=[], follow_up_queries=[], sources=[s], tokens_used=0)
        r2 = SearchResult(findings=[], gaps=[], follow_up_queries=[], sources=[s], tokens_used=0)
        state = ResearchState(topic="t", search_results=[r1, r2])
        assert len(state.all_sources) == 1

    def test_should_search_again_respects_max_loops(self):
        draft = SynthesisDraft(draft="x", remaining_gaps=["gap"], needs_more_search=True)
        # At max loops — should not search again
        state = ResearchState(topic="t", synthesis_draft=draft, loop_count=2, max_loops=2)
        assert state.should_search_again is False
        # Under max loops — should search again
        state2 = ResearchState(topic="t", synthesis_draft=draft, loop_count=1, max_loops=2)
        assert state2.should_search_again is True

    def test_with_error_returns_failed_state(self):
        state = ResearchState(topic="t")
        failed = state.with_error("something broke")
        assert failed.status == GraphStatus.FAILED
        assert "something broke" in failed.errors
        # Original state is unchanged
        assert state.status == GraphStatus.INITIALIZING

    def test_token_usage_total(self):
        usage = TokenUsage(search_agent=500, synthesis_agent=300, report_agent=200)
        assert usage.total == 1000


# ---------------------------------------------------------------------------
# Graph structure tests — verify the graph is wired correctly
# ---------------------------------------------------------------------------

class TestGraphStructure:
    def test_graph_compiles(self):
        graph = compile_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        builder = build_graph()
        graph = builder.compile()
        node_names = set(graph.nodes.keys())
        assert "search_agent"    in node_names
        assert "synthesis_agent" in node_names
        assert "human_review"    in node_names
        assert "report_agent"    in node_names

    def test_graph_has_conditional_edge_from_synthesis(self):
        """Verify the conditional edge behaviourally: with max_loops=2 the
        search node must run twice, which only happens if the conditional edge
        routes back correctly after the first synthesis."""
        graph = compile_graph(checkpointer=MemorySaver())
        state = ResearchState(topic="edge test", max_loops=2)
        config = {"configurable": {"thread_id": "edge-test"}}
        result = graph.invoke(state, config=config)
        assert result["loop_count"] == 2


# ---------------------------------------------------------------------------
# End-to-end flow tests — the graph must complete successfully
# ---------------------------------------------------------------------------

class TestGraphFlow:
    def test_full_graph_completes(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        assert result["status"] == GraphStatus.COMPLETE

    def test_loop_count_increments(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        assert result["loop_count"] >= 1

    def test_search_results_accumulate(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        assert len(result["search_results"]) >= 1

    def test_final_report_is_populated(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        report = result["final_report"]
        assert report is not None
        assert attr(report, "title") == simple_topic.topic
        assert attr(report, "word_count") > 0

    def test_human_review_auto_approved(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        review = result["human_review"]
        assert review is not None
        assert attr(review, "approved") is True

    def test_no_errors_on_happy_path(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        assert result["errors"] == []

    def test_token_usage_tracked(self, graph, base_config, simple_topic):
        result = graph.invoke(simple_topic, config=base_config)
        usage = result["token_usage"]
        assert attr(usage, "search_agent") > 0

    def test_executive_brief_format(self, graph):
        state = ResearchState(
            topic="brief format test",
            report_format=ReportFormat.EXECUTIVE_BRIEF,
            max_loops=1,
        )
        config = {"configurable": {"thread_id": "test-brief"}}
        result = graph.invoke(state, config=config)
        report = result["final_report"]
        assert attr(report, "format") == ReportFormat.EXECUTIVE_BRIEF

    def test_checkpoint_persists_state(self):
        """Verify state is recoverable after the graph runs (Week 4 foundation)."""
        checkpointer = MemorySaver()
        graph = compile_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "persist-test"}}

        state = ResearchState(topic="persistence test", max_loops=1)
        graph.invoke(state, config=config)

        # Retrieve state from checkpointer
        saved = graph.get_state(config)
        assert saved is not None
        assert saved.values["topic"] == "persistence test"
        assert saved.values["status"] == GraphStatus.COMPLETE
