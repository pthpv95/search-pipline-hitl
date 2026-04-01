# Multi-Agent Research Pipeline — Final Build Plan

> This is the execution plan to use going forward.
> It combines the concrete week-by-week structure of `PLAN.md` with the stronger engineering guardrails from `PLAN_REVISED.md`.
> Do not treat fixed sample outputs as requirements. Build for correct behavior, clear interfaces, and honest evaluation.

---

## Project Overview

Build a multi-agent research pipeline using LangGraph and Claude tool use.
The pipeline should:

- accept a research topic
- perform targeted web research
- synthesize findings into a draft
- pause for human review
- generate a cited final report
- save run artifacts for inspection and evaluation

The result should be credible as a portfolio project and practical to run locally.

---

## Operating Modes

Define these modes from the start.

### `dev`

Purpose:
fast local development

Rules:

- mock search results are allowed
- external credentials are optional
- tests should validate behavior and interfaces, not content quality

### `live`

Purpose:
real end-to-end runs with external providers

Rules:

- real search and real model calls
- citations must map to real sources
- saved runs may be used for demos

### `eval`

Purpose:
generate runs for evaluation

Rules:

- mock search results are not allowed
- every saved source must be real
- token, timing, and provider metadata must be persisted

---

## Target Repository Structure

```text
research_agent/
├── state.py
├── graph.py
├── config.py
├── run_pipeline.py
├── cli_review.py
├── agents/
│   ├── __init__.py
│   ├── search.py
│   ├── synthesis.py
│   ├── human_review.py
│   └── report.py
├── tools/
│   ├── __init__.py
│   └── web.py
├── evals/
│   ├── __init__.py
│   ├── eval.py
│   └── runs/
├── tests/
│   ├── test_state.py
│   ├── test_graph.py
│   ├── test_agents.py
│   └── test_evals.py
├── requirements.txt
├── .env.example
└── README.md
```

`config.py` is required so mode, provider, loop, and model settings are centralized.

---

## Global Constraints

These apply every week.

- Python 3.11+
- full type hints on application code
- no uncaught provider or model exceptions
- every node must either return a valid partial state update or terminate cleanly with recorded errors
- `max_loops` must come from config or state, never node-local constants
- `eval` mode must never silently fall back to mocks
- citations must only reference sources present in state
- do not claim restart-safe persistence unless the checkpointer actually supports it
- run tests before moving to the next week

---

## Core State and Interface Rules

Before implementation, define and keep stable:

### State requirements

`ResearchState` should include:

- topic
- mode
- status
- current queries
- loop count
- max loops
- search results
- findings
- synthesis draft
- human review decision
- final report
- token usage
- node timings
- run metadata
- errors

### Supporting models

Include at minimum:

- `Finding`
- `Source`
- `SearchResult`
- `SynthesisDraft`
- `HumanReview`
- `FinalReport`
- `TokenUsage`
- `NodeTiming`
- `RunMetadata`

### Computed helpers

Add only helpers that reduce graph complexity:

- `all_findings`
- `all_sources`
- `latest_gaps`
- `should_search_again`
- `with_error()`

### Node contract rule

Each node should document:

- required input fields
- fields it may update
- how it reports recoverable failure
- what terminal failure looks like

---

## Week 1 — Skeleton, config, and stable state design

**Goal**: a runnable graph with stub agents and a trustworthy state contract.

### Tasks

- [ ] Create `config.py` with:
  - mode selection: `dev`, `live`, `eval`
  - model name
  - search provider
  - report format default
  - `max_loops`
- [ ] Create `state.py` with full schema:
  - `ResearchState`
  - `Finding`
  - `Source`
  - `SearchResult`
  - `SynthesisDraft`
  - `HumanReview`
  - `FinalReport`
  - `TokenUsage`
  - `NodeTiming`
  - `RunMetadata`
- [ ] Add useful computed helpers:
  - `all_findings`
  - `all_sources`
  - `latest_gaps`
  - `should_search_again`
  - `with_error()`
- [ ] Create `graph.py` with stub nodes:
  - `search_agent`
  - `synthesis_agent`
  - `human_review`
  - `report_agent`
- [ ] Wire graph edges, including conditional routing after synthesis
- [ ] Create deterministic stub outputs suitable for tests
- [ ] Create `tests/test_state.py` and `tests/test_graph.py`
- [ ] Create `requirements.txt` and `.env.example`

### Stub behavior

Each stub node must:

