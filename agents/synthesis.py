"""
agents/synthesis.py — Synthesis agent with structured output and corrective retry.

Reads: topic, search_results, loop_count, max_loops, mode, token_usage, node_timings
Writes: synthesis_draft, current_queries, status, token_usage, node_timings, errors
"""

from __future__ import annotations

import time
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field, ValidationError

from config import AppConfig, DEFAULT_CONFIG
from state import (
    Finding,
    GraphStatus,
    ResearchState,
    RunMode,
    Source,
    SynthesisDraft,
)


class SynthesisOutput(BaseModel):
    """Structured output the LLM must produce via tool call."""

    draft: str
    remaining_gaps: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    needs_more_search: bool
    follow_up_queries: list[str]
    limitations: list[str] = Field(default_factory=list)
    reasoning: str


SYNTHESIS_SYSTEM = (
    "You are a research synthesis agent. Given a collection of findings and sources "
    "from web research, synthesize them into a coherent draft. "
    "Identify remaining knowledge gaps and whether more search is needed. "
    "If the topic is well-covered, set needs_more_search to false. "
    "If gaps remain and more search would help, set needs_more_search to true "
    "and provide specific follow_up_queries. "
    "You MUST call the SynthesisOutput tool with your response. "
    "Do not respond with plain text."
)


def _build_synthesis_prompt(
    topic: str,
    findings: list[Finding],
    sources: list[Source],
    loop_count: int,
    max_loops: int,
    previous_gaps: list[str],
) -> str:
    findings_block = "\n".join(
        f"- [{i+1}] {f.content} (confidence: {f.confidence}, source: {f.source_url})"
        for i, f in enumerate(findings)
    )
    sources_block = "\n".join(
        f"- [{s.title}]({s.url}): {s.snippet}" for s in sources
    )
    gaps_block = "\n".join(f"- {g}" for g in previous_gaps) if previous_gaps else "None identified yet."

    return (
        f"Research topic: {topic}\n"
        f"Search round: {loop_count}/{max_loops}\n\n"
        f"Findings ({len(findings)} total):\n{findings_block}\n\n"
        f"Sources ({len(sources)} total):\n{sources_block}\n\n"
        f"Previously identified gaps:\n{gaps_block}\n\n"
        "Synthesize the findings into a coherent draft. "
        "Assess whether the topic is adequately covered or if more research is needed. "
        "Be specific about remaining gaps — vague gaps like 'more research needed' are not useful. "
        f"Note: this is search round {loop_count} of {max_loops} maximum. "
        + (
            "If you set needs_more_search to true, provide specific follow_up_queries. "
            if loop_count < max_loops
            else "This is the final round — set needs_more_search to false and record any limitations. "
        )
    )


def _extract_tokens(response: Any) -> tuple[int, int]:
    meta = getattr(response, "response_metadata", {}) or {}
    usage = meta.get("usage", {})
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def _parse_tool_call(response: Any) -> SynthesisOutput:
    """Parse and validate a SynthesisOutput from the LLM response's tool calls."""
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        raise ValueError("Model returned prose instead of a tool call")

    call = tool_calls[0]
    if call["name"] != "SynthesisOutput":
        raise ValueError(f"Model called wrong tool: {call['name']}")

    return SynthesisOutput.model_validate(call["args"])


