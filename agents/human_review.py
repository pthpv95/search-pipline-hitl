"""
agents/human_review.py — Human review node with interrupt support.

Reads: synthesis_draft, all_findings, all_sources, latest_gaps, loop_count, max_loops
Writes: human_review, status, node_timings, errors
"""

from __future__ import annotations

import time

from langgraph.types import interrupt

from state import (
    GraphStatus,
    HumanReview,
    ResearchState,
)


def build_review_payload(state: ResearchState) -> dict:
    """Build the review payload presented to the human reviewer."""
    draft = state.synthesis_draft.draft if state.synthesis_draft else ""
    gaps = state.latest_gaps
    confidence = state.synthesis_draft.confidence if state.synthesis_draft else 0.0
    limitations = state.synthesis_draft.limitations if state.synthesis_draft else []

    findings_summary = []
    for f in state.all_findings:
        findings_summary.append({
            "content": f.content[:200],
            "source_url": f.source_url,
            "confidence": f.confidence,
        })

    sources_summary = []
    for s in state.all_sources:
        sources_summary.append({
            "url": s.url,
            "title": s.title,
            "snippet": s.snippet[:150],
        })

    return {
        "topic": state.topic,
        "draft": draft,
        "confidence": confidence,
        "findings": findings_summary,
        "sources": sources_summary,
        "unresolved_gaps": gaps,
        "limitations": limitations,
        "loop_count": state.loop_count,
        "max_loops": state.max_loops,
    }


def parse_review_input(human_input: dict) -> HumanReview:
    """Parse structured human input into a HumanReview object.

    Expected keys:
        action: "approve" | "edit" | "reject"
        edited_draft: str (optional, for "edit" action)
        additional_queries: list[str] (optional)
        notes: str (optional)
        rejection_reason: str (optional, for "reject" action)
    """
    action = human_input.get("action", "approve")

    if action == "reject":
        return HumanReview(
            approved=False,
            rejected=True,
            rejection_reason=human_input.get("rejection_reason", "Rejected by reviewer"),
            notes=human_input.get("notes", ""),
        )

    if action == "edit":
        return HumanReview(
            approved=True,
            edited_draft=human_input.get("edited_draft"),
            additional_queries=human_input.get("additional_queries", []),
            notes=human_input.get("notes", ""),
        )

    # Default: approve
    return HumanReview(
        approved=True,
        additional_queries=human_input.get("additional_queries", []),
        notes=human_input.get("notes", ""),
    )


def run_human_review(state: ResearchState) -> dict:
    """Execute the human review node.

    1. Build review payload from current state
    2. Interrupt execution — wait for human input
    3. Parse human response into HumanReview
    4. Return state update
    """
    t0 = time.perf_counter()

    payload = build_review_payload(state)
    print(f"\n[human_review] presenting draft for review (confidence={payload['confidence']:.2f})")
    print(f"[human_review] {len(payload['findings'])} findings, {len(payload['sources'])} sources")

    # Interrupt and wait for human input
    human_input = interrupt(payload)

    review = parse_review_input(human_input)
    elapsed = time.perf_counter() - t0

    errors = list(state.errors)

    if review.rejected:
        print(f"[human_review] rejected: {review.rejection_reason}")
        return {
            "human_review": review,
            "status": GraphStatus.FAILED,
            "errors": errors + [f"Rejected by reviewer: {review.rejection_reason}"],
            "node_timings": state.node_timings.add(human_review=elapsed),
        }

    # Preserve edited draft from a previous review round if the current
    # review doesn't supply a new one (edit+query flow: the reviewer edits
    # the draft AND requests more search; the second approval shouldn't
    # lose the original edit).
    if not review.edited_draft and state.human_review and state.human_review.edited_draft:
        review = review.model_copy(update={"edited_draft": state.human_review.edited_draft})

    result: dict = {
        "human_review": review,
        "status": GraphStatus.WRITING_REPORT,
        "node_timings": state.node_timings.add(human_review=elapsed),
    }

    if review.additional_queries:
        print(f"[human_review] approved with {len(review.additional_queries)} additional queries")
        # Set current_queries so search_agent picks them up on next loop
        result["current_queries"] = review.additional_queries
    elif review.edited_draft:
        print("[human_review] approved with edited draft")
    else:
        print("[human_review] approved")

    return result
