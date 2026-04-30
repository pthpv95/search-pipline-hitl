"""
tests/test_evals.py — Tests for eval scoring, cost estimation, and run loading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.eval import (
    EvalReport,
    EvalScore,
    estimate_cost,
    evaluate_all,
    evaluate_run,
    format_cost_summary,
    load_eval_runs,
    score_citation_integrity,
    score_loop_discipline,
    score_source_validity,
    score_topical_coverage,
    score_unsupported_claim_rate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    *,
    topic: str = "AI agent memory architectures",
    mode: str = "eval",
    body: str = "Memory architectures matter [1]. Persistence is key [2].",
    sources: list[dict] | None = None,
    loop_count: int = 1,
    max_loops: int = 2,
    limitations: list[str] | None = None,
    token_usage: dict | None = None,
    model_name: str = "claude-sonnet-4-20250514",
) -> dict:
    return {
        "topic": topic,
        "mode": mode,
        "loop_count": loop_count,
        "max_loops": max_loops,
        "limitations": limitations or [],
        "errors": [],
        "token_usage": token_usage or {
            "search_agent_input": 1000,
            "search_agent_output": 200,
            "synthesis_agent_input": 800,
            "synthesis_agent_output": 300,
            "report_agent_input": 1500,
            "report_agent_output": 500,
            "total": 4300,
            "search_agent": 1200,
            "synthesis_agent": 1100,
            "report_agent": 2000,
        },
        "node_timings": {
            "search_agent": 0.5,
            "synthesis_agent": 0.3,
            "report_agent": 1.2,
            "human_review": 0.0,
            "total": 2.0,
        },
        "run_metadata": {
            "model_name": model_name,
            "search_provider": "tavily",
            "thread_id": "test",
        },
        "final_report": {
            "title": topic,
            "executive_summary": "Summary text",
            "body": body,
            "format": "deep_dive",
            "word_count": len(body.split()),
            "sources": sources if sources is not None else [
                {"url": "https://example.com/a", "title": "A", "snippet": "..."},
                {"url": "https://example.com/b", "title": "B", "snippet": "..."},
            ],
        },
    }


def _write_run(tmp_path: Path, name: str, run: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(run))
    return path


# ---------------------------------------------------------------------------
# load_eval_runs
# ---------------------------------------------------------------------------


class TestLoadEvalRuns:
    def test_filters_by_eval_mode(self, tmp_path):
        _write_run(tmp_path, "eval_one.json", _make_run(mode="eval"))
        _write_run(tmp_path, "dev_one.json", _make_run(mode="dev"))
        _write_run(tmp_path, "live_one.json", _make_run(mode="live"))

        runs = load_eval_runs(runs_dir=tmp_path)
        assert len(runs) == 1
        assert runs[0][1]["mode"] == "eval"

    def test_include_all_modes(self, tmp_path):
        _write_run(tmp_path, "eval_one.json", _make_run(mode="eval"))
        _write_run(tmp_path, "dev_one.json", _make_run(mode="dev"))

        runs = load_eval_runs(runs_dir=tmp_path, include_all_modes=True)
        assert len(runs) == 2

    def test_missing_dir_returns_empty(self, tmp_path):
        runs = load_eval_runs(runs_dir=tmp_path / "nonexistent")
        assert runs == []

    def test_skips_invalid_json(self, tmp_path, capsys):
        (tmp_path / "broken.json").write_text("not json")
        _write_run(tmp_path, "good.json", _make_run(mode="eval"))

        runs = load_eval_runs(runs_dir=tmp_path)
        assert len(runs) == 1
        captured = capsys.readouterr()
        assert "skipping" in captured.out


# ---------------------------------------------------------------------------
# Citation integrity
# ---------------------------------------------------------------------------


class TestCitationIntegrity:
    def test_all_citations_valid(self):
        run = _make_run(
            body="Claim A [1]. Claim B [2].",
            sources=[
                {"url": "https://a.com", "title": "A", "snippet": "..."},
                {"url": "https://b.com", "title": "B", "snippet": "..."},
            ],
        )
        score, note = score_citation_integrity(run)
        assert score == 1.0
        assert "2/2" in note

    def test_out_of_range_marker(self):
        run = _make_run(
            body="Good [1]. Bad [5].",
            sources=[{"url": "https://a.com", "title": "A", "snippet": "..."}],
        )
        score, _ = score_citation_integrity(run)
        assert score == 0.5

    def test_no_citations_full_score(self):
        run = _make_run(body="No citations here.")
        score, note = score_citation_integrity(run)
        assert score == 1.0
        assert "no inline" in note


# ---------------------------------------------------------------------------
# Source validity
# ---------------------------------------------------------------------------


class TestSourceValidity:
    def test_all_valid_urls(self):
        run = _make_run(sources=[
            {"url": "https://example.com/a", "title": "A", "snippet": "..."},
            {"url": "http://example.org/b", "title": "B", "snippet": "..."},
        ])
        score, _ = score_source_validity(run)
        assert score == 1.0

    def test_invalid_scheme(self):
        run = _make_run(sources=[
            {"url": "https://valid.com", "title": "v", "snippet": "..."},
            {"url": "ftp://wrong.com", "title": "x", "snippet": "..."},
            {"url": "not a url", "title": "y", "snippet": "..."},
        ])
        score, _ = score_source_validity(run)
        assert score == pytest.approx(1 / 3, rel=1e-3)

    def test_no_sources_zero(self):
        run = _make_run(sources=[])
        score, _ = score_source_validity(run)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Topical coverage
# ---------------------------------------------------------------------------


class TestTopicalCoverage:
    def test_full_coverage(self):
        run = _make_run(
            topic="memory architectures",
            body="Memory and architectures discussed extensively here.",
        )
        score, _ = score_topical_coverage(run)
        assert score == 1.0

    def test_partial_coverage(self):
        run = _make_run(
            topic="memory architectures persistence",
            body="Memory is the key topic here.",
        )
        score, _ = score_topical_coverage(run)
        assert 0.0 < score < 1.0

    def test_multi_loop_without_limitations_capped(self):
        run = _make_run(
            topic="memory",
            body="Memory is everything we cover here.",
            loop_count=2,
            limitations=[],
        )
        score, _ = score_topical_coverage(run)
        # Capped at 0.85 because >1 loop without limitations
        assert score <= 0.85

    def test_multi_loop_with_limitations_uncapped(self):
        run = _make_run(
            topic="memory",
            body="Memory is everything we cover here.",
            loop_count=2,
            limitations=["loop cap reached"],
        )
        score, _ = score_topical_coverage(run)
        assert score == 1.0


# ---------------------------------------------------------------------------
# Unsupported claim rate
# ---------------------------------------------------------------------------


class TestUnsupportedClaimRate:
    def test_all_paragraphs_cited(self):
        body = "Paragraph one [1].\n\nParagraph two [2].\n\nParagraph three [1]."
        run = _make_run(body=body)
        score, _ = score_unsupported_claim_rate(run)
        assert score == 1.0

    def test_some_paragraphs_uncited(self):
        body = "Cited paragraph [1].\n\nUncited paragraph here.\n\nAnother cited [1]."
        run = _make_run(body=body)
        score, _ = score_unsupported_claim_rate(run)
        assert score == pytest.approx(2 / 3, rel=1e-3)

    def test_excludes_headings_and_source_lists(self):
        body = (
            "## Heading\n\n"
            "Real paragraph [1].\n\n"
            "## Sources\n\n"
            "- [1] [Title](http://example.com)"
        )
        run = _make_run(body=body)
        score, note = score_unsupported_claim_rate(run)
        assert score == 1.0
        assert "1/1" in note


# ---------------------------------------------------------------------------
# Loop discipline
# ---------------------------------------------------------------------------


class TestLoopDiscipline:
    def test_single_loop_full_score(self):
        run = _make_run(loop_count=1, max_loops=2)
        score, _ = score_loop_discipline(run)
        assert score == 1.0

    def test_multi_loop_with_limitations_full_score(self):
        run = _make_run(loop_count=2, max_loops=2, limitations=["cap reached"])
        score, _ = score_loop_discipline(run)
        assert score == 1.0

    def test_multi_loop_without_limitations_reduced(self):
        run = _make_run(loop_count=2, max_loops=2, limitations=[])
        score, _ = score_loop_discipline(run)
        assert score == 0.85

    def test_over_cap_penalized(self):
        run = _make_run(loop_count=4, max_loops=2)
        score, _ = score_loop_discipline(run)
        assert score == 0.3

    def test_missing_max_loops_uses_fallback(self):
        run = _make_run(loop_count=1, max_loops=0)
        score, note = score_loop_discipline(run)
        assert score == 1.0
        assert "no cap" in note


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_known_model_cost(self):
        # claude-sonnet-4: $3 input / $15 output per million.
        # 1M input + 1M output = $3 + $15 = $18 total per node, $54 across 3 nodes.
        token_usage = {
            "search_agent_input": 1_000_000,
            "search_agent_output": 1_000_000,
            "synthesis_agent_input": 1_000_000,
            "synthesis_agent_output": 1_000_000,
            "report_agent_input": 1_000_000,
            "report_agent_output": 1_000_000,
        }
        costs = estimate_cost(token_usage, "claude-sonnet-4-20250514")
        assert costs["search_agent"] == pytest.approx(18.0)
        assert costs["total"] == pytest.approx(54.0)

    def test_unknown_model_uses_fallback(self):
        token_usage = {
            "search_agent_input": 1_000_000,
            "search_agent_output": 0,
            "synthesis_agent_input": 0,
            "synthesis_agent_output": 0,
            "report_agent_input": 0,
            "report_agent_output": 0,
        }
        costs = estimate_cost(token_usage, "made-up-model")
        # Falls back to default $3/$15 — 1M input = $3
        assert costs["search_agent"] == pytest.approx(3.0)

    def test_none_token_usage(self):
        costs = estimate_cost(None, "claude-sonnet-4-20250514")
        assert costs["total"] == 0.0

    def test_works_with_pydantic_model(self):
        from state import TokenUsage

        usage = TokenUsage(
            search_agent_input=500_000,
            search_agent_output=100_000,
        )
        costs = estimate_cost(usage, "claude-sonnet-4-20250514")
        # 500k * $3/M + 100k * $15/M = $1.5 + $1.5 = $3.0
        assert costs["search_agent"] == pytest.approx(3.0)

    def test_legacy_token_usage_uses_blended_fallback(self):
        """Pre-existing run artifacts only have flat per-node totals.

        Without a fallback, estimate_cost would report $0 for them. Verify
        the blended rate kicks in so cost reporting stays meaningful.
        """
        # claude-sonnet-4: blended = ($3 + $15) / 2 = $9 per million.
        # 1M tokens per node × $9/M × 3 nodes = $27 total.
        legacy_token_usage = {
            "search_agent": 1_000_000,
            "synthesis_agent": 1_000_000,
            "report_agent": 1_000_000,
            "total": 3_000_000,
        }
        costs = estimate_cost(legacy_token_usage, "claude-sonnet-4-20250514")
        assert costs["search_agent"] == pytest.approx(9.0)
        assert costs["synthesis_agent"] == pytest.approx(9.0)
        assert costs["report_agent"] == pytest.approx(9.0)
        assert costs["total"] == pytest.approx(27.0)

    def test_split_fields_take_precedence_over_legacy_total(self):
        """When both split and legacy fields exist, the split wins."""
        token_usage = {
            "search_agent_input": 1_000_000,
            "search_agent_output": 0,
            "search_agent": 999_999_999,  # legacy field with absurd value
            "synthesis_agent_input": 0,
            "synthesis_agent_output": 0,
            "report_agent_input": 0,
            "report_agent_output": 0,
        }
        costs = estimate_cost(token_usage, "claude-sonnet-4-20250514")
        # 1M input * $3/M = $3 (legacy field ignored)
        assert costs["search_agent"] == pytest.approx(3.0)


class TestFormatCostSummary:
    def test_includes_model_and_total(self):
        token_usage = {
            "search_agent_input": 1000,
            "search_agent_output": 500,
            "synthesis_agent_input": 800,
            "synthesis_agent_output": 400,
            "report_agent_input": 1500,
            "report_agent_output": 800,
            "search_agent": 1500,
            "synthesis_agent": 1200,
            "report_agent": 2300,
            "total": 5000,
        }
        timings = {
            "search_agent": 0.5,
            "synthesis_agent": 0.3,
            "report_agent": 1.2,
            "total": 2.0,
        }
        out = format_cost_summary(token_usage, timings, "claude-sonnet-4-20250514")
        assert "claude-sonnet-4-20250514" in out
        assert "search_agent" in out
        assert "total" in out
        assert "$" in out


# ---------------------------------------------------------------------------
# evaluate_run / evaluate_all
# ---------------------------------------------------------------------------


class TestEvaluateRun:
    def test_evaluate_run_returns_full_report(self):
        run = _make_run()
        report = evaluate_run(run, path=Path("test.json"))
        assert isinstance(report, EvalReport)
        assert report.topic == "AI agent memory architectures"
        assert report.mode == "eval"
        assert isinstance(report.scores, EvalScore)
        assert 0.0 <= report.scores.overall <= 1.0
        assert report.cost_usd > 0
        assert len(report.notes) == 5

    def test_overall_score_is_average(self):
        scores = EvalScore(
            citation_integrity=1.0,
            source_validity=0.5,
            topical_coverage=0.5,
            unsupported_claim_rate=1.0,
            loop_discipline=1.0,
        )
        # (1 + 0.5 + 0.5 + 1 + 1) / 5 = 0.8
        assert scores.overall == pytest.approx(0.8)

    def test_evaluate_all_loads_and_scores(self, tmp_path):
        _write_run(tmp_path, "a.json", _make_run(topic="topic A"))
        _write_run(tmp_path, "b.json", _make_run(topic="topic B"))
        _write_run(tmp_path, "dev.json", _make_run(mode="dev"))

        reports = evaluate_all(runs_dir=tmp_path)
        assert len(reports) == 2  # only the two eval-mode runs
        topics = {r.topic for r in reports}
        assert topics == {"topic A", "topic B"}

    def test_evaluate_all_empty_dir(self, tmp_path):
        reports = evaluate_all(runs_dir=tmp_path)
        assert reports == []
