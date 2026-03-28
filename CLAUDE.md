# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A LangGraph-based research assistant with human-in-the-loop (HITL) review. The graph orchestrates a multi-step research pipeline: **search → synthesis → human review → report generation**. Currently uses stub agents (no LLM calls) that will be replaced incrementally week by week.

## Commands

```bash
# Install dependencies (Python 3.9+, uses venv)
pip install -r requirements.txt

# Run the graph end-to-end (smoke test with stub agents)
python graph.py

# Run all tests
pytest test_graph.py -v

# Run a single test
pytest test_graph.py::TestStateSchema::test_default_state_is_valid -v
```

## Architecture

Two files comprise the entire application:

- **`state.py`** — Pydantic state schema (`ResearchState`) and all sub-models. This is the single source of truth for data flowing through the graph. Every node reads from and writes to this schema. Contains convenience properties (`all_findings`, `all_sources`, `should_search_again`) that keep logic out of nodes.

- **`graph.py`** — LangGraph `StateGraph` definition with four nodes and a conditional edge:
  1. `search_agent` → searches for information (stub)
  2. `synthesis_agent` → synthesizes findings, decides if more search is needed (stub)
  3. `human_review` → HITL checkpoint, currently auto-approves (stub)
  4. `report_agent` → generates final report (stub)

  The conditional edge after `synthesis_agent` (`route_after_synthesis`) either loops back to `search_agent` or proceeds to `human_review` based on `state.should_search_again`.

## Key Design Rules

- **Node field ownership**: Each node should only write to fields it owns (documented in comments above each node function).
- **Immutable state updates**: Never mutate lists in place — always return new lists. Nodes return dicts of changed fields, not full state objects.
- **Stub replacement pattern**: Each stub is clearly marked with `--- STUB DATA ---` / `--- END STUB ---` comments. Replace the entire block when implementing real logic.
- **Checkpointing**: `compile_graph()` accepts an optional `checkpointer` (e.g., `MemorySaver()`) for persistent state, needed for HITL interrupt support.
