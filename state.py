"""
state.py — typed graph state and supporting models.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class RunMode(str, Enum):
    DEV = "dev"
    LIVE = "live"
    EVAL = "eval"


class ReportFormat(str, Enum):
    EXECUTIVE_BRIEF = "executive_brief"
    DEEP_DIVE = "deep_dive"


class GraphStatus(str, Enum):
    INITIALIZING = "initializing"
    SEARCHING = "searching"
    SYNTHESIZING = "synthesizing"
    AWAITING_HUMAN = "awaiting_human"
    WRITING_REPORT = "writing_report"
    COMPLETE = "complete"
    FAILED = "failed"


class Source(BaseModel):
    url: str
    title: str
    snippet: str
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_type: str = "mock"


class Finding(BaseModel):
    content: str
    source_url: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    follow_up_queries: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    reasoning: str = ""
    tokens_used: int = 0


class SynthesisDraft(BaseModel):
    draft: str
    remaining_gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    needs_more_search: bool = False
    follow_up_queries: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class HumanReview(BaseModel):
    approved: bool = False
    rejected: bool = False
    edited_draft: str | None = None
    additional_queries: list[str] = Field(default_factory=list)
    notes: str = ""
    rejection_reason: str = ""


class FinalReport(BaseModel):
    title: str
    executive_summary: str
    body: str
    sources: list[Source] = Field(default_factory=list)
    format: ReportFormat = ReportFormat.DEEP_DIVE
    word_count: int = 0


class TokenUsage(BaseModel):
    search_agent: int = 0
    synthesis_agent: int = 0
    report_agent: int = 0

    @property
    def total(self) -> int:
        return self.search_agent + self.synthesis_agent + self.report_agent

    def add(self, **kwargs: int) -> "TokenUsage":
        updates = {k: getattr(self, k) + v for k, v in kwargs.items()}
        return self.model_copy(update=updates)


class NodeTiming(BaseModel):
    search_agent: float = 0.0
    synthesis_agent: float = 0.0
    report_agent: float = 0.0
    human_review: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.search_agent
            + self.synthesis_agent
            + self.report_agent
            + self.human_review
        )

    def add(self, **kwargs: float) -> "NodeTiming":
        updates = {k: getattr(self, k) + v for k, v in kwargs.items()}
        return self.model_copy(update=updates)


class RunMetadata(BaseModel):
    model_name: str = "stub-model"
    search_provider: str = "stub-search"
    thread_id: str | None = None


class ResearchState(BaseModel):
    topic: str = ""
    mode: RunMode = RunMode.DEV
    report_format: ReportFormat = ReportFormat.DEEP_DIVE

    search_results: list[SearchResult] = Field(default_factory=list)
    current_queries: list[str] = Field(default_factory=list)
    loop_count: int = 0
    max_loops: int = 2

    synthesis_draft: SynthesisDraft | None = None
    human_review: HumanReview | None = None
    final_report: FinalReport | None = None

    status: GraphStatus = GraphStatus.INITIALIZING
    errors: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    node_timings: NodeTiming = Field(default_factory=NodeTiming)
    run_metadata: RunMetadata = Field(default_factory=RunMetadata)

    messages: Annotated[list[Any], add_messages] = Field(default_factory=list)

    @property
    def all_findings(self) -> list[Finding]:
        return [finding for result in self.search_results for finding in result.findings]

    @property
    def all_sources(self) -> list[Source]:
        seen: set[str] = set()
        sources: list[Source] = []
        for result in self.search_results:
            for source in result.sources:
                if source.url in seen:
                    continue
                seen.add(source.url)
                sources.append(source)
        return sources

    @property
    def latest_gaps(self) -> list[str]:
        if self.synthesis_draft is None:
            return []
        return self.synthesis_draft.remaining_gaps

    @property
    def should_search_again(self) -> bool:
        if self.synthesis_draft is None:
            return False
        if self.loop_count >= self.max_loops:
            return False
        return self.synthesis_draft.needs_more_search and bool(
            self.synthesis_draft.remaining_gaps
        )

    def with_error(self, msg: str) -> "ResearchState":
        return self.model_copy(
            update={
                "errors": self.errors + [msg],
                "status": GraphStatus.FAILED,
            }
        )
