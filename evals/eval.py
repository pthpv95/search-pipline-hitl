"""
evals/eval.py — Evaluation, cost tracking, and scoring for saved research runs.

Loads JSON run artifacts written by run_pipeline.save_run() and scores them on
five dimensions: citation integrity, source validity, topical coverage,
unsupported claim rate, and loop discipline. Also computes per-node and total
cost from configured model pricing.

Usage:
    python -m evals.eval                   # score all eval-mode runs
    python -m evals.eval --runs-dir runs/  # explicit runs directory
    python -m evals.eval --include-all     # also score dev/live runs
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import get_pricing

# Words that don't count toward topical coverage matching.
_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "and", "or", "to",
    "is", "are", "was", "were", "be", "been", "being", "with", "by",
    "as", "at", "from", "this", "that", "it", "its", "if", "then",
    "than", "but", "not", "no", "yes", "can", "will", "shall",
    "should", "would", "could", "may", "might", "must", "do", "does",
    "did", "have", "has", "had", "what", "when", "where", "why",
    "how", "which", "who", "whom", "whose",
}

DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EvalScore:
    citation_integrity: float = 0.0
    source_validity: float = 0.0
    topical_coverage: float = 0.0
    unsupported_claim_rate: float = 0.0
    loop_discipline: float = 0.0

    @property
    def overall(self) -> float:
        scores = [
            self.citation_integrity,
            self.source_validity,
            self.topical_coverage,
            self.unsupported_claim_rate,
            self.loop_discipline,
        ]
        return sum(scores) / len(scores)


@dataclass
class EvalReport:
    run_path: Path
    topic: str
    mode: str
    scores: EvalScore
    notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_run(path: Path) -> dict[str, Any]:
    """Load a single run JSON file."""
    return json.loads(path.read_text())


def load_eval_runs(
    runs_dir: Path | None = None,
    include_all_modes: bool = False,
) -> list[tuple[Path, dict[str, Any]]]:
    """Load saved run artifacts.

    By default returns only runs with mode == "eval" (per PLAN_FINAL.md:
    "Load saved `eval` runs only"). Set include_all_modes=True to include
    dev and live runs as well.
    """
    runs_dir = runs_dir or DEFAULT_RUNS_DIR
    if not runs_dir.exists():
        return []

    runs: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(runs_dir.glob("*.json")):
        try:
            data = load_run(path)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[evals] skipping {path.name}: {e}")
            continue
        if not include_all_modes and data.get("mode") != "eval":
            continue
        runs.append((path, data))
    return runs


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def score_citation_integrity(run: dict[str, Any]) -> tuple[float, str]:
    """Fraction of inline [N] citations that resolve to a saved source.

    Score is 1.0 when every marker maps to a real source, 0.0 when none do.
    Reports look fine if they have no inline markers AND no body — but if
    there's body content with no citations, that's flagged separately by
    the unsupported-claim-rate scorer.
    """
    report = run.get("final_report") or {}
    body = report.get("body", "")
    sources = report.get("sources", []) or []
    markers = re.findall(r"\[(\d+)\]", body)
    if not markers:
        # No citations to validate; treat as full score (other scorer
        # catches uncited claims).
        return 1.0, "no inline citations"
    valid = sum(1 for m in markers if 1 <= int(m) <= len(sources))
    score = valid / len(markers)
    return score, f"{valid}/{len(markers)} citations resolve"


def score_source_validity(run: dict[str, Any]) -> tuple[float, str]:
    """Fraction of saved sources whose URL has a valid scheme and host."""
    report = run.get("final_report") or {}
    sources = report.get("sources", []) or []
    if not sources:
        return 0.0, "no sources"
    valid = 0
    for src in sources:
        url = src.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            valid += 1
    score = valid / len(sources)
    return score, f"{valid}/{len(sources)} URLs valid"


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS}


def score_topical_coverage(run: dict[str, Any]) -> tuple[float, str]:
    """Overlap between topic terms and report body, plus limitations check.

    If gaps remained but no limitations were recorded, the score is reduced.
    """
    topic = run.get("topic", "")
    report = run.get("final_report") or {}
    body = report.get("body", "")
    topic_terms = _tokenize(topic)
    body_terms = _tokenize(body)
    if not topic_terms:
        return 0.0, "empty topic"
    overlap = len(topic_terms & body_terms) / len(topic_terms)

    # If we ran more than one search round and there are no recorded
    # limitations, the report likely glossed over the gaps that drove the
    # extra search — cap the score.
    loop_count = run.get("loop_count", 0)
    has_limitations = bool(run.get("limitations"))
    if loop_count > 1 and not has_limitations:
        overlap = min(overlap, 0.85)

    return overlap, f"{int(overlap * 100)}% topic terms in body"


def score_unsupported_claim_rate(run: dict[str, Any]) -> tuple[float, str]:
    """Score = fraction of body paragraphs that include an inline citation.

    Higher is better. Headings, bullet lists, and bibliography lines are
    excluded so they don't dilute the denominator.
    """
    report = run.get("final_report") or {}
    body = report.get("body", "")
    paragraphs = []
    for raw in body.split("\n\n"):
        text = raw.strip()
        if not text:
            continue
        if text.startswith("#"):
            continue
        # Skip pure source-list blocks ("- [1] Title")
        if text.startswith("- [") and "](" in text:
            continue
        paragraphs.append(text)

    if not paragraphs:
        return 1.0, "no body paragraphs"

    cited = sum(1 for p in paragraphs if re.search(r"\[\d+\]", p))
    score = cited / len(paragraphs)
    return score, f"{cited}/{len(paragraphs)} paragraphs cite sources"


def score_loop_discipline(run: dict[str, Any]) -> tuple[float, str]:
    """Score loop usage relative to the configured cap.

    Full score when loop_count <= max_loops AND if extra loops happened,
    limitations or gaps are recorded (justifying the extra work). Penalize
    when loops exceed the cap or when extra loops have no recorded rationale.
    """
    loops = run.get("loop_count", 0)
    max_loops = run.get("max_loops", 0)
    has_limitations = bool(run.get("limitations"))

    if max_loops == 0:
        # Older runs may not have saved max_loops; fall back to a soft check.
        if loops <= 2:
            return 1.0, f"{loops} loops (no cap recorded)"
        return 0.6, f"{loops} loops (no cap recorded; many)"

    if loops > max_loops:
        return 0.3, f"{loops}/{max_loops} loops (over cap)"

    if loops <= 1:
        return 1.0, f"{loops}/{max_loops} loops"

    # Multiple loops — full score only if rationale is recorded.
    if has_limitations:
        return 1.0, f"{loops}/{max_loops} loops with limitations recorded"
    return 0.85, f"{loops}/{max_loops} loops without limitations"


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def estimate_cost(
    token_usage: Any,
    model_name: str,
) -> dict[str, float]:
    """Estimate per-node and total cost from token usage and model pricing.

    `token_usage` may be a TokenUsage instance, a dict from a saved run, or
    None. Returns a dict with per-node and total USD costs.

    Backward compatibility: older saved runs only persisted flat per-node
    totals (`search_agent`, etc.) without the input/output split. When the
    split fields are missing or zero, fall back to the legacy total at a
    blended (input + output) / 2 rate so cost reporting stays meaningful for
    those artifacts instead of silently reporting $0.
    """
    pricing = get_pricing(model_name)
    in_rate = pricing["input_per_million"]
    out_rate = pricing["output_per_million"]
    blended_rate = (in_rate + out_rate) / 2

    def _attr(obj: Any, key: str, default: int = 0) -> int:
        if obj is None:
            return default
        if isinstance(obj, dict):
            value = obj.get(key)
            return int(value) if value is not None else default
        return getattr(obj, key, default) or default

    nodes = ("search_agent", "synthesis_agent", "report_agent")
    costs: dict[str, float] = {}
    total = 0.0
    for node in nodes:
        in_t = _attr(token_usage, f"{node}_input")
        out_t = _attr(token_usage, f"{node}_output")
        if in_t == 0 and out_t == 0:
            # Legacy artifact: only the flat per-node total was saved.
            # Apply the blended rate as a best-effort estimate.
            legacy_total = _attr(token_usage, node)
            cost = legacy_total * blended_rate / 1_000_000
        else:
            cost = (in_t * in_rate + out_t * out_rate) / 1_000_000
        costs[node] = cost
        total += cost
    costs["total"] = total
    return costs


def format_cost_summary(
    token_usage: Any,
    node_timings: Any,
    model_name: str,
) -> str:
    """Build a compact, multi-line cost + timing summary string.

    Output looks like:
        Cost summary (model: claude-sonnet-4-20250514)
          search_agent      1,234 tok   0.42s   ~$0.0123
          synthesis_agent   2,345 tok   0.31s   ~$0.0234
          report_agent      3,456 tok   1.05s   ~$0.0345
          ─────────────────────────────────────────────
          total             7,035 tok   1.78s   ~$0.0702
    """
    costs = estimate_cost(token_usage, model_name)

    def _attr(obj: Any, key: str, default: float = 0.0) -> float:
        if obj is None:
            return default
        if isinstance(obj, dict):
            value = obj.get(key)
            return float(value) if value is not None else default
        return float(getattr(obj, key, default) or default)

    lines = [f"Cost summary (model: {model_name})"]
    nodes = (
        ("search_agent", "search_agent"),
        ("synthesis_agent", "synthesis_agent"),
        ("report_agent", "report_agent"),
    )
    for node_key, timing_key in nodes:
        tokens = int(_attr(token_usage, node_key))
        seconds = _attr(node_timings, timing_key)
        cost = costs[node_key]
        lines.append(
            f"  {node_key:<17} {tokens:>7,} tok   {seconds:>5.2f}s   ~${cost:.4f}"
        )
    lines.append("  " + "─" * 47)
    total_tokens = int(_attr(token_usage, "total"))
    total_seconds = _attr(node_timings, "total")
    lines.append(
        f"  {'total':<17} {total_tokens:>7,} tok   {total_seconds:>5.2f}s   ~${costs['total']:.4f}"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------


def evaluate_run(run: dict[str, Any], path: Path | None = None) -> EvalReport:
    """Score a single run dict and return an EvalReport."""
    citation, c_note = score_citation_integrity(run)
    source, s_note = score_source_validity(run)
    coverage, t_note = score_topical_coverage(run)
    supported, u_note = score_unsupported_claim_rate(run)
    loop, l_note = score_loop_discipline(run)

    scores = EvalScore(
        citation_integrity=citation,
        source_validity=source,
        topical_coverage=coverage,
        unsupported_claim_rate=supported,
        loop_discipline=loop,
    )

    model_name = (run.get("run_metadata") or {}).get("model_name", "unknown")
    costs = estimate_cost(run.get("token_usage"), model_name)

    token_usage = run.get("token_usage") or {}
    total_tokens = int(token_usage.get("total", 0)) if isinstance(token_usage, dict) else 0

    return EvalReport(
        run_path=path or Path("<inline>"),
        topic=run.get("topic", "<unknown>"),
        mode=run.get("mode", "unknown"),
        scores=scores,
        notes=[c_note, s_note, t_note, u_note, l_note],
        cost_usd=costs["total"],
        total_tokens=total_tokens,
    )


def evaluate_all(
    runs_dir: Path | None = None,
    include_all_modes: bool = False,
) -> list[EvalReport]:
    """Load and score every eval (or all-mode) run in runs_dir."""
    return [
        evaluate_run(data, path)
        for path, data in load_eval_runs(runs_dir, include_all_modes=include_all_modes)
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_report(report: EvalReport) -> str:
    s = report.scores
    lines = [
        f"\n{report.run_path.name}",
        f"  topic:      {report.topic}",
        f"  mode:       {report.mode}",
        f"  citation:   {s.citation_integrity:.2f}  ({report.notes[0]})",
        f"  sources:    {s.source_validity:.2f}  ({report.notes[1]})",
        f"  coverage:   {s.topical_coverage:.2f}  ({report.notes[2]})",
        f"  supported:  {s.unsupported_claim_rate:.2f}  ({report.notes[3]})",
        f"  loops:      {s.loop_discipline:.2f}  ({report.notes[4]})",
        f"  overall:    {s.overall:.2f}",
        f"  tokens:     {report.total_tokens:,}    cost: ~${report.cost_usd:.4f}",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score saved research runs")
    parser.add_argument("--runs-dir", type=Path, default=None)
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Score dev/live runs in addition to eval runs",
    )
    args = parser.parse_args()

    reports = evaluate_all(runs_dir=args.runs_dir, include_all_modes=args.include_all)
    if not reports:
        scope = "all-mode" if args.include_all else "eval-mode"
        print(f"No {scope} runs found in {args.runs_dir or DEFAULT_RUNS_DIR}.")
        return

    for report in reports:
        print(_format_report(report))

    # Aggregate summary
    n = len(reports)
    avg_overall = sum(r.scores.overall for r in reports) / n
    total_cost = sum(r.cost_usd for r in reports)
    total_tokens = sum(r.total_tokens for r in reports)
    print("\n" + "=" * 60)
    print(f"Runs scored:    {n}")
    print(f"Avg overall:    {avg_overall:.2f}")
    print(f"Total tokens:   {total_tokens:,}")
    print(f"Total cost:     ~${total_cost:.4f}")


if __name__ == "__main__":
    main()
