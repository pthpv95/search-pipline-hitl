# Codebase Navigation Guide

A practical guide for understanding this repo quickly. The codebase is small (~17 source files, ~8 test files) — don't let the number of concepts intimidate you.

## Mental model

> **State flows through nodes. `state.py` is the noun, `agents/*.py` are the verbs, `graph.py` is the sentence.**

Every piece of data lives in `ResearchState`. Every node reads fields from it and writes fields back. Once that clicks, every file falls into place.

## Read in dependency order

Don't read alphabetically — read in the order data flows:

1. **`state.py`** — the contract. `ResearchState` and its sub-models (`SearchResult`, `Synthesis`, `ReportOutput`, `TokenUsage`). Every node reads/writes this; understand it and the rest is just functions.
2. **`config.py`** — environment, modes, model pricing. Short, no logic to memorize.
3. **`graph.py`** — the StateGraph wiring. Tells you which nodes exist and how they connect (`route_after_synthesis`, `route_after_human_review`). This is your **map**.
4. **`agents/*.py`** — one per node. Read in execution order: `search → synthesis → human_review → report`.
5. **`run_pipeline.py`** / **`cli_review.py`** — the two entry points. Skim last; they just drive the graph.

Tip: open `graph.py` and the agent files side by side. Whenever you see `add_node("search_agent", run_search_agent)`, jump to `agents/search.py`. The graph is the index.

## Tests are executable documentation

`tests/test_*.py` mirrors source files 1:1. When a function confuses you, **read its test first** — it shows inputs, outputs, and edge cases without LLM-call boilerplate.

Example: before reading `score_topical_coverage`, read `TestTopicalCoverage` in `tests/test_evals.py` — you'll see exactly what "capped at 0.85" means.

## Three queries that unlock the codebase

When you want to understand any concept:

- **"Where is this field written?"** — grep the field name in `agents/`. Each node's docstring claims field ownership; the grep verifies it.
- **"What calls this function?"** — grep the function name across the repo. One caller = linear flow; many callers = utility.
- **"How does data X get into state Y?"** — trace it: search the field name in `state.py` (definition), then `agents/` (writers), then `tests/` (examples).

## Run it and watch it move

The fastest way to internalize the flow:

```bash
python graph.py                                    # stub run, prints state transitions
python run_pipeline.py "your topic" --mode dev     # full pipeline with mock search
pytest tests/test_graph.py -v                      # see node ordering tested
```

`--mode dev` needs no API keys and exercises every node with mock data. Add a temporary `print(state)` inside any node to see what each step adds.

## The "two-file rule" for any change

For any task, ask: *which fields in `state.py` does it touch, and which node owns them?* Almost every change lands in **one agent file + one test file**. If your change is sprawling across more than that, you're probably in the wrong abstraction.

## Files to defer until needed

- `tools/web.py` — Tavily wrapper, only matters if you change search
- `evals/` — only matters when scoring saved runs
- `cli_review.py` — only matters if you change the human review UX
- `architecture.md` — read once for the diagram, then forget about it

## Field ownership cheat sheet

| Node              | Writes to (from `state.py`)                        |
|-------------------|----------------------------------------------------|
| `search_agent`    | `search_results`, `loop_count`, `token_usage.search_agent_*` |
| `synthesis_agent` | `synthesis_draft`, `token_usage.synthesis_agent_*` |
| `human_review`    | `human_review` (`approved`, `rejected`, `edited_draft`, `additional_queries`) |
| `report_agent`    | `final_report`, `token_usage.report_agent_*`       |

Routing is driven by computed properties on `ResearchState` (e.g. `should_search_again`), not by fields a node writes directly.

When debugging, first identify which field is wrong, then jump directly to the node that owns it.
