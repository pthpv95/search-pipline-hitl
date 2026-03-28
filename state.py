"""
state.py — The single source of truth for the entire graph.

Every node reads from and writes to this schema.
Keeping it here, typed, and strict prevents an entire class of bugs
where nodes pass data to each other in inconsistent shapes.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Sub-models — the building blocks of the state
# ---------------------------------------------------------------------------

class Source(BaseModel):
    """A single source found during web search."""
    url: str
    title: str
    snippet: str                        # Short excerpt from the page
    relevance_score: float = Field(ge=0.0, le=1.0, default=0.5)


class Finding(BaseModel):
    """A single extracted fact or insight from search results."""
    content: str                        # The actual finding
    source_url: str                     # Which source this came from
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class SearchResult(BaseModel):
    """Structured output from the search agent — one per search iteration."""
    findings: list[Finding]
    gaps: list[str]                     # Unanswered questions the agent detected
    follow_up_queries: list[str]        # Queries to fill those gaps
    sources: list[Source]
    tokens_used: int = 0


class SynthesisDraft(BaseModel):
    """Structured output from the synthesis agent."""
    draft: str                          # The actual synthesis text (markdown)
    remaining_gaps: list[str]           # Gaps still unresolved after this round
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    needs_more_search: bool = False     # Whether another search loop is warranted


class HumanReview(BaseModel):
    """What the human provided during the HITL checkpoint."""
    approved: bool
    edited_draft: str | None = None     # If the human edited the synthesis
    additional_queries: list[str] = []  # If the human wants more research
    notes: str = ""                     # Free-form feedback


class FinalReport(BaseModel):
    """The finished output from the report agent."""
    title: str
    executive_summary: str
    body: str                           # Full markdown report
    sources: list[Source]
    format: str = "deep_dive"           # "executive_brief" | "deep_dive"
    word_count: int = 0


class TokenUsage(BaseModel):
    """Cost tracking — filled in by each node as it runs."""
    search_agent: int = 0
    synthesis_agent: int = 0
    report_agent: int = 0

    @property
    def total(self) -> int:
        return self.search_agent + self.synthesis_agent + self.report_agent


# ---------------------------------------------------------------------------
# Report format enum — controls report agent behavior
# ---------------------------------------------------------------------------

class ReportFormat(str, Enum):
    EXECUTIVE_BRIEF = "executive_brief"   # ~1 page, key points only
    DEEP_DIVE = "deep_dive"               # Full report with all sources


# ---------------------------------------------------------------------------
# Graph status — lets you inspect what the graph is doing at any point
# ---------------------------------------------------------------------------

class GraphStatus(str, Enum):
    INITIALIZING = "initializing"
    SEARCHING = "searching"
    SYNTHESIZING = "synthesizing"
    AWAITING_HUMAN = "awaiting_human"
    WRITING_REPORT = "writing_report"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# The main state — this is what flows through every node
# ---------------------------------------------------------------------------

class ResearchState(BaseModel):
    """
    The complete state of one research run.

    Design rules:
    - Nodes must only write to fields they own (see comments below).
    - Never mutate a list in place — always return a new list.
    - All fields have defaults so any node can be tested in isolation.
    """

    # -- Input (set at graph initialization, never changed after) -----------
    topic: str = ""
    report_format: ReportFormat = ReportFormat.DEEP_DIVE

    # -- Search agent state -------------------------------------------------
    search_results: list[SearchResult] = Field(default_factory=list)
    current_queries: list[str] = Field(default_factory=list)
    loop_count: int = 0                 # How many search→synthesis iterations
    max_loops: int = 2                  # Hard cap — prevents infinite loops

    # -- Synthesis agent state ----------------------------------------------
    synthesis_draft: SynthesisDraft | None = None

    # -- HITL checkpoint state ----------------------------------------------
    human_review: HumanReview | None = None

    # -- Report agent state -------------------------------------------------
    final_report: FinalReport | None = None

    # -- Operational metadata (filled by every node) ------------------------
    status: GraphStatus = GraphStatus.INITIALIZING
    errors: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)

    # -- LangGraph messages (for nodes that use chat history internally) ----
    # add_messages is a LangGraph reducer that appends instead of replacing.
    # You won't need this until Week 3+ but it's good to wire up now.
    messages: Annotated[list[Any], add_messages] = Field(default_factory=list)

    # -----------------------------------------------------------------------
    # Convenience helpers — keep logic out of nodes, in the state model
    # -----------------------------------------------------------------------

    @property
    def all_findings(self) -> list[Finding]:
        """Flatten findings across all search rounds."""
        return [f for result in self.search_results for f in result.findings]

    @property
    def all_sources(self) -> list[Source]:
        """Deduplicated sources across all search rounds."""
        seen: set[str] = set()
        sources: list[Source] = []
        for result in self.search_results:
            for s in result.sources:
                if s.url not in seen:
                    seen.add(s.url)
                    sources.append(s)
        return sources

    @property
    def should_search_again(self) -> bool:
        """
        True if another search loop is warranted.
        Checked by the conditional edge after synthesis.
        """
        if self.loop_count >= self.max_loops:
            return False
        if self.synthesis_draft is None:
            return False
        return self.synthesis_draft.needs_more_search

    @property
    def latest_gaps(self) -> list[str]:
        """Gaps from the most recent synthesis — what to search for next."""
        if self.synthesis_draft is None:
            return []
        return self.synthesis_draft.remaining_gaps

    def with_error(self, msg: str) -> "ResearchState":
        """Return a copy of state with an error appended. Use in except blocks."""
        return self.model_copy(update={
            "errors": self.errors + [msg],
            "status": GraphStatus.FAILED,
        })
