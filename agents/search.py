"""
agents/search.py — Search agent with structured output and corrective retry.

Reads: topic, current_queries, loop_count, max_loops, mode, search_results, token_usage, node_timings
Writes: search_results, loop_count, status, current_queries, token_usage, node_timings, errors
"""

from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field, ValidationError, model_validator

from config import AppConfig, DEFAULT_CONFIG
from llm_factory import extract_token_usage, get_chat_model, has_llm_key, tool_choice_for
from state import (
    Finding,
    GraphStatus,
    ResearchState,
    RunMode,
    SearchResult,
    Source,
)
from tools.web import hits_to_sources, web_search


class SearchOutput(BaseModel):
    """Structured output the LLM must produce via tool call."""

    findings: list[Finding]
    gaps: list[str]
    follow_up_queries: list[str]
    sources: list[Source]
    reasoning: str

    @model_validator(mode="before")
    @classmethod
    def _coerce_stringified_lists(cls, data: Any) -> Any:
        """Some providers return list fields as JSON strings (e.g. '[]' instead of [])."""
        if isinstance(data, dict):
            for key, value in list(data.items()):
                if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                    try:
                        data[key] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
        return data


SEARCH_SYSTEM = (
    "You are a research search agent. Given a topic and search results, "
    "extract structured findings, identify gaps, and suggest follow-up queries. "
    "You MUST call the SearchOutput tool with your response. "
    "Do not respond with plain text."
)


def _build_search_prompt(topic: str, queries: list[str], sources: list[Source]) -> str:
    source_block = "\n".join(
        f"- [{s.title}]({s.url}): {s.snippet}" for s in sources
    )
    query_label = ", ".join(queries) if queries else topic
    return (
        f"Research topic: {topic}\n"
        f"Current queries: {query_label}\n\n"
        f"Search results:\n{source_block}\n\n"
        "Extract findings from these results. Identify remaining gaps. "
        "Suggest follow-up queries if coverage is incomplete. "
        "Include source URLs in each finding."
    )


def _parse_tool_call(response: Any) -> SearchOutput:
    """Parse and validate a SearchOutput from the LLM response's tool calls.

    Raises ValueError if the response has no tool calls, the wrong tool, or invalid args.
    """
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        raise ValueError("Model returned prose instead of a tool call")

    call = tool_calls[0]
    if call["name"] != "SearchOutput":
        raise ValueError(f"Model called wrong tool: {call['name']}")

    return SearchOutput.model_validate(call["args"])


def run_search_agent(
    state: ResearchState,
    config: AppConfig | None = None,
) -> dict:
    """Execute the search agent node.

    1. Run web search using current queries
    2. Feed results to LLM for structured extraction
    3. Retry on malformed output (bounded)
    4. Return state update dict
    """
    cfg = config or DEFAULT_CONFIG
    t0 = time.perf_counter()

    query_seed = state.current_queries or [state.topic]
    print(f"\n[search_agent] topic={state.topic}")
    print(f"[search_agent] loop={state.loop_count + 1}/{state.max_loops}")
    print(f"[search_agent] queries={query_seed}")

    # --- Step 1: Web search ---
    all_hits = []
    source_type = "mock"
    for q in query_seed:
        hits, stype = web_search(
            q,
            mode=state.mode,
            tavily_api_key=cfg.tavily_api_key,
        )
        all_hits.extend(hits)
        source_type = stype

    sources = hits_to_sources(all_hits, source_type)
    print(f"[search_agent] fetched {len(sources)} sources ({source_type})")

    # --- Step 2: LLM structured extraction ---
    if not has_llm_key(cfg) and state.mode != RunMode.DEV:
        raise RuntimeError(
            f"{state.mode.value} mode requires a valid API key for LLM extraction"
        )

    if not has_llm_key(cfg):
        # No LLM key — return stub extraction (dev mode only)
        print("[search_agent] no LLM key configured, using stub extraction (dev mode)")
        search_output = SearchOutput(
            findings=[
                Finding(
                    content=f"Stub finding from search on '{state.topic}'",
                    source_url=sources[0].url if sources else "https://example.com",
                    confidence=0.8,
                )
            ],
            gaps=[f"What are the long-term implications of {state.topic}?"],
            follow_up_queries=[f"{state.topic} long-term implications"],
            sources=sources,
            reasoning="Stub extraction — no LLM key available.",
        )
        tokens_in, tokens_out = 0, 0
    else:
        search_output, tokens_in, tokens_out = _llm_extract(
            topic=state.topic,
            queries=query_seed,
            sources=sources,
            cfg=cfg,
        )

    elapsed = time.perf_counter() - t0
    tokens_total = tokens_in + tokens_out

    result = SearchResult(
        findings=search_output.findings,
        gaps=search_output.gaps,
        follow_up_queries=search_output.follow_up_queries,
        sources=search_output.sources,
        reasoning=search_output.reasoning,
        tokens_used=tokens_total,
    )

    return {
        "search_results": state.search_results + [result],
        "loop_count": state.loop_count + 1,
        "current_queries": search_output.follow_up_queries,
        "status": GraphStatus.SYNTHESIZING,
        "token_usage": state.token_usage.add(
            search_agent_input=tokens_in,
            search_agent_output=tokens_out,
        ),
        "node_timings": state.node_timings.add(search_agent=elapsed),
    }


def _llm_extract(
    topic: str,
    queries: list[str],
    sources: list[Source],
    cfg: AppConfig,
) -> tuple[SearchOutput, int, int]:
    """Call LLM with tool binding and corrective retry. Returns (output, input_tokens, output_tokens)."""
    llm = get_chat_model(cfg)
    llm_with_tool = llm.bind_tools(
        [SearchOutput],
        tool_choice=tool_choice_for("SearchOutput", cfg.llm_provider),
    )

    prompt = _build_search_prompt(topic, queries, sources)
    messages = [HumanMessage(content=f"{SEARCH_SYSTEM}\n\n{prompt}")]
    total_in = 0
    total_out = 0

    for attempt in range(1, cfg.max_retries + 2):  # 1 initial + max_retries
        response = llm_with_tool.invoke(messages)
        in_tokens, out_tokens = extract_token_usage(response)
        total_in += in_tokens
        total_out += out_tokens

        try:
            output = _parse_tool_call(response)
            print(f"[search_agent] LLM extraction succeeded (attempt {attempt})")
            return output, total_in, total_out
        except (ValueError, ValidationError) as e:
            if attempt > cfg.max_retries:
                raise RuntimeError(
                    f"Search agent failed after {attempt} attempts: {e}"
                ) from e

            print(f"[search_agent] retry {attempt}/{cfg.max_retries}: {e}")
            # Corrective retry: feed the error back
            tool_calls = getattr(response, "tool_calls", [])
            messages.append(response)

            if tool_calls:
                # Model made a tool call but args were invalid — use ToolMessage
                messages.append(
                    ToolMessage(
                        content=f"Validation error: {e}. Please retry with corrections.",
                        tool_call_id=tool_calls[0]["id"],
                    )
                )
            # Always add a human nudge (handles both prose and bad-args cases)
            messages.append(
                HumanMessage(
                    content=f"Your previous response was invalid: {e}. "
                    "You MUST call the SearchOutput tool. Retry now."
                )
            )

    # unreachable, but satisfies type checker
    raise RuntimeError("Search agent retry loop exited unexpectedly")