- log which node ran and current loop count
- return fake but schema-valid data
- update status
- update token usage and timing with stub values

### Acceptance criteria

- `python graph.py` completes in `dev` mode
- final state reaches a terminal success status
- final state contains at least one finding and one source
- loop count never exceeds configured max
- tests pass

---

## Week 2 — Search agent, web tools, and structured output

**Goal**: replace the search stub with a real search node while preserving local development ergonomics.

### Tasks

- [ ] Create `tools/web.py` with:
  - `web_search(query: str) -> list[SearchResult]`
  - `fetch_page(url: str) -> str`
- [ ] Support at least one real search provider
- [ ] Allow mock fallback only in `dev` mode
- [ ] Mark search results as `mock` or `live`
- [ ] Normalize raw provider responses into a stable schema
- [ ] Create `agents/search.py` with `SearchOutput` schema
- [ ] Use explicit tool binding for structured output
- [ ] Implement corrective retry on malformed tool output
- [ ] Bound retries and record failure details in state
- [ ] Replace the stub block in `graph.py` search node with the real implementation
- [ ] Extract actual token usage when available and store it in state
- [ ] Add `tests/test_agents.py` for:
  - schema validation
  - prose-response rejection
  - wrong-tool rejection
  - retry exhaustion
  - state update shape
  - `dev` fallback behavior
  - `eval` mode failure if mocks would be required

### Recommended `SearchOutput`

```python
class SearchOutput(BaseModel):
    findings: list[Finding]
    gaps: list[str]
    follow_up_queries: list[str]
    sources: list[Source]
    reasoning: str
```

All fields required.

### Acceptance criteria

- search node returns typed findings and sources in `live` mode
- `dev` mode runs without search credentials
- `eval` mode fails fast if it would use mocks
- tests pass

---

## Week 3 — Synthesis agent and controlled search loop

**Goal**: produce a useful synthesis draft and only loop when more search is justified.

### Tasks

- [ ] Create `agents/synthesis.py` with `SynthesisDraft`:
  ```python
  class SynthesisDraft(BaseModel):
      draft: str
      remaining_gaps: list[str]
      confidence: float
      needs_more_search: bool
      follow_up_queries: list[str]
  ```
- [ ] Implement the synthesis agent using structured output
- [ ] Include all findings and all sources in the synthesis input
- [ ] Make gap detection specific and actionable
- [ ] Route back to search only when all are true:
  - `needs_more_search` is `True`
  - `remaining_gaps` is non-empty
  - `loop_count < max_loops`
- [ ] When looping, use refined follow-up queries rather than the original topic
- [ ] If `max_loops` is reached, continue with limitations recorded in state
- [ ] Add tests for:
  - topic with real unresolved gaps
  - topic with sufficient coverage
  - loop cap respected
  - limitations recorded when loop cap blocks further search

### Acceptance criteria

- synthesis output always contains either actionable follow-up queries or a clear statement that coverage is sufficient
- graph loops only when justified by state
- loop count never exceeds configured max
- tests pass

---

## Week 4 — Report agent and end-to-end non-interactive pipeline

**Goal**: produce usable cited reports before adding interactive review complexity.

### Tasks

- [ ] Create `agents/report.py` with two formats:

  **Executive brief**
  - Title
  - 3-sentence executive summary
  - 5 key findings
  - recommendations
  - inline citations

  **Deep dive**
  - Title
  - executive summary
  - narrative body with sections
  - integrated findings with inline citations
  - gaps and limitations
  - source list

- [ ] Generate reports from:
  - synthesis draft
  - findings
  - source metadata
  - known limitations
- [ ] Enforce citation integrity:
  - every inline citation must resolve to a saved source
  - no bibliography entry may appear unless it exists in state
  - unsupported claims should be omitted or labeled as open questions
- [ ] Add word count validation with warnings, not hard failures
- [ ] Create `run_pipeline.py` for non-interactive runs with auto-approve
- [ ] Create `save_run()` to persist completed `ResearchState` as JSON
- [ ] Save:
  - topic
  - mode
  - model
  - timings
  - token usage
  - final report
  - source list
  - errors
- [ ] Add tests for:
  - citation-source consistency
  - report format validation
  - saved JSON structure
  - auto-approve path

### Acceptance criteria

- `run_pipeline.py` completes end to end in `live` mode
- successful runs persist JSON artifacts
- reports contain inline citations and a source list
- no citation points to a missing source
- tests pass

---

## Week 5 — Human review and checkpoint/resume

