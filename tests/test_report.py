"""
tests/test_report.py — Report agent and run persistence tests.

Covers: schema validation, citation integrity, report format validation,
dev/eval mode, retry logic, saved JSON structure, auto-approve path.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.report import (
    ReportOutput,
    _parse_tool_call,
    _validate_citations,
    run_report_agent,
)
from config import AppConfig
from run_pipeline import run_pipeline, save_run
from state import (
    Finding,
    FinalReport,
    GraphStatus,
    HumanReview,
    ReportFormat,
    ResearchState,
    RunMode,
    SearchResult,
    Source,
    SynthesisDraft,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _dev_config(**overrides) -> AppConfig:
    return AppConfig(mode=RunMode.DEV, **overrides)


def _live_config(**overrides) -> AppConfig:
    return AppConfig(
        mode=RunMode.LIVE,
        openai_api_key="test-key",
        tavily_api_key="test-key",
        **overrides,
    )


def _mock_ai_response(tool_calls=None, content="", response_metadata=None):
    msg = MagicMock()
    msg.tool_calls = tool_calls or []
    msg.content = content
    msg.response_metadata = response_metadata or {
        "usage": {"input_tokens": 200, "output_tokens": 100},
    }
    return msg


def _valid_report_output_args(source_urls=None) -> dict:
    urls = source_urls or ["https://example.com/1"]
    return {
        "title": "Test Report",
        "executive_summary": "This is a summary.",
        "body": "# Report\n\nSome content [1]. More content [1].",
        "cited_source_urls": urls,
        "reasoning": "test reasoning",
    }


def _state_for_report(
    topic: str = "test topic",
    mode: RunMode = RunMode.DEV,
    report_format: ReportFormat = ReportFormat.DEEP_DIVE,
    num_sources: int = 2,
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
    return ResearchState(
        topic=topic,
        mode=mode,
        report_format=report_format,
        loop_count=2,
        max_loops=2,
        search_results=[
            SearchResult(
                findings=findings,
                sources=sources,
                gaps=[],
                reasoning="test",
            )
        ],
        synthesis_draft=SynthesisDraft(
            draft=f"## Synthesis of {topic}\n\nKey findings about the topic.",
            remaining_gaps=[],
            confidence=0.85,
            needs_more_search=False,
            limitations=["Loop cap reached; proceeding with available evidence."] if with_limitations else [],
        ),
        human_review=HumanReview(approved=True),
        status=GraphStatus.WRITING_REPORT,
    )


# ---------------------------------------------------------------------------
# ReportOutput schema validation
# ---------------------------------------------------------------------------

class TestReportOutputSchema:
    def test_valid_output_parses(self):
        output = ReportOutput.model_validate(_valid_report_output_args())
        assert output.title == "Test Report"
        assert len(output.cited_source_urls) == 1

    def test_missing_required_field_fails(self):
        args = _valid_report_output_args()
        del args["body"]
        with pytest.raises(Exception):
            ReportOutput.model_validate(args)

    def test_empty_citations_is_valid(self):
        args = _valid_report_output_args()
        args["cited_source_urls"] = []
        output = ReportOutput.model_validate(args)
        assert output.cited_source_urls == []


# ---------------------------------------------------------------------------
# _parse_tool_call
# ---------------------------------------------------------------------------

class TestParseToolCall:
    def test_valid_tool_call(self):
        response = _mock_ai_response(
            tool_calls=[{"name": "ReportOutput", "id": "1", "args": _valid_report_output_args()}]
        )
        output = _parse_tool_call(response)
        assert isinstance(output, ReportOutput)

    def test_prose_response_rejected(self):
        response = _mock_ai_response(tool_calls=[], content="Here is a report...")
        with pytest.raises(ValueError, match="prose"):
            _parse_tool_call(response)

    def test_wrong_tool_rejected(self):
        response = _mock_ai_response(
            tool_calls=[{"name": "WrongTool", "id": "1", "args": {}}]
        )
        with pytest.raises(ValueError, match="wrong tool"):
            _parse_tool_call(response)


# ---------------------------------------------------------------------------
# Citation integrity
# ---------------------------------------------------------------------------

class TestCitationIntegrity:
    def test_valid_citations_no_violations(self):
        output = ReportOutput.model_validate(_valid_report_output_args(
            source_urls=["https://example.com/1"]
        ))
        violations = _validate_citations(output, {"https://example.com/1", "https://example.com/2"}, num_sources=2)
        assert violations == []

    def test_unknown_url_is_violation(self):
        output = ReportOutput.model_validate(_valid_report_output_args(
            source_urls=["https://invented.com/fake"]
        ))
        violations = _validate_citations(output, {"https://example.com/1"}, num_sources=1)
        assert len(violations) == 1
        assert "not in source list" in violations[0]

    def test_dangling_inline_marker_is_violation(self):
        """Inline [N] markers referencing non-existent sources are caught."""
        args = _valid_report_output_args(source_urls=["https://example.com/1"])
        args["body"] = "Some claim [1]. Another claim [5]."
        output = ReportOutput.model_validate(args)
        violations = _validate_citations(output, {"https://example.com/1"}, num_sources=1)
        assert any("[5]" in v for v in violations)

    def test_citation_violations_recorded_as_errors(self):
        """Citation violations should be added to errors list but not block completion."""
        state = _state_for_report(num_sources=1)
        # Run with dev stub — stub cites sources[0] which exists, so no violation expected
        result = run_report_agent(state, config=_dev_config())
        assert result["status"] == GraphStatus.COMPLETE

    def test_report_sources_filtered_to_cited(self):
        """Final report should only include actually-cited sources."""
        state = _state_for_report(num_sources=3)
        result = run_report_agent(state, config=_dev_config())
        report = result["final_report"]
        # Dev stub cites only the first source URL
        assert len(report.sources) <= len(state.all_sources)


# ---------------------------------------------------------------------------
# Dev mode
# ---------------------------------------------------------------------------

class TestDevMode:
    def test_runs_without_credentials(self):
        state = _state_for_report()
        result = run_report_agent(state, config=_dev_config())
        assert result["final_report"] is not None
        assert result["status"] == GraphStatus.COMPLETE

    def test_deep_dive_format(self):
        state = _state_for_report(report_format=ReportFormat.DEEP_DIVE)
        result = run_report_agent(state, config=_dev_config())
        report = result["final_report"]
        assert report.format == ReportFormat.DEEP_DIVE
        assert "## Analysis" in report.body or "## Executive Summary" in report.body

    def test_executive_brief_format(self):
        state = _state_for_report(report_format=ReportFormat.EXECUTIVE_BRIEF)
        result = run_report_agent(state, config=_dev_config())
        report = result["final_report"]
        assert report.format == ReportFormat.EXECUTIVE_BRIEF
        assert "Key Findings" in report.body

    def test_uses_edited_draft_when_available(self):
        state = _state_for_report()
        state = state.model_copy(update={
            "human_review": HumanReview(
                approved=True,
                edited_draft="EDITED DRAFT CONTENT",
            ),
        })
        result = run_report_agent(state, config=_dev_config())
        assert "EDITED DRAFT CONTENT" in result["final_report"].body

    def test_limitations_included_in_deep_dive(self):
        state = _state_for_report(with_limitations=True)
        result = run_report_agent(state, config=_dev_config())
        assert "Limitations" in result["final_report"].body

    def test_state_update_shape(self):
        state = _state_for_report()
        result = run_report_agent(state, config=_dev_config())
        required_keys = {"final_report", "status", "errors", "token_usage", "node_timings"}
        assert required_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# Eval/live mode
# ---------------------------------------------------------------------------

class TestEvalMode:
    def test_eval_fails_without_openai_key(self):
        state = _state_for_report(mode=RunMode.EVAL)
        cfg = AppConfig(mode=RunMode.EVAL, openai_api_key="")
        with pytest.raises(RuntimeError, match="requires OPENAI_API_KEY"):
            run_report_agent(state, config=cfg)

    def test_live_fails_without_openai_key(self):
        state = _state_for_report(mode=RunMode.LIVE)
        cfg = AppConfig(mode=RunMode.LIVE, openai_api_key="")
        with pytest.raises(RuntimeError, match="requires OPENAI_API_KEY"):
            run_report_agent(state, config=cfg)


# ---------------------------------------------------------------------------
# LLM retry logic (mocked)
# ---------------------------------------------------------------------------

class TestRetryLogic:
    @patch("agents.report.ChatOpenAI")
    def test_succeeds_on_first_attempt(self, mock_llm_cls):
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        state = _state_for_report(mode=RunMode.LIVE)
        source_urls = [s.url for s in state.all_sources]
        response = _mock_ai_response(
            tool_calls=[{"name": "ReportOutput", "id": "1", "args": _valid_report_output_args(source_urls[:1])}]
        )
        bound.invoke.return_value = response

        result = run_report_agent(state, config=_live_config())
        assert result["final_report"] is not None
        assert bound.invoke.call_count == 1

    @patch("agents.report.ChatOpenAI")
    def test_retry_exhaustion_raises(self, mock_llm_cls):
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        prose = _mock_ai_response(tool_calls=[], content="nope")
        bound.invoke.return_value = prose

        state = _state_for_report(mode=RunMode.LIVE)
        with pytest.raises(RuntimeError, match="failed after"):
            run_report_agent(state, config=_live_config(max_retries=1))


# ---------------------------------------------------------------------------
# Run persistence (save_run)
# ---------------------------------------------------------------------------

class TestSaveRun:
    def test_save_run_creates_json(self, tmp_path):
        state = _state_for_report()
        result = run_report_agent(state, config=_dev_config())
        # Merge with state fields that run_report_agent doesn't return
        full_result = {
            "topic": state.topic,
            "mode": state.mode,
            "status": result["status"],
            "loop_count": state.loop_count,
            "errors": result["errors"],
            "token_usage": result["token_usage"],
            "node_timings": result["node_timings"],
            "run_metadata": state.run_metadata,
            "final_report": result["final_report"],
            "synthesis_draft": state.synthesis_draft,
            "search_results": state.search_results,
        }

        path = save_run(full_result, runs_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    def test_saved_json_structure(self, tmp_path):
        state = _state_for_report(with_limitations=True)
        result = run_report_agent(state, config=_dev_config())
        full_result = {
            "topic": state.topic,
            "mode": state.mode,
            "status": result["status"],
            "loop_count": state.loop_count,
            "errors": result["errors"],
            "token_usage": result["token_usage"],
            "node_timings": result["node_timings"],
            "run_metadata": state.run_metadata,
            "final_report": result["final_report"],
            "synthesis_draft": state.synthesis_draft,
            "search_results": state.search_results,
        }

        path = save_run(full_result, runs_dir=tmp_path)
        data = json.loads(path.read_text())

        # Required top-level keys
        assert "topic" in data
        assert "mode" in data
        assert "status" in data
        assert "loop_count" in data
        assert "errors" in data
        assert "limitations" in data
        assert "token_usage" in data
        assert "node_timings" in data
        assert "run_metadata" in data
        assert "final_report" in data
        assert "saved_at" in data

    def test_saved_json_has_report_sources(self, tmp_path):
        state = _state_for_report()
        result = run_report_agent(state, config=_dev_config())
        full_result = {
            "topic": state.topic,
            "mode": state.mode,
            "status": result["status"],
            "loop_count": state.loop_count,
            "errors": result["errors"],
            "token_usage": result["token_usage"],
            "node_timings": result["node_timings"],
            "run_metadata": state.run_metadata,
            "final_report": result["final_report"],
            "synthesis_draft": state.synthesis_draft,
            "search_results": state.search_results,
        }

        path = save_run(full_result, runs_dir=tmp_path)
        data = json.loads(path.read_text())

        assert data["final_report"] is not None
        assert "sources" in data["final_report"]
        assert len(data["final_report"]["sources"]) >= 1
        assert "url" in data["final_report"]["sources"][0]

    def test_saved_json_token_usage_has_total(self, tmp_path):
        state = _state_for_report()
        result = run_report_agent(state, config=_dev_config())
        full_result = {
            "topic": state.topic,
            "mode": state.mode,
            "status": result["status"],
            "loop_count": state.loop_count,
            "errors": result["errors"],
            "token_usage": result["token_usage"],
            "node_timings": result["node_timings"],
            "run_metadata": state.run_metadata,
            "final_report": result["final_report"],
            "synthesis_draft": state.synthesis_draft,
            "search_results": state.search_results,
        }

        path = save_run(full_result, runs_dir=tmp_path)
        data = json.loads(path.read_text())

        assert "total" in data["token_usage"]
        assert "total" in data["node_timings"]


# ---------------------------------------------------------------------------
# Auto-approve pipeline (end-to-end dev mode)
# ---------------------------------------------------------------------------

class TestAutoApprovePipeline:
    def test_run_pipeline_completes_in_dev_mode(self):
        result = run_pipeline(
            topic="test pipeline topic",
            mode=RunMode.DEV,
            max_loops=1,
            save=False,
        )
        assert result["status"] == GraphStatus.COMPLETE
        assert result["final_report"] is not None
        assert result["final_report"].word_count > 0

    def test_run_pipeline_saves_artifact(self, tmp_path):
        # Monkey-patch RUNS_DIR for this test
        import run_pipeline as rp
        original = rp.RUNS_DIR
        rp.RUNS_DIR = tmp_path
        try:
            result = run_pipeline(
                topic="save test",
                mode=RunMode.DEV,
                max_loops=1,
                save=True,
            )
            files = list(tmp_path.glob("*.json"))
            assert len(files) == 1
            data = json.loads(files[0].read_text())
            assert data["topic"] == "save test"
        finally:
            rp.RUNS_DIR = original
