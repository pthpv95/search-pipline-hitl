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
| `tests/`               | Test suite (state, graph, agents, human review, etc.)|
| `runs/`                | Persisted run artifacts (JSON)                       |
| `architecture.md`      | Detailed architecture diagram and state model        |

## Persistence

- **In-process**: `MemorySaver` checkpointer supports interrupt/resume within a single process
- **Run artifacts**: Completed runs are saved as JSON in `runs/`
- Cross-process restart is not supported
