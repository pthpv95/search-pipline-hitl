"""
tests/test_synthesis.py — Synthesis agent tests.

Tests structured output parsing, retry logic, dev/eval mode behavior,
loop cap enforcement, limitations recording, and routing decisions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.synthesis import (
    SynthesisOutput,
    _parse_tool_call,
    run_synthesis_agent,
)
from config import AppConfig
from state import (
    Finding,
    GraphStatus,
    ResearchState,
    RunMode,
    SearchResult,
    Source,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _dev_config(**overrides) -> AppConfig:
    return AppConfig(mode=RunMode.DEV, **overrides)


def _live_config(**overrides) -> AppConfig:
    return AppConfig(
        mode=RunMode.LIVE,
        anthropic_api_key="test-key",
        tavily_api_key="test-key",
        **overrides,
    )


def _mock_ai_response(tool_calls=None, content="", response_metadata=None):
    msg = MagicMock()
    msg.tool_calls = tool_calls or []
    msg.content = content
    msg.response_metadata = response_metadata or {
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    return msg


def _valid_synthesis_output_args() -> dict:
    return {
        "draft": "## Synthesis\n\nKey findings about the topic.",
        "remaining_gaps": ["gap 1"],
        "confidence": 0.75,
        "needs_more_search": True,
        "follow_up_queries": ["follow up query 1"],
        "limitations": [],
        "reasoning": "test reasoning",
    }


def _state_with_findings(
    topic: str = "test topic",
    mode: RunMode = RunMode.DEV,
    loop_count: int = 1,
    max_loops: int = 2,
    num_findings: int = 1,
) -> ResearchState:
    findings = [
        Finding(
            content=f"Finding {i+1} about {topic}",
            source_url=f"https://example.com/{i+1}",
            confidence=0.8,
        )
        for i in range(num_findings)
    ]
    sources = [
        Source(
            url=f"https://example.com/{i+1}",
            title=f"Source {i+1}",
            snippet=f"Snippet {i+1}",
            relevance_score=0.8,
            source_type="mock",
        )
        for i in range(num_findings)
    ]
    return ResearchState(
        topic=topic,
        mode=mode,
        loop_count=loop_count,
        max_loops=max_loops,
        search_results=[
            SearchResult(
                findings=findings,
                sources=sources,
                gaps=["existing gap"],
                reasoning="test",
            )
        ],
    )


# ---------------------------------------------------------------------------
# SynthesisOutput schema validation
# ---------------------------------------------------------------------------

class TestSynthesisOutputSchema:
    def test_valid_output_parses(self):
        output = SynthesisOutput.model_validate(_valid_synthesis_output_args())
        assert output.draft.startswith("## Synthesis")
        assert output.needs_more_search is True
        assert len(output.follow_up_queries) == 1

    def test_missing_required_field_fails(self):
        args = _valid_synthesis_output_args()
        del args["reasoning"]
        with pytest.raises(Exception):
            SynthesisOutput.model_validate(args)

    def test_confidence_bounds_enforced(self):
        args = _valid_synthesis_output_args()
        args["confidence"] = 1.5
        with pytest.raises(Exception):
            SynthesisOutput.model_validate(args)

    def test_no_search_needed_is_valid(self):
        args = _valid_synthesis_output_args()
        args["needs_more_search"] = False
        args["remaining_gaps"] = []
        args["follow_up_queries"] = []
        output = SynthesisOutput.model_validate(args)
        assert output.needs_more_search is False


# ---------------------------------------------------------------------------
# _parse_tool_call
# ---------------------------------------------------------------------------

class TestParseToolCall:
    def test_valid_tool_call(self):
        response = _mock_ai_response(
            tool_calls=[{"name": "SynthesisOutput", "id": "1", "args": _valid_synthesis_output_args()}]
        )
        output = _parse_tool_call(response)
        assert isinstance(output, SynthesisOutput)

    def test_prose_response_rejected(self):
        response = _mock_ai_response(tool_calls=[], content="Here is a synthesis...")
        with pytest.raises(ValueError, match="prose"):
            _parse_tool_call(response)

    def test_wrong_tool_rejected(self):
        response = _mock_ai_response(
            tool_calls=[{"name": "WrongTool", "id": "1", "args": {}}]
        )
        with pytest.raises(ValueError, match="wrong tool"):
            _parse_tool_call(response)

    def test_invalid_args_rejected(self):
        response = _mock_ai_response(
            tool_calls=[{"name": "SynthesisOutput", "id": "1", "args": {"bad": "data"}}]
        )
        with pytest.raises(Exception):
            _parse_tool_call(response)


# ---------------------------------------------------------------------------
# Dev mode — no API keys needed
# ---------------------------------------------------------------------------

class TestDevMode:
    def test_runs_without_credentials(self):
        state = _state_with_findings()
        result = run_synthesis_agent(state, config=_dev_config())

        assert result["synthesis_draft"] is not None
        assert result["synthesis_draft"].draft != ""
        assert "token_usage" in result
        assert "node_timings" in result

    def test_state_update_shape(self):
        state = _state_with_findings()
        result = run_synthesis_agent(state, config=_dev_config())

        required_keys = {"synthesis_draft", "current_queries", "status", "token_usage", "node_timings"}
        assert required_keys.issubset(result.keys())

    def test_dev_stub_wants_more_search_when_few_findings(self):
        state = _state_with_findings(loop_count=1, max_loops=3, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())

        assert result["synthesis_draft"].needs_more_search is True
        assert len(result["current_queries"]) > 0
        assert result["status"] == GraphStatus.SEARCHING

    def test_dev_stub_sufficient_when_many_findings(self):
        state = _state_with_findings(loop_count=1, max_loops=3, num_findings=6)
        result = run_synthesis_agent(state, config=_dev_config())

        assert result["synthesis_draft"].needs_more_search is False
        assert result["status"] == GraphStatus.AWAITING_HUMAN


# ---------------------------------------------------------------------------
# Eval mode — must fail without credentials
# ---------------------------------------------------------------------------

class TestEvalMode:
    def test_eval_fails_without_llm_key(self):
        state = _state_with_findings(mode=RunMode.EVAL)
        cfg = AppConfig(mode=RunMode.EVAL, anthropic_api_key="")
        with pytest.raises(RuntimeError, match="requires a valid API key"):
            run_synthesis_agent(state, config=cfg)

    def test_live_fails_without_llm_key(self):
        state = _state_with_findings(mode=RunMode.LIVE)
        cfg = AppConfig(mode=RunMode.LIVE, anthropic_api_key="")
        with pytest.raises(RuntimeError, match="requires a valid API key"):
            run_synthesis_agent(state, config=cfg)


# ---------------------------------------------------------------------------
# Loop cap enforcement
# ---------------------------------------------------------------------------

class TestLoopCap:
    def test_loop_cap_forces_no_more_search(self):
        """When loop_count == max_loops, needs_more_search must be False."""
        state = _state_with_findings(loop_count=2, max_loops=2, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())

        draft = result["synthesis_draft"]
        assert draft.needs_more_search is False
        assert result["status"] == GraphStatus.AWAITING_HUMAN

    def test_loop_cap_records_limitations(self):
        """When loop cap blocks further search, a limitation should be recorded."""
        state = _state_with_findings(loop_count=2, max_loops=2, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())

        draft = result["synthesis_draft"]
        assert any("loop cap" in lim.lower() for lim in draft.limitations)

    def test_under_loop_cap_allows_more_search(self):
        state = _state_with_findings(loop_count=1, max_loops=3, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())

        draft = result["synthesis_draft"]
        assert draft.needs_more_search is True
        assert result["status"] == GraphStatus.SEARCHING


# ---------------------------------------------------------------------------
# Routing decisions
# ---------------------------------------------------------------------------

class TestRouting:
    def test_routes_to_search_when_gaps_and_needs_more(self):
        state = _state_with_findings(loop_count=1, max_loops=3, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())
        assert result["status"] == GraphStatus.SEARCHING

    def test_routes_to_human_when_sufficient(self):
        state = _state_with_findings(loop_count=1, max_loops=3, num_findings=6)
        result = run_synthesis_agent(state, config=_dev_config())
        assert result["status"] == GraphStatus.AWAITING_HUMAN

    def test_routes_to_human_when_at_loop_cap(self):
        state = _state_with_findings(loop_count=2, max_loops=2, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())
        assert result["status"] == GraphStatus.AWAITING_HUMAN

    def test_follow_up_queries_used_as_current_queries(self):
        """current_queries should be follow_up_queries, not remaining_gaps."""
        state = _state_with_findings(loop_count=1, max_loops=3, num_findings=1)
        result = run_synthesis_agent(state, config=_dev_config())

        draft = result["synthesis_draft"]
        if draft.follow_up_queries:
            assert result["current_queries"] == draft.follow_up_queries


# ---------------------------------------------------------------------------
# LLM retry logic (mocked)
# ---------------------------------------------------------------------------

class TestRetryLogic:
    @patch("agents.synthesis.get_chat_model")
    def test_succeeds_on_first_attempt(self, mock_get_chat_model):
        mock_llm = MagicMock()
        mock_get_chat_model.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        response = _mock_ai_response(
            tool_calls=[{"name": "SynthesisOutput", "id": "1", "args": _valid_synthesis_output_args()}]
        )
        bound.invoke.return_value = response

        state = _state_with_findings(mode=RunMode.LIVE)
        result = run_synthesis_agent(state, config=_live_config())

        assert result["synthesis_draft"] is not None
        assert bound.invoke.call_count == 1

    @patch("agents.synthesis.get_chat_model")
    def test_retries_on_prose_then_succeeds(self, mock_get_chat_model):
        from langchain_core.messages import ToolMessage as TM

        mock_llm = MagicMock()
        mock_get_chat_model.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        prose_response = _mock_ai_response(tool_calls=[], content="Just some text")
        valid_response = _mock_ai_response(
            tool_calls=[{"name": "SynthesisOutput", "id": "2", "args": _valid_synthesis_output_args()}]
        )
        bound.invoke.side_effect = [prose_response, valid_response]

        state = _state_with_findings(mode=RunMode.LIVE)
        result = run_synthesis_agent(state, config=_live_config(max_retries=2))

        assert result["synthesis_draft"] is not None
        assert bound.invoke.call_count == 2

        # No ToolMessage for prose retry
        retry_messages = bound.invoke.call_args_list[1][0][0]
        assert not any(isinstance(m, TM) for m in retry_messages)

    @patch("agents.synthesis.get_chat_model")
    def test_retry_exhaustion_raises(self, mock_get_chat_model):
        mock_llm = MagicMock()
        mock_get_chat_model.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        prose = _mock_ai_response(tool_calls=[], content="nope")
        bound.invoke.return_value = prose

        state = _state_with_findings(mode=RunMode.LIVE)
        with pytest.raises(RuntimeError, match="failed after"):
            run_synthesis_agent(state, config=_live_config(max_retries=1))

    @patch("agents.synthesis.get_chat_model")
    def test_token_usage_accumulated_across_retries(self, mock_get_chat_model):
        mock_llm = MagicMock()
        mock_get_chat_model.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        prose = _mock_ai_response(
            tool_calls=[], content="nope",
            response_metadata={"usage": {"input_tokens": 100, "output_tokens": 50}},
        )
        valid = _mock_ai_response(
            tool_calls=[{"name": "SynthesisOutput", "id": "2", "args": _valid_synthesis_output_args()}],
            response_metadata={"usage": {"input_tokens": 200, "output_tokens": 100}},
        )
        bound.invoke.side_effect = [prose, valid]

        state = _state_with_findings(mode=RunMode.LIVE)
        result = run_synthesis_agent(state, config=_live_config(max_retries=2))

        # 150 from first attempt + 300 from second = 450
        assert result["token_usage"].synthesis_agent == 450

    @patch("agents.synthesis.get_chat_model")
    def test_llm_loop_cap_override(self, mock_get_chat_model):
        """Even if LLM says needs_more_search=True, loop cap forces it False."""
        mock_llm = MagicMock()
        mock_get_chat_model.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        args = _valid_synthesis_output_args()
        args["needs_more_search"] = True
        args["remaining_gaps"] = ["still need info"]
        response = _mock_ai_response(
            tool_calls=[{"name": "SynthesisOutput", "id": "1", "args": args}]
        )
        bound.invoke.return_value = response

        # At loop cap
        state = _state_with_findings(mode=RunMode.LIVE, loop_count=2, max_loops=2)
        result = run_synthesis_agent(state, config=_live_config())

        assert result["synthesis_draft"].needs_more_search is False
        assert result["status"] == GraphStatus.AWAITING_HUMAN
        assert any("loop cap" in lim.lower() for lim in result["synthesis_draft"].limitations)
