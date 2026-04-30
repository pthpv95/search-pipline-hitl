# AGENTS.md

## Commands

```bash
pip install -r requirements.txt    # Python 3.9+, uses repo-local .venv

# Run (dev mode — no API keys needed, uses mocks)
python graph.py                    # Smoke test: full pipeline, auto-approves review
python run_pipeline.py "topic"     # Non-interactive, auto-approves review
python cli_review.py "topic"       # Interactive HITL (prompts for approve/edit/query/reject)

# Run (live/eval mode — needs ANTHROPIC_API_KEY + TAVILY_API_KEY in .env)
python run_pipeline.py "topic" --mode live
python run_pipeline.py "topic" --mode eval --format executive_brief --max-loops 3

# Tests — always dev mode: conftest.py blanks API keys so no live calls leak
pytest -v                          # All tests
pytest tests/test_graph.py -v      # Single file
pytest tests/test_state.py::test_should_search_again_respects_loop_cap_and_gaps -v

# Web UI (two terminals)
python server.py                   # Backend :8000
cd web && npm run dev              # Frontend :5173, proxies /api → :8000

# Evaluation
python -m evals.run_eval_topics    # Batch-run 5 eval topics (needs live keys, ~$0.10-$0.50)
python -m evals.eval               # Score saved eval-mode runs
```

## Architecture

Four LangGraph nodes in `graph.py`, each backed by a real agent in `agents/`:

```
search_agent → synthesis_agent → human_review (interrupt) → report_agent → END
     ↑              |                    ↑                      |
     └── loop ──────┘                    └── reviewer queries ──┘
```

- **`state.py`** — `ResearchState` (Pydantic) is the single source of truth. Convenience properties `all_findings`, `all_sources`, `should_search_again`, `latest_gaps` keep logic out of nodes.
- **`agents/search.py`** — Claude + Tavily web search with structured `SearchOutput` tool call + corrective retry.
- **`agents/synthesis.py`** — Synthesizes findings, detects gaps, decides loop. Structured `SynthesisOutput` tool call.
- **`agents/human_review.py`** — Calls `langgraph.types.interrupt()` with review payload; parses resume dict (`{action, edited_draft?, additional_queries?, notes?, rejection_reason?}`).
- **`agents/report.py`** — Generates final report with inline citations. Validates citations post-hoc (warns, doesn't fail).
- **`config.py`** — `AppConfig` loads from env. `MODEL_PRICING` for cost estimation. `DEFAULT_CONFIG` is mutated by `conftest.py` to remove keys during tests.
- **`tools/web.py`** — Tavily search wrapper with dev-mode mock fallback. `fetch_page()` caps at 10k chars.
- **`run_pipeline.py`** — Auto-approves human review by sending `Command(resume={"action": "approve"})`.
- **`cli_review.py`** — Reads `state.tasks[0].interrupts[0].value` for review payload; prompts user interactively.
- **`server.py`** — FastAPI backend for browser UI. `SessionRegistry` holds in-memory state for active runs.

## Key conventions

- **Immutable state**: Nodes return dicts of changed fields — never mutate `ResearchState` in place. Use `model_copy()`, `model_copy(update={...})`, or `.add()` methods on `TokenUsage`/`NodeTiming`.
- **Node ownership**: Each agent docstring lists exactly which state fields it reads and writes.
- **LLM agents share a pattern**: `ChatAnthropic` with tool binding → `bind_tools([PydanticModel], tool_choice={"type": "tool", "name": "..."})` → corrective retry up to `max_retries` times. Token counts extracted from `response_metadata.usage`.
- **No LLM key → RuntimeError** in live/eval mode. Dev mode gracefully falls back to stubs.
- **Citation validation is soft**: `_validate_citations()` appends warnings to `state.errors` instead of failing the run.
- **Loop cap enforcement**: `synthesis_agent` forces `needs_more_search=False` when `loop_count >= max_loops` and appends a limitation note.

## Gotchas

- **Tests blank API keys**: `tests/conftest.py` sets `config.DEFAULT_CONFIG = AppConfig(anthropic_api_key="", tavily_api_key="")`. Any agent receiving `DEFAULT_CONFIG` in tests runs in stub mode. If you pass a custom `AppConfig` with real keys to an agent in a test, it will make live API calls.
- **In-process persistence only**: `MemorySaver` checkpointer works within a single process. No durable resume after restart.
- **`TokenUsage` backward-compat constructor**: Pass `search_agent=500` (legacy) and it's treated as input tokens. New code should use `search_agent_input=300, search_agent_output=200`.
- **CLAUDE.md is outdated**: The project has evolved past stubs. This file (`AGENTS.md`) is authoritative for current OpenCode sessions.
- **No `pyproject.toml` or CI**: Dependency install is `pip install -r requirements.txt`. No linter/formatter/typechecker configured.

## Workflow
- Ask clarifying questions before starting complex tasks
- Make minimal changes, don't refactor unrelated code
- Create separate commits per logical change, not one giant commit
- When unsure between two approaches, explain both and let me choose
- Never auto-commit after completing a task — ask for review first. Only commit when the user says "lgmt" (looks good to me) or gives explicit approval.