def run_synthesis_agent(
    state: ResearchState,
    config: AppConfig | None = None,
) -> dict:
    """Execute the synthesis agent node.

    1. Collect all findings and sources from search rounds
    2. Feed to LLM for structured synthesis
    3. Retry on malformed output (bounded)
    4. Decide whether to loop or proceed
    5. Return state update dict
    """
    cfg = config or DEFAULT_CONFIG
    t0 = time.perf_counter()

    findings = state.all_findings
    sources = state.all_sources
    # Use gaps from the latest search round, not the previous synthesis draft
    previous_gaps = state.search_results[-1].gaps if state.search_results else []

    print(f"\n[synthesis_agent] topic={state.topic}")
    print(f"[synthesis_agent] loop={state.loop_count}/{state.max_loops}")
    print(f"[synthesis_agent] findings={len(findings)}, sources={len(sources)}")

    # --- LLM structured synthesis ---
    if not cfg.openai_api_key and state.mode != RunMode.DEV:
        raise RuntimeError(
            f"{state.mode.value} mode requires OPENAI_API_KEY for synthesis"
        )

    if not cfg.openai_api_key:
        # Dev mode stub
        print("[synthesis_agent] no OPENAI_API_KEY, using stub synthesis (dev mode)")
        at_loop_cap = state.loop_count >= state.max_loops
        has_gaps = len(findings) < 5
        needs_more = not at_loop_cap and has_gaps

        synthesis_output = SynthesisOutput(
            draft=(
                f"## Synthesis of {state.topic}\n\n"
                f"Search rounds completed: {state.loop_count}\n"
                f"Findings collected: {len(findings)}\n\n"
                + "\n".join(f"- {f.content}" for f in findings)
            ),
            remaining_gaps=(
                [f"What are the long-term implications of {state.topic}?"]
                if has_gaps
                else []
            ),
            confidence=0.6 if has_gaps else 0.85,
            needs_more_search=needs_more,
            follow_up_queries=(
                [f"{state.topic} long-term implications"]
                if needs_more
                else []
            ),
            limitations=(
                ["Loop cap reached; proceeding with available evidence."]
                if at_loop_cap and has_gaps
                else []
            ),
            reasoning="Stub synthesis — no LLM key available.",
        )
        tokens_in, tokens_out = 0, 0
    else:
        synthesis_output, tokens_in, tokens_out = _llm_synthesize(
            topic=state.topic,
            findings=findings,
            sources=sources,
            loop_count=state.loop_count,
            max_loops=state.max_loops,
            previous_gaps=previous_gaps,
            cfg=cfg,
        )

    elapsed = time.perf_counter() - t0

    # If at loop cap, force needs_more_search=False and record limitation
    at_loop_cap = state.loop_count >= state.max_loops
    if at_loop_cap and synthesis_output.needs_more_search:
        synthesis_output = synthesis_output.model_copy(update={
            "needs_more_search": False,
            "limitations": synthesis_output.limitations
            + ["Loop cap reached; proceeding with available evidence."],
        })

    draft = SynthesisDraft(
        draft=synthesis_output.draft,
        remaining_gaps=synthesis_output.remaining_gaps,
        confidence=synthesis_output.confidence,
        needs_more_search=synthesis_output.needs_more_search,
        follow_up_queries=synthesis_output.follow_up_queries,
        limitations=synthesis_output.limitations,
    )

    # Use follow_up_queries for next search round, fall back to remaining_gaps
    next_queries = synthesis_output.follow_up_queries or synthesis_output.remaining_gaps
    next_status = (
        GraphStatus.SEARCHING
        if draft.needs_more_search and draft.remaining_gaps
        else GraphStatus.AWAITING_HUMAN
    )

    return {
        "synthesis_draft": draft,
        "current_queries": next_queries,
        "status": next_status,
        "token_usage": state.token_usage.add(
            synthesis_agent_input=tokens_in,
            synthesis_agent_output=tokens_out,
        ),
        "node_timings": state.node_timings.add(synthesis_agent=elapsed),
    }


def _llm_synthesize(
    topic: str,
    findings: list[Finding],
    sources: list[Source],
    loop_count: int,
    max_loops: int,
    previous_gaps: list[str],
    cfg: AppConfig,
) -> tuple[SynthesisOutput, int, int]:
    """Call LLM with tool binding and corrective retry. Returns (output, input_tokens, output_tokens)."""
    llm = ChatOpenAI(
        model=cfg.model_name,
        api_key=cfg.openai_api_key,
        temperature=0,
    )
    llm_with_tool = llm.bind_tools(
        [SynthesisOutput],
        tool_choice="SynthesisOutput",
    )

    prompt = _build_synthesis_prompt(
        topic, findings, sources, loop_count, max_loops, previous_gaps,
    )
    messages = [HumanMessage(content=f"{SYNTHESIS_SYSTEM}\n\n{prompt}")]
    total_in = 0
    total_out = 0

    for attempt in range(1, cfg.max_retries + 2):  # 1 initial + max_retries
        response = llm_with_tool.invoke(messages)
        in_tokens, out_tokens = _extract_tokens(response)
        total_in += in_tokens
        total_out += out_tokens

        try:
            output = _parse_tool_call(response)
            print(f"[synthesis_agent] LLM synthesis succeeded (attempt {attempt})")
            return output, total_in, total_out
        except (ValueError, ValidationError) as e:
            if attempt > cfg.max_retries:
                raise RuntimeError(
                    f"Synthesis agent failed after {attempt} attempts: {e}"
                ) from e

            print(f"[synthesis_agent] retry {attempt}/{cfg.max_retries}: {e}")
            tool_calls = getattr(response, "tool_calls", [])
            messages.append(response)

            if tool_calls:
                messages.append(
                    ToolMessage(
                        content=f"Validation error: {e}. Please retry with corrections.",
                        tool_call_id=tool_calls[0]["id"],
                    )
                )
            messages.append(
                HumanMessage(
                    content=f"Your previous response was invalid: {e}. "
                    "You MUST call the SynthesisOutput tool. Retry now."
                )
            )

    raise RuntimeError("Synthesis agent retry loop exited unexpectedly")
