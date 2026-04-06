"""
tests/test_human_review.py — Human review agent and interrupt tests.

Covers: review payload shape, parse_review_input, interrupt/resume flow,
edited draft path, additional queries path, rejection path, persistence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.human_review import build_review_payload, parse_review_input
from graph import compile_graph
from state import (
    Finding,
    FinalReport,
    GraphStatus,
    HumanReview,
    ReportFormat,
    ResearchState,
    RunMetadata,
    RunMode,
    SearchResult,
    Source,
    SynthesisDraft,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _state_for_review(
    topic: str = "test topic",
    num_sources: int = 2,
    with_gaps: bool = False,
    with_limitations: bool = False,
) -> ResearchState:
    sources = [
        Source(
            url=f"https://example.com/{i+1}",
            title=f"Source {i+1}",
            snippet=f"Snippet about {topic} {i+1}",
            relevance_score=0.8,
            source_type="mock",
        )
        for i in range(num_sources)
    ]
    findings = [
        Finding(
            content=f"Finding about {topic}",
            source_url=sources[0].url,
            confidence=0.8,
        )
    ]
    gaps = ["What about edge cases?"] if with_gaps else []
    limitations = ["Loop cap reached"] if with_limitations else []

    return ResearchState(
        topic=topic,
        mode=RunMode.DEV,
        loop_count=1,
        max_loops=2,
        search_results=[
            SearchResult(
                findings=findings,
                sources=sources,
                gaps=gaps,
                reasoning="test",
            )
        ],
        synthesis_draft=SynthesisDraft(
            draft=f"## Synthesis of {topic}\n\nKey findings about the topic.",
            remaining_gaps=gaps,
            confidence=0.85,
            needs_more_search=False,
            limitations=limitations,
        ),
        status=GraphStatus.AWAITING_HUMAN,
    )


# ---------------------------------------------------------------------------
# Review payload shape
# ---------------------------------------------------------------------------

class TestReviewPayload:
    def test_payload_has_required_keys(self):
        state = _state_for_review()
        payload = build_review_payload(state)
        required = {"topic", "draft", "confidence", "findings", "sources",
                     "unresolved_gaps", "limitations", "loop_count", "max_loops"}
        assert required.issubset(payload.keys())

    def test_payload_contains_topic(self):
        state = _state_for_review(topic="AI safety")
        payload = build_review_payload(state)
        assert payload["topic"] == "AI safety"

    def test_payload_includes_findings(self):
        state = _state_for_review(num_sources=3)
        payload = build_review_payload(state)
        assert len(payload["findings"]) >= 1
        assert "content" in payload["findings"][0]
        assert "source_url" in payload["findings"][0]

    def test_payload_includes_sources(self):
        state = _state_for_review(num_sources=3)
        payload = build_review_payload(state)
        assert len(payload["sources"]) == 3
        assert "url" in payload["sources"][0]
        assert "title" in payload["sources"][0]

    def test_payload_includes_gaps(self):
        state = _state_for_review(with_gaps=True)
        payload = build_review_payload(state)
        assert len(payload["unresolved_gaps"]) == 1

    def test_payload_includes_limitations(self):
        state = _state_for_review(with_limitations=True)
        payload = build_review_payload(state)
        assert len(payload["limitations"]) == 1

    def test_payload_loop_info(self):
        state = _state_for_review()
        payload = build_review_payload(state)
        assert payload["loop_count"] == 1
        assert payload["max_loops"] == 2


# ---------------------------------------------------------------------------
# parse_review_input
# ---------------------------------------------------------------------------

class TestParseReviewInput:
    def test_approve_action(self):
        review = parse_review_input({"action": "approve"})
        assert review.approved is True
        assert review.rejected is False

    def test_approve_with_notes(self):
        review = parse_review_input({"action": "approve", "notes": "Looks good"})
        assert review.approved is True
        assert review.notes == "Looks good"

    def test_approve_with_additional_queries(self):
        review = parse_review_input({
            "action": "approve",
            "additional_queries": ["query 1", "query 2"],
        })
        assert review.approved is True
        assert review.additional_queries == ["query 1", "query 2"]

    def test_edit_action(self):
        review = parse_review_input({
            "action": "edit",
            "edited_draft": "My edited draft",
            "notes": "Fixed intro",
        })
        assert review.approved is True
        assert review.edited_draft == "My edited draft"
        assert review.notes == "Fixed intro"

    def test_edit_with_queries(self):
        review = parse_review_input({
            "action": "edit",
            "edited_draft": "New draft",
            "additional_queries": ["more on X"],
        })
        assert review.approved is True
        assert review.edited_draft == "New draft"
        assert review.additional_queries == ["more on X"]

    def test_reject_action(self):
        review = parse_review_input({
            "action": "reject",
            "rejection_reason": "Not relevant",
        })
        assert review.approved is False
        assert review.rejected is True
        assert review.rejection_reason == "Not relevant"

    def test_reject_default_reason(self):
        review = parse_review_input({"action": "reject"})
        assert review.rejected is True
        assert review.rejection_reason == "Rejected by reviewer"

    def test_default_action_is_approve(self):
        review = parse_review_input({})
        assert review.approved is True
        assert review.rejected is False


# ---------------------------------------------------------------------------
# Interrupt/resume integration tests
# ---------------------------------------------------------------------------

def _run_until_interrupt(topic="test topic", max_loops=1):
    """Run the graph until it hits the human review interrupt."""
    graph = compile_graph(checkpointer=MemorySaver())
    thread_id = f"test-{topic.replace(' ', '-')}"
    config = {"configurable": {"thread_id": thread_id}}
    initial = ResearchState(
        topic=topic,
        mode=RunMode.DEV,
        max_loops=max_loops,
        run_metadata=RunMetadata(thread_id=thread_id),
    )
    result = graph.invoke(initial, config=config)
    state = graph.get_state(config)
    return graph, config, state, result


class TestInterruptResume:
    def test_graph_interrupts_at_human_review(self):
        graph, config, state, _ = _run_until_interrupt()
        # Graph should be paused at human_review
        assert "human_review" in state.next

    def test_interrupt_payload_is_review_payload(self):
        graph, config, state, _ = _run_until_interrupt()
        # Extract interrupt value
        tasks = state.tasks
        payload = None
        for task in tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                payload = task.interrupts[0].value
                break
        assert payload is not None
        assert "topic" in payload
        assert "draft" in payload
        assert "findings" in payload

    def test_approve_resumes_to_completion(self):
        graph, config, state, _ = _run_until_interrupt()
        result = graph.invoke(
            Command(resume={"action": "approve"}),
            config=config,
        )
        assert result["status"] == GraphStatus.COMPLETE
        assert result["final_report"] is not None

    def test_reject_terminates_pipeline(self):
        graph, config, state, _ = _run_until_interrupt()
        result = graph.invoke(
            Command(resume={"action": "reject", "rejection_reason": "Bad quality"}),
            config=config,
        )
        assert result["status"] == GraphStatus.FAILED
        assert any("Rejected" in e for e in result["errors"])
        assert result.get("final_report") is None

    def test_edited_draft_flows_to_report(self):
        graph, config, state, _ = _run_until_interrupt()
        result = graph.invoke(
            Command(resume={
                "action": "edit",
                "edited_draft": "CUSTOM EDITED DRAFT HERE",
            }),
            config=config,
        )
        assert result["status"] == GraphStatus.COMPLETE
        assert result["final_report"] is not None
        # The edited draft should appear in the report body
        assert "CUSTOM EDITED DRAFT" in result["final_report"].body

    def test_additional_queries_trigger_search_loop(self):
        # Use max_loops=2 so there's room for an extra loop
        graph, config, state, _ = _run_until_interrupt(max_loops=2)
        result = graph.invoke(
            Command(resume={
                "action": "approve",
                "additional_queries": ["what about edge cases?"],
            }),
            config=config,
        )
        # Should interrupt again at human_review after the extra search
        state = graph.get_state(config)
        # Either it completed (went through review -> search -> synthesis -> review -> report)
        # or it's at another interrupt
        if state.next:
            # Second interrupt — approve to finish
            result = graph.invoke(
                Command(resume={"action": "approve"}),
                config=config,
            )
        assert result["status"] == GraphStatus.COMPLETE
        # Should have done 2 loops
        assert result["loop_count"] == 2

    def test_additional_queries_at_loop_cap_skips_search(self):
        """When at loop cap, additional queries are ignored and pipeline proceeds to report."""
        graph, config, state, _ = _run_until_interrupt(max_loops=1)
        # max_loops=1, loop_count should already be 1
        result = graph.invoke(
            Command(resume={
                "action": "approve",
                "additional_queries": ["ignored query"],
            }),
            config=config,
        )
        assert result["status"] == GraphStatus.COMPLETE
        # Still only 1 loop — additional queries ignored at cap
        assert result["loop_count"] == 1


# ---------------------------------------------------------------------------
# Checkpoint persistence
# ---------------------------------------------------------------------------

class TestCheckpointPersistence:
    def test_state_preserved_during_interrupt(self):
        """Verify that state is preserved while waiting for human input."""
        graph, config, state, _ = _run_until_interrupt()
        values = state.values
        assert values["topic"] == "test topic"
        assert values["status"] == GraphStatus.SYNTHESIZING or values["status"] == GraphStatus.AWAITING_HUMAN
        assert len(values["search_results"]) >= 1
        assert values["synthesis_draft"] is not None

    def test_checkpoint_accessible_after_completion(self):
        graph, config, state, _ = _run_until_interrupt()
        result = graph.invoke(
            Command(resume={"action": "approve"}),
            config=config,
        )
        final_state = graph.get_state(config)
        assert final_state.values["status"] == GraphStatus.COMPLETE
        assert final_state.values["final_report"] is not None
        # No pending nodes
        assert not final_state.next


# ---------------------------------------------------------------------------
# HumanReview model
# ---------------------------------------------------------------------------

class TestHumanReviewModel:
    def test_default_values(self):
        review = HumanReview()
        assert review.approved is False
        assert review.rejected is False
        assert review.edited_draft is None
        assert review.additional_queries == []
        assert review.notes == ""
        assert review.rejection_reason == ""

    def test_approved_review(self):
        review = HumanReview(approved=True, notes="LGTM")
        assert review.approved is True
        assert review.rejected is False

    def test_rejected_review(self):
        review = HumanReview(rejected=True, rejection_reason="Off topic")
        assert review.rejected is True
        assert review.approved is False
