"""
tests/test_agents.py — Search agent tests.

Tests structured output parsing, retry logic, dev/eval mode behavior,
and state update shape. No real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.search import (
    SearchOutput,
    _parse_tool_call,
    run_search_agent,
)
from config import AppConfig
from state import (
    Finding,
    GraphStatus,
    ResearchState,
    RunMode,
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


def _eval_config(**overrides) -> AppConfig:
    return AppConfig(
        mode=RunMode.EVAL,
        anthropic_api_key="test-key",
        tavily_api_key="test-key",
        **overrides,
    )


def _mock_ai_response(tool_calls=None, content="", response_metadata=None):
    """Build a fake AIMessage-like object."""
    msg = MagicMock()
    msg.tool_calls = tool_calls or []
    msg.content = content
    msg.response_metadata = response_metadata or {
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    return msg


def _valid_search_output_args() -> dict:
    return {
        "findings": [
            {"content": "Test finding", "source_url": "https://example.com", "confidence": 0.9}
        ],
        "gaps": ["remaining gap"],
        "follow_up_queries": ["follow up query"],
        "sources": [
            {"url": "https://example.com", "title": "Test", "snippet": "snippet", "relevance_score": 0.8, "source_type": "live"}
        ],
        "reasoning": "test reasoning",
    }


# ---------------------------------------------------------------------------
# SearchOutput schema validation
# ---------------------------------------------------------------------------

class TestSearchOutputSchema:
    def test_valid_output_parses(self):
        output = SearchOutput.model_validate(_valid_search_output_args())
        assert len(output.findings) == 1
        assert output.reasoning == "test reasoning"

    def test_missing_required_field_fails(self):
        args = _valid_search_output_args()
        del args["reasoning"]
        with pytest.raises(Exception):
            SearchOutput.model_validate(args)

    def test_empty_findings_is_valid(self):
        args = _valid_search_output_args()
        args["findings"] = []
        output = SearchOutput.model_validate(args)
        assert output.findings == []


# ---------------------------------------------------------------------------
# _parse_tool_call
# ---------------------------------------------------------------------------

class TestParseToolCall:
    def test_valid_tool_call(self):
        response = _mock_ai_response(
            tool_calls=[{"name": "SearchOutput", "id": "1", "args": _valid_search_output_args()}]
        )
        output = _parse_tool_call(response)
        assert isinstance(output, SearchOutput)

    def test_prose_response_rejected(self):
        response = _mock_ai_response(tool_calls=[], content="Here are some findings...")
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
            tool_calls=[{"name": "SearchOutput", "id": "1", "args": {"bad": "data"}}]
        )
        with pytest.raises(Exception):
            _parse_tool_call(response)


# ---------------------------------------------------------------------------
# Dev mode — no API keys needed
# ---------------------------------------------------------------------------

class TestDevMode:
    def test_runs_without_credentials(self):
        state = ResearchState(topic="test topic", mode=RunMode.DEV, max_loops=1)
        cfg = _dev_config()
        result = run_search_agent(state, config=cfg)

        assert result["status"] == GraphStatus.SYNTHESIZING
        assert result["loop_count"] == 1
        assert len(result["search_results"]) == 1

        sr = result["search_results"][0]
        assert len(sr.findings) >= 1
        assert len(sr.sources) >= 1
        assert all(s.source_type == "mock" for s in sr.sources)

    def test_state_update_shape(self):
        state = ResearchState(topic="shape test", mode=RunMode.DEV, max_loops=2)
        result = run_search_agent(state, config=_dev_config())

        required_keys = {"search_results", "loop_count", "status", "current_queries", "token_usage", "node_timings"}
        assert required_keys.issubset(result.keys())

    def test_immutable_accumulation(self):
        """search_results should accumulate, not replace."""
        state = ResearchState(topic="accum test", mode=RunMode.DEV, max_loops=3)
        r1 = run_search_agent(state, config=_dev_config())
        assert len(r1["search_results"]) == 1

        # Simulate second call with accumulated state
        state2 = state.model_copy(update={"search_results": r1["search_results"], "loop_count": 1})
        r2 = run_search_agent(state2, config=_dev_config())
        assert len(r2["search_results"]) == 2


# ---------------------------------------------------------------------------
# Eval mode — must fail without credentials
# ---------------------------------------------------------------------------

class TestEvalMode:
    def test_eval_fails_without_tavily_key(self):
        state = ResearchState(topic="eval test", mode=RunMode.EVAL, max_loops=1)
        cfg = AppConfig(mode=RunMode.EVAL, tavily_api_key="")
        with pytest.raises(RuntimeError, match="eval mode requires"):
            run_search_agent(state, config=cfg)

    @patch("agents.search.web_search", return_value=([], "live"))
    def test_eval_fails_without_anthropic_key(self, _mock_ws):
        state = ResearchState(topic="eval test", mode=RunMode.EVAL, max_loops=1)
        cfg = AppConfig(mode=RunMode.EVAL, tavily_api_key="key", anthropic_api_key="")
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            run_search_agent(state, config=cfg)

    @patch("agents.search.web_search", return_value=([], "live"))
    def test_live_fails_without_anthropic_key(self, _mock_ws):
        state = ResearchState(topic="live test", mode=RunMode.LIVE, max_loops=1)
        cfg = AppConfig(mode=RunMode.LIVE, tavily_api_key="key", anthropic_api_key="")
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            run_search_agent(state, config=cfg)


# ---------------------------------------------------------------------------
# LLM retry logic (mocked)
# ---------------------------------------------------------------------------

class TestRetryLogic:
    @patch("agents.search.web_search")
    @patch("agents.search.ChatAnthropic")
    def test_succeeds_on_first_attempt(self, mock_llm_cls, mock_web_search):
        mock_web_search.return_value = ([], "live")
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        response = _mock_ai_response(
            tool_calls=[{"name": "SearchOutput", "id": "1", "args": _valid_search_output_args()}]
        )
        bound.invoke.return_value = response

        state = ResearchState(topic="retry test", mode=RunMode.LIVE, max_loops=1)
        result = run_search_agent(state, config=_live_config())

        assert result["status"] == GraphStatus.SYNTHESIZING
        assert bound.invoke.call_count == 1

    @patch("agents.search.web_search")
    @patch("agents.search.ChatAnthropic")
    def test_retries_on_prose_then_succeeds(self, mock_llm_cls, mock_web_search):
        from langchain_core.messages import HumanMessage as HM, ToolMessage as TM

        mock_web_search.return_value = ([], "live")
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        # First call returns prose, second returns valid tool call
        prose_response = _mock_ai_response(tool_calls=[], content="Just some text")
        valid_response = _mock_ai_response(
            tool_calls=[{"name": "SearchOutput", "id": "2", "args": _valid_search_output_args()}]
        )
        bound.invoke.side_effect = [prose_response, valid_response]

        state = ResearchState(topic="retry test", mode=RunMode.LIVE, max_loops=1)
        result = run_search_agent(state, config=_live_config(max_retries=2))

        assert result["status"] == GraphStatus.SYNTHESIZING
        assert bound.invoke.call_count == 2

        # Verify no ToolMessage was sent for the prose retry (no tool_call_id to reference)
        retry_messages = bound.invoke.call_args_list[1][0][0]
        assert not any(isinstance(m, TM) for m in retry_messages)

    @patch("agents.search.web_search")
    @patch("agents.search.ChatAnthropic")
    def test_retry_exhaustion_raises(self, mock_llm_cls, mock_web_search):
        mock_web_search.return_value = ([], "live")
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        # All calls return prose
        prose = _mock_ai_response(tool_calls=[], content="nope")
        bound.invoke.return_value = prose

        state = ResearchState(topic="exhaust test", mode=RunMode.LIVE, max_loops=1)
        with pytest.raises(RuntimeError, match="failed after"):
            run_search_agent(state, config=_live_config(max_retries=1))

    @patch("agents.search.web_search")
    @patch("agents.search.ChatAnthropic")
    def test_token_usage_accumulated_across_retries(self, mock_llm_cls, mock_web_search):
        mock_web_search.return_value = ([], "live")
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        bound = MagicMock()
        mock_llm.bind_tools.return_value = bound

        prose = _mock_ai_response(
            tool_calls=[], content="nope",
            response_metadata={"usage": {"input_tokens": 100, "output_tokens": 50}},
        )
        valid = _mock_ai_response(
            tool_calls=[{"name": "SearchOutput", "id": "2", "args": _valid_search_output_args()}],
            response_metadata={"usage": {"input_tokens": 200, "output_tokens": 100}},
        )
        bound.invoke.side_effect = [prose, valid]

        state = ResearchState(topic="token test", mode=RunMode.LIVE, max_loops=1)
        result = run_search_agent(state, config=_live_config(max_retries=2))

        # 150 from first attempt + 300 from second = 450
        assert result["token_usage"].search_agent == 450
