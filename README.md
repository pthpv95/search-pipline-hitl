# Research Assistant with Human-in-the-Loop

A LangGraph-based research pipeline that orchestrates search, synthesis, human review, and report generation. Uses Claude (via `langchain-anthropic`) for search analysis, synthesis, and report writing, with Tavily for web search.

## How it works

```
search_agent → synthesis_agent → [need more?] → human_review (interrupt) → report_agent → END
                                      ↓                 ↓
                                 search_agent      search_agent
                                   (loop)        (reviewer queries)
```

The pipeline supports three review outcomes after the human interrupt:
- **Approve** — proceeds to report generation
- **Approve + queries** — triggers an additional search/synthesis loop (if under loop cap)
- **Edit** — reviewer modifies the draft directly; edit is preserved through any subsequent loops
- **Reject** — terminates the pipeline

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your API keys:
- `ANTHROPIC_API_KEY` — required for Claude LLM calls
- `TAVILY_API_KEY` — required for live web search (optional in `dev` mode)

## Usage

```bash
# Non-interactive run (auto-approves at human review)
python run_pipeline.py "your research topic"

# Interactive CLI (prompts for approve/edit/query/reject)
python cli_review.py "your research topic" --max-loops 2

# Smoke test (stub agents, auto-approve)
python graph.py

# Run all tests
pytest -v

# Run a specific test file
pytest tests/test_human_review.py -v
```

### Run modes

| Mode   | Flag         | Behavior                                    |
|--------|--------------|---------------------------------------------|
| `dev`  | `--mode dev` | Mock search fallback, no API keys needed    |
| `live` | `--mode live`| Real Claude + Tavily calls                  |
| `eval` | `--mode eval`| Like live, but tags runs for evaluation     |

## Project Structure

| File / Directory       | Purpose                                              |
|------------------------|------------------------------------------------------|
| `state.py`             | Pydantic state schema (`ResearchState`) and sub-models |
| `graph.py`             | LangGraph `StateGraph` definition, nodes, and routing |
| `config.py`            | Environment config and API key loading               |
| `agents/search.py`     | Search agent — Claude + Tavily web search            |
| `agents/synthesis.py`  | Synthesis agent — combines findings, detects gaps    |
| `agents/human_review.py`| Human review node with `interrupt()` for HITL       |
| `agents/report.py`     | Report agent — generates cited final reports         |
| `tools/web.py`         | Tavily search wrapper with dev-mode mock fallback    |
| `run_pipeline.py`      | Non-interactive pipeline runner with auto-approve    |
| `cli_review.py`        | Interactive CLI for human review                     |
| `evals/eval.py`        | Score saved runs on citation, source, coverage, etc. |
| `evals/run_eval_topics.py` | Batch-run the 5 suggested eval topics            |
| `tests/`               | Test suite (state, graph, agents, human review, evals)|
| `runs/`                | Persisted run artifacts (JSON)                       |
| `architecture.md`      | Detailed architecture diagram and state model        |

## Persistence

- **In-process**: `MemorySaver` checkpointer supports interrupt/resume within a single process
- **Run artifacts**: Completed runs are saved as JSON in `runs/`
- Cross-process restart is not supported

## Evaluation and cost tracking

Every run records actual token usage from Claude response metadata, per-node
elapsed time via `time.perf_counter()`, and an estimated USD cost computed
from `MODEL_PRICING` in `config.py`. After a run finishes, `run_pipeline.py`
prints a compact cost summary:

```
Cost summary (model: claude-sonnet-4-20250514)
  search_agent        2,341 tok    0.84s   ~$0.0234
  synthesis_agent     1,821 tok    0.51s   ~$0.0182
  report_agent        3,103 tok    1.27s   ~$0.0310
  ───────────────────────────────────────────────
  total               7,265 tok    2.62s   ~$0.0726
```

To generate a batch of eval-mode runs and score them:

```bash
# 1. Run the 5 suggested eval topics (requires real API keys, costs ~$0.10–$0.50 total)
python -m evals.run_eval_topics

# 2. Score every saved eval-mode run
python -m evals.eval
```

`evals/eval.py` scores each run on five dimensions (each in `[0.0, 1.0]`):

| Score                    | What it measures                                           |
|--------------------------|------------------------------------------------------------|
| `citation_integrity`     | Fraction of inline `[N]` markers that resolve to a source  |
| `source_validity`        | Fraction of saved sources with a valid scheme/host URL     |
| `topical_coverage`       | Topic-term overlap with the report body (capped if extra loops have no recorded limitations) |
| `unsupported_claim_rate` | Fraction of body paragraphs that include an inline citation |
| `loop_discipline`        | Whether `loop_count <= max_loops` and extra loops are justified |

The default loader returns only `mode == "eval"` runs to keep evaluation
honest — pass `--include-all` to also score `dev`/`live` artifacts.

## Known limitations

- **In-process persistence only.** Pausing for human review and resuming
  works within a single Python process, but the graph cannot resume after a
  process restart (no durable checkpointer).
- **Citation integrity is a soft check.** If the model cites a URL that
  isn't in the source list, the report agent records a warning in
  `state.errors` instead of failing the run.
- **Cost figures are estimates.** They use static `MODEL_PRICING` rates and
  do not account for cached input or batched discounts.
- **Topic coverage is keyword-based.** It rewards body text that mentions
  the topic's terms — it does not measure semantic accuracy.