**Goal**: add a real human review step without lying about persistence behavior.

### Tasks

- [ ] Create `agents/human_review.py` using `interrupt(...)`
- [ ] Present review payload with:
  - draft
  - key findings
  - sources
  - unresolved gaps
  - loop count
- [ ] Accept structured human input:
  - `approved`
  - `edited_draft`
  - `additional_queries`
  - `notes`
  - `rejected`
- [ ] Create `cli_review.py`:
  - run until interrupt
  - display review payload
  - prompt for approve, edit, add queries, reject
  - resume execution with structured input
- [ ] Route review outcomes:
  - approved with no queries -> report
  - approved with queries -> one more search cycle
  - rejected -> terminate cleanly with reason recorded
- [ ] Choose and document one persistence story:

  **Option A: in-process only**
  - use `MemorySaver`
  - do not claim cross-process restart support

  **Option B: restart-safe**
  - use a durable checkpointer
  - document exact resume flow after process restart

- [ ] Add tests for:
  - interrupt payload shape
  - resume behavior
  - edited draft path
  - additional queries path
  - persistence behavior matching the chosen checkpointer

### Acceptance criteria

- a paused run can be inspected
- a human can approve, edit, add queries, or reject
- resume behavior is documented and tested
- no mismatch exists between persistence claims and actual implementation
- tests pass

---

## Week 6 — Evaluation, cost tracking, and documentation

**Goal**: measure the system honestly and present it clearly.

### Tasks

- [ ] Create `evals/eval.py`
- [ ] Load saved `eval` runs only
- [ ] Score runs on:
  - citation integrity
  - source validity
  - topical coverage
  - unsupported-claim rate
  - loop discipline
- [ ] Recommended heuristic definitions:

  **Citation integrity**
  - fraction of inline citations that resolve to saved sources

  **Source validity**
  - URL has valid scheme and host
  - optional reachability check if network is available

  **Topical coverage**
  - overlap between topic terms and report sections
  - presence of limitations if gaps remained

  **Unsupported-claim rate**
  - flag factual paragraphs without citations

  **Loop discipline**
  - full score when loop count stays within limits and each extra loop has a recorded rationale

- [ ] Record actual token usage from model response metadata
- [ ] Record elapsed time per node with `time.perf_counter()`
- [ ] Estimate per-node and total cost from configured model pricing
- [ ] Add a compact cost summary printer
- [ ] Run and save 5 real eval topics in `eval` mode
- [ ] Update `README.md` with:
  - what the project does
  - architecture overview
  - mode explanation
  - quickstart
  - one real example run
  - known limitations
  - real debugging notes only if they actually happened
- [ ] Add tests for eval artifact loading and summary calculations

### Suggested eval topics

```python
EVAL_TOPICS = [
    "impact of LLMs on software developer productivity",
    "state of multi-agent AI systems in 2025",
    "LangGraph vs CrewAI vs AutoGen comparison",
    "prompt engineering techniques for structured output",
    "AI agent memory architectures",
]
```

### Acceptance criteria

- eval script runs on saved eval artifacts
- cost summary prints for completed runs
- README explains the system clearly without overstating claims
- tests pass

---

## Quick Reference Patterns

### Structured tool call

```python
llm_with_tools = llm.bind(
    tools=[MY_TOOL],
    tool_choice={"type": "tool", "name": "my_tool_name"},
)
```

### Corrective retry after validation failure

```python
messages = messages + [
    response,
    ToolMessage(
        content=f"Validation error: {e}. Please retry.",
        tool_call_id=response.tool_calls[0]["id"],
    ),
    HumanMessage(content="Retry with corrections."),
]
```

### Conditional edge routing

```python
builder.add_conditional_edges(
    "synthesis_agent",
    route_after_synthesis,
    {
        "search_agent": "search_agent",
        "report_agent": "report_agent",
    },
)
```

### Resume from checkpoint

```python
config = {"configurable": {"thread_id": "my-thread"}}
saved = graph.get_state(config)
graph.update_state(config, human_input)
graph.invoke(None, config=config)
```

Use this pattern only if it matches the chosen checkpointer model.

---

## Done When

A technical reviewer can:

1. run the project in `dev` mode without provider credentials
2. run it in `live` mode with real credentials
3. inspect a saved run artifact
4. verify that citations resolve to real saved sources
5. see that loop behavior respects config
6. see that persistence behavior matches what the README claims

If those conditions are met, the project is in good shape.
