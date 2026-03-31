# Multi-Agent Research Pipeline — Revised Build Plan

> This file replaces the execution guidance in `PLAN.md`.
> Do not modify `PLAN.md`; use this plan for implementation.
> Build sequentially, but optimize for working software and honest evaluation over tutorial-style milestone counts.

---

## Project Goal

Build a research pipeline that:

- accepts a topic
- performs targeted web research
- synthesizes findings into a draft
- pauses for human review
- produces a cited markdown report
- saves enough state to inspect and resume runs

The finished project should be reliable in local development and credible as a portfolio piece.

---

## Non-Goals

Do not optimize for:

- exact test counts
- exact loop counts for a default topic
- exact token totals in sample output
- fake "production-grade" claims when running with mock search data

---

## Operating Modes

Define these modes explicitly from the start.

### `dev`

Purpose:
fast local iteration without external API dependencies

Rules:

- mock web search is allowed
- report generation may use stubbed or cached inputs
- acceptance criteria should validate behavior, not quality claims

### `live`

Purpose:
real end-to-end execution with external search and LLM calls

Rules:

- uses real search provider and real model calls
- citations must map to real sources
- saved runs from this mode may be used for demos

### `eval`

Purpose:
generate comparable runs for assessment

Rules:

- no mock search results
- every source must be real and persisted
- the run metadata must record provider, model, timings, and token usage

---

## Target Repository Shape

