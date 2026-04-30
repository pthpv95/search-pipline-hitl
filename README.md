# Research Assistant with Human-in-the-Loop

A LangGraph-based research pipeline that orchestrates search, synthesis, human review, and report generation. LLM-agnostic via a provider abstraction — supports Anthropic Claude and OpenCode Go (GLM‑5, DeepSeek, Kimi, Qwen) out of the box. Uses Tavily for web search.

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

### Docker (recommended)

```bash
cp .env.example .env   # edit with your API keys
docker compose up      # backend :8000, frontend :5173
```

### Local

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your API keys.

**LLM provider** — choose one:

| Provider | Env vars |
|---|---|
| Anthropic (default) | `ANTHROPIC_API_KEY` |
| OpenCode Go ($5/month) | `LLM_PROVIDER=opencode_go`, `OPENCODE_GO_API_KEY`, optionally `OPENCODE_GO_MODEL` (default: `glm-5`) |

**Web search:** `TAVILY_API_KEY` — required for live search (optional in `dev` mode).

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

# Web UI (two terminals)
python server.py                   # Backend :8000
cd web && npm run dev              # Frontend :5173, proxies /api → :8000
```

### Run modes

| Mode   | Flag         | Behavior                                    |
|--------|--------------|---------------------------------------------|
| `dev`  | `--mode dev` | Mock search fallback, no API keys needed    |
| `live` | `--mode live`| Real LLM + Tavily calls                     |
| `eval` | `--mode eval`| Like live, but tags runs for evaluation     |

## Project Structure

| File / Directory       | Purpose                                              |
|------------------------|------------------------------------------------------|
| `state.py`             | Pydantic state schema (`ResearchState`) and sub-models |
| `graph.py`             | LangGraph `StateGraph` definition, nodes, and routing |
| `config.py`            | Environment config and API key loading               |
| `llm_factory.py`       | Provider abstraction — returns ChatAnthropic or ChatOpenAI |
| `config.py`            | Environment config, model pricing, and provider fields   |
| `auth/trials.py`       | IP-based trial gating (2 free runs, then API key)       |
| `agents/search.py`     | Search agent — LLM + Tavily web search               |
| `agents/synthesis.py`  | Synthesis agent — combines findings, detects gaps    |
| `agents/human_review.py`| Human review node with `interrupt()` for HITL       |
| `agents/report.py`     | Report agent — generates cited final reports         |
| `tools/web.py`         | Tavily search wrapper with dev-mode mock fallback    |
| `run_pipeline.py`      | Non-interactive pipeline runner with auto-approve    |
| `cli_review.py`        | Interactive CLI for human review                     |
| `server.py`            | FastAPI backend for the browser UI                   |
| `api_adapters.py`      | State → JSON DTO transforms for the API              |
| `api_models.py`        | Pydantic request/response models for the API         |
| `api_runtime.py`       | In-memory session registry + background graph runner |
| `web/`                 | React + Vite browser console (run list, pipeline graph, review panel) |
| `Dockerfile`           | Python backend container                                |
| `Dockerfile.web`       | Nginx + React frontend container                        |
| `docker-compose.yml`   | One-command orchestration (backend + frontend)          |
| `pyproject.toml`       | Project metadata, deps, ruff/mypy/pytest config         |
| `evals/eval.py`        | Score saved runs on citation, source, coverage, etc. |
| `evals/run_eval_topics.py` | Batch-run the 5 suggested eval topics            |
| `tests/`               | Test suite (state, graph, agents, human review, evals, server)|
| `runs/`                | Persisted run artifacts (JSON)                       |
| `architecture.md`      | Detailed architecture diagram and state model        |

## Persistence

- **In-process**: `MemorySaver` checkpointer supports interrupt/resume within a single process
- **Run artifacts**: Completed runs are saved as JSON in `runs/`
- Cross-process restart is not supported

## Evaluation and cost tracking

Every run records actual token usage from LLM response metadata (supports
both Anthropic and OpenAI‑compatible formats), per-node elapsed time via
`time.perf_counter()`, and an estimated USD cost computed from `MODEL_PRICING`
in `config.py`. After a run finishes, `run_pipeline.py` prints a compact
cost summary:

```
Cost summary (model: glm-5)
  search_agent        6,428 tok    1.99s   ~$0.0189
  synthesis_agent    13,641 tok    1.66s   ~$0.0334
  report_agent        4,055 tok    0.75s   ~$0.0159
  ───────────────────────────────────────────────
  total              24,124 tok    4.40s   ~$0.0682
```

To generate a batch of eval-mode runs and score them:

```bash
# 1. Run the 5 suggested eval topics (requires real API keys, costs ~$0.10–$0.50 total)
python -m evals.run_eval_topics

# 2. Score every saved eval-mode run
python -m evals.eval
```

`evals/eval.py` scores each run on five dimensions (each in `[0.0, 1.0]`):

```
20260409T134400Z_impact_of_llms_on_software_developer_pro_24295f.json
  topic:      impact of LLMs on software developer productivity
  mode:       eval
  citation:   1.00  (15/15 citations resolve)
  sources:    1.00  (9/9 URLs valid)
  coverage:   1.00  (100% topic terms in body)
  supported:  0.69  (11/16 paragraphs cite sources)
  loops:      1.00  (2/2 loops with limitations recorded)
  overall:    0.94
  tokens:     28,299    cost: ~$0.1910

20260409T134656Z_state_of_multi_agent_ai_systems_in_2025_58f084.json
  topic:      state of multi-agent AI systems in 2025
  mode:       eval
  citation:   1.00  (13/13 citations resolve)
  sources:    1.00  (11/11 URLs valid)
  coverage:   1.00  (100% topic terms in body)
  supported:  0.55  (11/20 paragraphs cite sources)
  loops:      1.00  (2/2 loops with limitations recorded)
  overall:    0.91
  tokens:     38,408    cost: ~$0.2353

20260409T134932Z_langgraph_vs_crewai_vs_autogen_compariso_14c94f.json
  topic:      LangGraph vs CrewAI vs AutoGen comparison
  mode:       eval
  citation:   1.00  (42/42 citations resolve)
  sources:    1.00  (10/10 URLs valid)
  coverage:   1.00  (100% topic terms in body)
  supported:  0.92  (24/26 paragraphs cite sources)
  loops:      1.00  (2/2 loops with limitations recorded)
  overall:    0.98
  tokens:     43,432    cost: ~$0.2410

20260409T135231Z_prompt_engineering_techniques_for_struct_1b91b4.json
  topic:      prompt engineering techniques for structured output
  mode:       eval
  citation:   0.88  (14/16 citations resolve)
  sources:    1.00  (9/9 URLs valid)
  coverage:   1.00  (100% topic terms in body)
  supported:  0.65  (13/20 paragraphs cite sources)
  loops:      1.00  (2/2 loops with limitations recorded)
  overall:    0.91
  tokens:     33,776    cost: ~$0.2256

20260409T135511Z_ai_agent_memory_architectures_07530f.json
  topic:      AI agent memory architectures
  mode:       eval
  citation:   0.86  (18/21 citations resolve)
  sources:    1.00  (11/11 URLs valid)
  coverage:   1.00  (100% topic terms in body)
  supported:  0.71  (15/21 paragraphs cite sources)
  loops:      1.00  (2/2 loops with limitations recorded)
  overall:    0.91
  tokens:     26,122    cost: ~$0.1753

============================================================
Runs scored:    10
Avg overall:    0.93
Total tokens:   340,858
Total cost:     ~$2.1154
```

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
