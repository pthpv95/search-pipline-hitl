"""
agents/report.py — Report agent with structured output and citation integrity.

Reads: topic, synthesis_draft, human_review, search_results, all_findings, all_sources,
       report_format, mode, token_usage, node_timings
Writes: final_report, status, token_usage, node_timings, errors
"""

from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field, ValidationError, model_validator

from config import DEFAULT_CONFIG, AppConfig
from llm_factory import extract_token_usage, get_chat_model, has_llm_key, tool_choice_for
from state import (
    FinalReport,
    GraphStatus,
    ReportFormat,
    ResearchState,
    RunMode,
    Source,
)


class ReportOutput(BaseModel):
    """Structured output the LLM must produce via tool call."""

    title: str
    executive_summary: str
    body: str
    cited_source_urls: list[str] = Field(
        description="URLs of sources actually cited in the body, must be subset of provided sources"
    )
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


REPORT_SYSTEM = (
    "You are a research report agent. Given a synthesis draft, findings, and sources, "
    "produce a polished, well-structured report. "
    "Every factual claim must include an inline citation like [1], [2], etc. "
    "Only cite sources from the provided source list — never invent URLs. "
    "Include cited_source_urls listing every source URL you actually referenced. "
    "You MUST call the ReportOutput tool with your response. "
    "Do not respond with plain text."
)


def _build_report_prompt(
    topic: str,
    draft: str,
    sources: list[Source],
    report_format: ReportFormat,
    limitations: list[str],
) -> str:
    numbered_sources = "\n".join(
        f"[{i+1}] {s.title} — {s.url}\n    {s.snippet}"
        for i, s in enumerate(sources)
    )
    limitations_block = "\n".join(f"- {lim}" for lim in limitations) if limitations else "None."

    format_instruction = (
        "Format: EXECUTIVE BRIEF\n"
        "- Title\n"
        "- 3-sentence executive summary\n"
        "- 5 key findings (bulleted, with inline citations)\n"
        "- Recommendations\n"
        "- Keep it concise — under 500 words.\n"
        if report_format == ReportFormat.EXECUTIVE_BRIEF
        else
        "Format: DEEP DIVE\n"
        "- Title\n"
        "- Executive summary paragraph\n"
        "- Narrative body with sections and inline citations\n"
        "- Gaps and limitations section\n"
        "- Source list at the end\n"
        "- Target 800-1500 words.\n"
    )

    return (
        f"Research topic: {topic}\n\n"
        f"Synthesis draft:\n{draft}\n\n"
        f"Available sources (use [N] for inline citations):\n{numbered_sources}\n\n"
        f"Known limitations:\n{limitations_block}\n\n"
        f"{format_instruction}\n"
        "IMPORTANT: Only cite sources from the list above. "
        "Include all cited source URLs in the cited_source_urls field."
    )


def _parse_tool_call(response: Any) -> ReportOutput:
    """Parse and validate a ReportOutput from the LLM response's tool calls."""
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        raise ValueError("Model returned prose instead of a tool call")

    call = tool_calls[0]
    if call["name"] != "ReportOutput":
        raise ValueError(f"Model called wrong tool: {call['name']}")

    return ReportOutput.model_validate(call["args"])


def _validate_citations(
    report_output: ReportOutput,
    valid_urls: set[str],
    num_sources: int,
) -> list[str]:
    """Check citation integrity. Returns list of violations.

    Checks:
    1. Every URL in cited_source_urls exists in the source list
    2. Every inline [N] marker in body refers to a valid source index
    """
    import re

    violations = []
    for url in report_output.cited_source_urls:
        if url not in valid_urls:
            violations.append(f"Cited URL not in source list: {url}")

    # Check inline markers like [1], [2], etc.
    markers = {int(m) for m in re.findall(r"\[(\d+)\]", report_output.body)}
    for m in sorted(markers):
        if m < 1 or m > num_sources:
            violations.append(f"Inline citation [{m}] has no matching source (only {num_sources} available)")

    return violations


def run_report_agent(
    state: ResearchState,
    config: AppConfig | None = None,
) -> dict:
    """Execute the report agent node.

    1. Gather approved draft, findings, sources
    2. Feed to LLM for structured report generation
    3. Validate citation integrity
    4. Return state update dict
    """
    cfg = config or DEFAULT_CONFIG
    t0 = time.perf_counter()

    # Use edited draft if human reviewer provided one
    approved_draft = (
        state.human_review.edited_draft
        if state.human_review and state.human_review.edited_draft
        else (state.synthesis_draft.draft if state.synthesis_draft else "")
    )

    sources = state.all_sources
    limitations = (
        state.synthesis_draft.limitations if state.synthesis_draft else []
    )

    print(f"\n[report_agent] format={state.report_format}")
    print(f"[report_agent] sources={len(sources)}, draft_len={len(approved_draft)}")

    # --- LLM structured report ---
    if not has_llm_key(cfg) and state.mode != RunMode.DEV:
        raise RuntimeError(
            f"{state.mode.value} mode requires a valid API key for report generation"
        )

    if not has_llm_key(cfg):
        print("[report_agent] no LLM key configured, using stub report (dev mode)")
        report_output, tokens_in, tokens_out = _stub_report(
            state.topic, approved_draft, sources, state.report_format, limitations,
        )
    else:
        report_output, tokens_in, tokens_out = _llm_report(
            topic=state.topic,
            draft=approved_draft,
            sources=sources,
            report_format=state.report_format,
            limitations=limitations,
            cfg=cfg,
        )

    elapsed = time.perf_counter() - t0

    # Citation integrity check — warn but don't fail
    valid_urls = {s.url for s in sources}
    violations = _validate_citations(report_output, valid_urls, len(sources))
    errors = list(state.errors)
    if violations:
        for v in violations:
            print(f"[report_agent] citation warning: {v}")
            errors.append(f"citation: {v}")

    # Filter sources to only those actually cited
    cited_urls = set(report_output.cited_source_urls) & valid_urls
    cited_sources = [s for s in sources if s.url in cited_urls] if cited_urls else sources

    word_count = len(report_output.body.split())
    _warn_word_count(word_count, state.report_format)

    report = FinalReport(
        title=report_output.title,
        executive_summary=report_output.executive_summary,
        body=report_output.body,
        sources=cited_sources,
        format=state.report_format,
        word_count=word_count,
    )

    return {
        "final_report": report,
        "status": GraphStatus.COMPLETE,
        "errors": errors,
        "token_usage": state.token_usage.add(
            report_agent_input=tokens_in,
            report_agent_output=tokens_out,
        ),
        "node_timings": state.node_timings.add(report_agent=elapsed),
    }