```text
research_agent/
├── state.py
├── graph.py
├── run_pipeline.py
├── cli_review.py
├── config.py
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

`config.py` is added to avoid scattering provider settings, loop limits, and mode switches.

---

## Core Design Rules

These rules apply throughout the build.

1. State transitions must be explicit and typed.
2. Every node must either:
   - return a valid partial state update, or
   - record an error in state and terminate cleanly.
3. `max_loops` must always come from configuration or state, never from node-local constants.
4. Human review must use a dynamic interrupt pattern, not static breakpoints for core workflow logic.
5. If restart-safe persistence is a requirement, use a durable checkpointer. Do not rely on `MemorySaver` for cross-process durability.
6. Evals must never run on mocked search results.
7. Acceptance criteria should verify invariants, not exact incidental outputs.

---

## Phase 1 — State, config, and skeleton graph

**Goal**: a runnable graph with stubbed agents and a stable state contract.

### Build

- Create `config.py` with:
  - mode selection: `dev`, `live`, `eval`
  - model name
  - search provider
  - `max_loops`
  - report format defaults
- Create `state.py` with:
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
- Add computed helpers only if they reduce graph complexity:
  - `all_findings`
  - `all_sources`
  - `latest_gaps`
  - `should_search_again`
  - `with_error()`
- Create `graph.py` with stub nodes:
  - `search_agent`
  - `synthesis_agent`
  - `human_review`
  - `report_agent`
- Make node outputs realistic but deterministic enough for tests.

### Define node contracts

Each node should clearly document:

- required input state fields
- fields it may update
- terminal failure behavior

### Tests

- State model validation
- Graph wiring
- Conditional routing
- Error recording

### Acceptance criteria

- `python graph.py` completes from start to finish in `dev` mode
- final state has:
  - terminal status
  - at least one finding
  - at least one source
  - no unhandled exception
- tests pass

---

## Phase 2 — Real search layer with dev fallback

**Goal**: replace the stub search node with a real search pipeline that still supports local development.

### Build

- Create `tools/web.py` with:
  - `web_search(query: str) -> list[SearchResult]`
  - `fetch_page(url: str) -> str`
- Support at least one real provider.
- Allow fallback mock results only in `dev` mode.
- Normalize search results into a stable schema before they reach the agent.
- Record whether a result is `mock` or `live`.

### Search agent

- Create `agents/search.py`
- Define `SearchOutput`
- Implement tool-driven structured extraction
- Validate outputs with Pydantic
- Add corrective retry logic for malformed tool responses
- Bound retries and record failure details in state

### Tests

- schema validation
- parsing failures
- retry exhaustion
- `dev` mode fallback behavior
- `eval` mode rejection when provider credentials are missing

### Acceptance criteria

- search node returns typed findings and sources in `live` mode
- `dev` mode can run without external credentials
- `eval` mode fails fast if it would have to use mocks
- tests pass

---

## Phase 3 — Synthesis and controlled loop logic

**Goal**: produce a synthesis draft and only loop when there is a concrete reason.

### Build

- Create `agents/synthesis.py`
- Define `SynthesisDraft` with:
  - draft body
  - unresolved gaps
  - confidence
  - `needs_more_search`
  - recommended follow-up queries
- Route back to search only when:
  - `needs_more_search` is true
  - unresolved gaps are non-empty
  - `loop_count < max_loops`
- When looping, carry forward only the refined follow-up queries rather than the full original prompt.

### Guardrails

- Gaps must be specific and answerable.
- The agent must not request another loop only because confidence is imperfect.
- If `max_loops` is reached, the pipeline must continue with explicit limitations recorded in state.

### Tests

- loops when gaps are concrete
- does not loop when topic is sufficiently covered
- respects `max_loops`
- records limitations when further search is blocked by loop cap

### Acceptance criteria

- graph loops only when justified by state
- loop count never exceeds configured max
- synthesis output always includes either:
  - follow-up queries, or
  - a clear statement that coverage is sufficient

---

## Phase 4 — Human review and durable resume

**Goal**: pause for a human decision and resume safely.

### Build

- Create `agents/human_review.py` using `interrupt(...)`
- Present review payload with:
  - draft
  - key findings
  - sources
  - unresolved gaps
  - loop count
- Resume with structured human input:
  - `approved`
  - `edited_draft`
  - `additional_queries`
  - `notes`
  - `rejected`

### Persistence

Pick one of these paths and state it clearly in the implementation:

1. In-process checkpointing only
   - use `MemorySaver`
   - do not claim cross-process resume

2. Cross-process resume
   - use a durable checkpointer
   - document how runs are resumed after interpreter restart

The preferred path for this project is option 2 if the goal is portfolio credibility.

### CLI

- Create `cli_review.py`
- Run graph until interrupt
- print review payload cleanly
- accept approve, edit, add-query, reject
- resume execution with structured input

### Routing after review

- approved with no extra queries -> report
- approved with extra queries -> one more search cycle
- rejected -> terminate with reviewed status and reason

### Tests

- interrupt payload shape
- resume behavior
- edited draft is used downstream
- additional queries trigger one more search pass
- persistence behavior matches the chosen checkpointer model

### Acceptance criteria

- a paused run can be inspected
- a human can edit or reject the draft
- resume behavior is documented and tested
- no mismatch exists between persistence claims and actual implementation

---

## Phase 5 — Reporting and citation integrity

**Goal**: generate useful reports without hallucinated claims or fake citations.

### Build

- Create `agents/report.py`
- Support two formats:
  - `executive_brief`
  - `deep_dive`
- Generate reports from:
  - approved draft or edited draft
  - findings
  - source metadata
  - known limitations

### Citation rules

- Every inline citation must resolve to a source in `state.all_sources`.
- No source may appear in the bibliography unless it exists in state.
- If a claim lacks source support, it must be omitted or labeled as an open question.

### Validation

- word count bounds by format
- citation index consistency
- source list non-empty in `live` and `eval` modes
- warning for format drift, not hard failure

### Run persistence

- Add `save_run()` to write final state JSON
- Save:
  - topic
  - mode
  - model
  - timings
  - token usage
  - final report
  - source list
  - errors

### Tests

- citation references map to real saved sources
- edited draft path is honored
- report format validation
- saved JSON structure

### Acceptance criteria

- `run_pipeline.py` runs end to end in `live` mode
- successful runs persist JSON artifacts
- reports contain inline citations and a source list
- no citation points to a missing source

---

## Phase 6 — Evaluation, cost accounting, and documentation

**Goal**: measure runs honestly and document the system clearly.

### Build eval pipeline

- Create `evals/eval.py`
- Load saved `eval` runs only
- Score each run on:
  - citation integrity
  - source validity
  - topical coverage
  - unsupported-claim rate
  - loop discipline

### Recommended heuristics

Use lightweight heuristics, but keep them honest:

- `citation_integrity`
  - fraction of inline citations that resolve to known sources
- `source_validity`
  - URL has valid scheme and host
  - optional live reachability check if network is available
- `topical_coverage`
  - overlap between topic keywords and report sections
  - presence of a limitations section for unresolved gaps
- `unsupported_claim_rate`
  - flag paragraphs with factual language but no citation
- `loop_discipline`
  - full score when loop count is within limit and each extra loop has recorded rationale

Do not define efficiency as "one loop is always better than two."

### Cost and latency

- record per-node input and output tokens
- record elapsed time per node
- estimate cost from configured model pricing
- print a compact run summary

### Documentation

Update `README.md` with:

- what the project does
- architecture overview
- mode explanation: `dev`, `live`, `eval`
- quickstart
- one real example run
- known limitations
- two real debugging notes only if they actually happened

Do not pad the README with invented lessons.

### Acceptance criteria

- eval script runs on saved eval artifacts
- cost summary prints for completed runs
- README explains the system to a new reader without overstating claims

---

## Cross-Cutting Quality Bar

Every phase must preserve these properties:

- fully typed Python
- deterministic tests where practical
- no silent fallback from `eval` mode to mocks
- no uncaught model or provider exceptions
- no fabricated citations
- no persistence claims the implementation cannot support

---

## Suggested Milestone Order

1. Phase 1 with stubbed graph
2. Phase 2 search integration
3. Phase 3 synthesis loop
4. Phase 5 reporting on top of auto-approve flow
5. Phase 4 human review and durable resume
6. Phase 6 evaluation and README polish

This order is intentional. It gets the main pipeline working before spending time on interactive review UX.

---

## Done When

A technical reviewer can:

1. run the pipeline in `dev` mode without provider credentials
2. run it in `live` mode with real credentials
3. inspect a saved run artifact
4. verify that citations resolve to real saved sources
5. see that resume and persistence behavior match the documented checkpointer design

If those conditions are true, the project is credible. If not, it still needs work.