def _warn_word_count(word_count: int, fmt: ReportFormat) -> None:
    if fmt == ReportFormat.EXECUTIVE_BRIEF and word_count > 600:
        print(f"[report_agent] warning: executive brief is {word_count} words (target: <500)")
    elif fmt == ReportFormat.DEEP_DIVE and word_count > 2000:
        print(f"[report_agent] warning: deep dive is {word_count} words (target: 800-1500)")


def _stub_report(
    topic: str,
    draft: str,
    sources: list[Source],
    report_format: ReportFormat,
    limitations: list[str],
) -> tuple[ReportOutput, int, int]:
    """Dev-mode stub report generation. Returns (output, input_tokens, output_tokens)."""
    source_urls = [s.url for s in sources]

    cite = " [1]" if sources else ""

    if report_format == ReportFormat.EXECUTIVE_BRIEF:
        body = (
            f"# {topic}\n\n"
            f"## Executive Summary\n\n"
            f"This research examined {topic} across multiple sources{cite}. "
            f"Key findings reveal important trends{cite}. "
            f"Further investigation is recommended.\n\n"
            f"## Key Findings\n\n"
            f"1. {draft[:100]}...{cite}\n"
            f"2. Multiple perspectives were identified{cite}\n"
            f"3. The topic shows ongoing development{cite}\n\n"
            f"## Recommendations\n\n"
            f"- Continue monitoring developments in {topic}\n"
        )
    else:
        lim_section = (
            "## Limitations\n\n"
            + "\n".join(f"- {lim}" for lim in limitations)
            if limitations
            else "## Limitations\n\nNo significant limitations identified."
        )
        source_list = (
            "\n".join(f"- [{i+1}] [{s.title}]({s.url})" for i, s in enumerate(sources))
            if sources else "No sources available."
        )
        body = (
            f"# {topic}\n\n"
            f"## Executive Summary\n\n"
            f"This report presents findings on {topic} based on {len(sources)} sources{cite}.\n\n"
            f"## Analysis\n\n{draft}\n\n"
            f"The research draws from {len(sources)} sources{cite}, "
            f"providing a comprehensive view of the topic.\n\n"
            f"{lim_section}\n\n"
            f"## Sources\n\n{source_list}"
        )

    return ReportOutput(
        title=topic,
        executive_summary=f"Research on {topic} with {len(sources)} sources.",
        body=body,
        cited_source_urls=source_urls[:1] if source_urls else [],
        reasoning="Stub report — no LLM key available.",
    ), 0, 0


def _llm_report(
    topic: str,
    draft: str,
    sources: list[Source],
    report_format: ReportFormat,
    limitations: list[str],
    cfg: AppConfig,
) -> tuple[ReportOutput, int, int]:
    """Call LLM with tool binding and corrective retry. Returns (output, input_tokens, output_tokens)."""
    llm = get_chat_model(cfg)
    llm_with_tool = llm.bind_tools(
        [ReportOutput],
        tool_choice=tool_choice_for("ReportOutput", cfg.llm_provider),
    )

    prompt = _build_report_prompt(topic, draft, sources, report_format, limitations)
    messages: list[Any] = [HumanMessage(content=f"{REPORT_SYSTEM}\n\n{prompt}")]
    total_in = 0
    total_out = 0

    for attempt in range(1, cfg.max_retries + 2):
        response = llm_with_tool.invoke(messages)
        in_tokens, out_tokens = extract_token_usage(response)
        total_in += in_tokens
        total_out += out_tokens

        try:
            output = _parse_tool_call(response)
            print(f"[report_agent] LLM report succeeded (attempt {attempt})")
            return output, total_in, total_out
        except (ValueError, ValidationError) as e:
            if attempt > cfg.max_retries:
                raise RuntimeError(
                    f"Report agent failed after {attempt} attempts: {e}"
                ) from e

            print(f"[report_agent] retry {attempt}/{cfg.max_retries}: {e}")
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
                    "You MUST call the ReportOutput tool. Retry now."
                )
            )

    raise RuntimeError("Report agent retry loop exited unexpectedly")
