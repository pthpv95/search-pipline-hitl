# Multi-Agent Research Pipeline — 6-Week Build Plan

> **Instructions for Claude Code**: This file is your execution guide.
> Work through each week sequentially. Complete all tasks and verify all
> acceptance criteria before moving to the next week. Run tests after
> every meaningful change. Ask for clarification if a requirement is ambiguous.

---

## Project Overview

Build a production-grade multi-agent research pipeline using LangGraph and
Claude's tool-use API. The pipeline takes a research topic and produces a
polished final report, coordinating three specialized agents with a
human-in-the-loop checkpoint and a controlled search-synthesis loop.

### Repository structure (target end state)

```
research_agent/
├── state.py              # ResearchState schema — single source of truth
├── graph.py              # LangGraph graph — nodes, edges, compilation
├── agents/
│   ├── __init__.py
│   ├── search.py         # Search agent (Week 2)
│   ├── synthesis.py      # Synthesis agent (Week 3)
│   ├── human_review.py   # HITL checkpoint (Week 4)
│   └── report.py         # Report agent (Week 5)
├── tools/
│   ├── __init__.py
│   └── web.py            # web_search and fetch_page tool definitions
├── evals/
│   ├── __init__.py
│   ├── runs/             # Saved end-to-end runs (JSON)
│   └── eval.py           # Evaluation script (Week 6)
├── tests/
│   ├── test_state.py     # State schema tests
│   ├── test_graph.py     # Graph structure and flow tests
│   └── test_agents.py    # Per-agent unit tests (Week 2+)
├── requirements.txt
├── .env.example
└── README.md
```

### Environment setup

```bash
pip install langgraph langchain-anthropic langchain-core pydantic pytest pytest-asyncio
export ANTHROPIC_API_KEY=your_key_here
```

---

## Week 1 — Project skeleton + state design

**Goal**: A fully wired graph that runs end-to-end with stub agents.
No LLM calls yet. All 18 tests pass.

### Tasks

- [ ] Create `state.py` with the full `ResearchState` schema including all
      sub-models: `Finding`, `Source`, `SearchResult`, `SynthesisDraft`,
      `HumanReview`, `FinalReport`, `TokenUsage`
- [ ] Add computed properties to `ResearchState`:
      `all_findings`, `all_sources`, `should_search_again`, `latest_gaps`,
      `with_error()`
- [ ] Create `graph.py` with four stub nodes: `search_agent`,
      `synthesis_agent`, `human_review_node`, `report_agent`
- [ ] Wire all edges including the conditional edge from `synthesis_agent`
      using `route_after_synthesis()`
- [ ] Compile graph with `MemorySaver` checkpointer
- [ ] Create `tests/test_state.py` and `tests/test_graph.py`
- [ ] Create `requirements.txt` and `.env.example`

### Stub behaviour

Each stub node must:
- Print which node is running and current loop count
- Return realistic fake data that matches the output schema
- Update `status` and `token_usage` fields

### Acceptance criteria

```bash
python graph.py          # Must print full run summary with status: COMPLETE
pytest tests/ -v         # Must show 18 passed, 0 failed
```

Expected output from `python graph.py`:
```
Status:       GraphStatus.COMPLETE
Search loops: 2
Findings:     4
Sources:      2
Tokens used:  2400
Errors:       none
```

---

## Week 2 — Search agent: tools + structured output

**Goal**: Replace the search agent stub with a real Claude tool-use
implementation that returns validated structured output with retry on failure.

### Tasks

- [ ] Create `tools/web.py` with two tool definitions:
  - `web_search(query: str) -> list[dict]` — wraps a real search API
    (Tavily, Serper, or DuckDuckGo). If no API key is available, return
    realistic mock results so the rest of the pipeline still works.
  - `fetch_page(url: str) -> str` — fetches and extracts main text content
    from a URL using `requests` + `BeautifulSoup` or `trafilatura`
- [ ] Create `agents/search.py` with `SearchOutput` Pydantic schema and
      `SEARCH_TOOL` explicit tool definition (do not use
      `with_structured_output()` — use explicit `bind(tools=...,
      tool_choice=...)` for full control)
- [ ] Implement `search_with_corrective_retry(topic, max_attempts=3)`:
  - On failure: append bad response + `ToolMessage` with validation error
    back into conversation history, then retry
  - Use exponential backoff: `0.5 * attempt` seconds between retries
  - Raise `RuntimeError` after all attempts exhausted
- [ ] Replace the stub block in `graph.py`'s `search_agent` node with a
      call to the real implementation
- [ ] Add token usage tracking: extract actual token counts from the
      Claude API response metadata and store in `token_usage.search_agent`
- [ ] Add `tests/test_agents.py` with unit tests for:
  - `SearchOutput` schema validation (valid input, missing fields, wrong types)
  - `parse_tool_call()` raises on prose response and wrong tool name
  - Search node returns correct state dict shape

### Acceptance criteria

```bash
pytest tests/ -v                    # All tests pass
python -c "
from agents.search import search_with_corrective_retry
r = search_with_corrective_retry('LangGraph multi-agent systems')
print(f'Findings: {len(r.findings)}, Gaps: {len(r.gaps)}')
assert len(r.findings) > 0
assert len(r.gaps) > 0
print('OK')
"
```

### Structured output schema (`SearchOutput`)

```python
class SearchOutput(BaseModel):
    findings: list[Finding]
    gaps: list[str]
    follow_up_queries: list[str]
    sources: list[str]
    reasoning: str
```

All fields required. No `Optional` fields. If the model omits a field,
Pydantic raises `ValidationError` and the retry kicks in.

---

## Week 3 — Synthesis agent + controlled search loop

**Goal**: Build the synthesis agent that produces a structured draft,
detects gaps, and triggers a second search round when needed. The
conditional loop must fire exactly as many times as needed and no more.

### Tasks

- [ ] Create `agents/synthesis.py` with `SynthesisDraft` output schema:
  ```python
  class SynthesisDraft(BaseModel):
      draft: str                    # Markdown synthesis
      remaining_gaps: list[str]     # Still-unresolved questions
      confidence: float             # 0.0–1.0
      needs_more_search: bool       # Controls the loop
  ```
- [ ] Implement the synthesis agent using multi-turn conversation:
  - System prompt: instruct the model to act as a critical analyst
  - Include all findings from `state.all_findings` in the user message
  - Include all sources in the user message
  - Force structured output using explicit tool-use (same pattern as Week 2)
- [ ] Implement gap detection logic in the synthesis prompt:
  - The model must identify specific, answerable gaps (not vague ones)
  - Generate follow-up queries that are more specific than the original
  - Set `needs_more_search=True` only if gaps are significant
- [ ] Wire the conditional edge in `graph.py`:
  - `route_after_synthesis()` reads `state.should_search_again`
  - `should_search_again` returns `True` only when both:
    `synthesis_draft.needs_more_search is True` AND
    `loop_count < max_loops`
  - When routing back, update `state.current_queries` with
    `synthesis_draft.remaining_gaps`
- [ ] Add synthesis agent tests — verify with 3 different topics:
  - Short topic with obvious gaps → should trigger another loop
  - Detailed topic with complete coverage → should not trigger another loop
  - Test that `max_loops` cap is respected regardless of gap detection

### Acceptance criteria

```bash
pytest tests/ -v        # All tests pass
python graph.py         # Must show loop_count: 2 for default topic
```

Verify the loop behaviour manually by reading the printed node output:
```
[search_agent]    Loop: 1 / 2
[synthesis_agent] Gaps remain — looping back
[search_agent]    Loop: 2 / 2
[synthesis_agent] Synthesis complete — routing to human review
```

---

## Week 4 — Human-in-the-loop checkpoint

**Goal**: Implement a real HITL checkpoint using `interrupt()` with
persistent state via `MemorySaver`. The graph must be pausable,
inspectable, and resumable across Python process restarts.

### Tasks

- [ ] Create `agents/human_review.py` with the HITL node:
  ```python
  from langgraph.types import interrupt

  def human_review_node(state: ResearchState) -> dict:
      # Show the human what's ready for review
      review_payload = {
          "draft": state.synthesis_draft.draft,
          "gaps":  state.synthesis_draft.remaining_gaps,
          "sources": [s.url for s in state.all_sources],
          "loop_count": state.loop_count,
      }
      # Suspend execution here — graph is paused until resumed
      human_input = interrupt(review_payload)
      # human_input arrives when graph.update_state() is called
      return {
          "human_review": HumanReview(
              approved=human_input.get("approved", True),
              edited_draft=human_input.get("edited_draft"),
              additional_queries=human_input.get("additional_queries", []),
              notes=human_input.get("notes", ""),
          ),
          "status": GraphStatus.WRITING_REPORT,
      }
  ```
- [ ] Update `graph.py` to compile with `interrupt_before=["human_review"]`
      so the interrupt fires before the node executes (safer pattern)
- [ ] Build a CLI review interface in a new file `cli_review.py`:
  - Stream graph execution until interrupt
  - Display draft and gaps to the terminal
  - Prompt: approve / edit draft / add queries / reject
  - Resume graph with `graph.update_state(config, human_input)`
  - Continue streaming until `END`
- [ ] Demonstrate checkpoint persistence:
  - Start a run, let it hit the interrupt, kill the process
  - In a new process, load the saved state and resume from the checkpoint
  - Document the exact commands in a comment at the top of `cli_review.py`
- [ ] Handle the case where human adds additional queries:
  - If `human_review.additional_queries` is non-empty, route back to
    `search_agent` for one more round before writing the report
  - Add this as a second conditional edge from `human_review`

### CLI interface format

```
╔══════════════════════════════════════════╗
║  HUMAN REVIEW CHECKPOINT                 ║
╚══════════════════════════════════════════╝

SYNTHESIS DRAFT:
───────────────
[draft text here]

REMAINING GAPS:
───────────────
1. [gap 1]
2. [gap 2]

SOURCES USED: 4
SEARCH LOOPS: 2

Options:
  [a] Approve and generate report
  [e] Edit draft before continuing
  [q] Add more search queries
  [r] Reject and stop

Your choice:
```

### Acceptance criteria

```bash
# Run until interrupt
python cli_review.py --topic "AI in healthcare"

# Must pause at review checkpoint, show draft, accept input, resume
# After approval must complete and show: Status: COMPLETE

# Test persistence
pytest tests/test_graph.py::TestGraphFlow::test_checkpoint_persists_state -v
```

---

## Week 5 — Report agent + output quality

**Goal**: Build the report agent that produces clean, well-cited markdown
reports in two formats. Run five real end-to-end pipelines and save the
results as your eval dataset.

### Tasks

- [ ] Create `agents/report.py` with two report formats:

  **Executive brief** (target: 300–500 words):
  - Title
  - 3-sentence executive summary
  - 5 key findings as bullet points
  - Recommendations section
  - Inline citations `[1]` with numbered source list

  **Deep dive** (target: 800–1500 words):
  - Title + executive summary
  - Full narrative body with section headings
  - All findings integrated with inline citations
  - Gaps and limitations section
  - Full source list with titles and URLs

- [ ] Implement citation injection: the report agent must reference
      `state.all_sources` and insert `[n]` citations inline where findings
      are mentioned. Citations must be accurate — no hallucinated sources.

- [ ] Add word count validation: raise a warning (not an error) if the
      report is more than 20% outside the target range for its format.

- [ ] Create `evals/runs/` directory and a `save_run()` helper that saves
      the complete `ResearchState` as JSON after each successful pipeline run.

- [ ] Run the full pipeline on 5 real topics and save results:
  ```python
  EVAL_TOPICS = [
      "impact of LLMs on software developer productivity",
      "state of multi-agent AI systems in 2025",
      "LangGraph vs CrewAI vs AutoGen comparison",
      "prompt engineering techniques for structured output",
      "AI agent memory architectures",
  ]
  ```

- [ ] Create a `run_pipeline.py` script that runs a topic end-to-end
      non-interactively (auto-approves HITL) and saves the result.

### Report template structure

The system prompt for the report agent must include:
1. The approved synthesis draft (or human-edited version)
2. All findings with their source URLs
3. The target format (brief or deep-dive)
4. Explicit instruction to cite sources inline as `[1]`, `[2]` etc.
5. Instruction NOT to include information not present in the findings

### Acceptance criteria

```bash
# Run all 5 eval topics
python run_pipeline.py --topics all --format deep_dive --auto-approve

# Must produce 5 JSON files in evals/runs/
ls evals/runs/     # topic_1.json ... topic_5.json

# Each JSON must contain:
# - final_report.body with >500 words
# - final_report.sources with >0 entries
# - token_usage totals
# - errors: []
pytest tests/ -v   # All tests still pass
```

---

## Week 6 — Evals, cost tracking, and portfolio polish

**Goal**: Build a simple eval script, add per-node cost and latency
tracking, write a README with a real example, and record a demo.

### Tasks

#### Eval script (`evals/eval.py`)

- [ ] Load all JSON files from `evals/runs/`
- [ ] Score each run on three dimensions (simple heuristics, no LLM judge):

  **Source quality** (0–1):
  - Are all cited URLs reachable? (check with `requests.head()`)
  - Do sources URLs look real (has a domain, not localhost)?
  - Score: `valid_sources / total_sources`

  **Coverage** (0–1):
  - Did the pipeline address the original topic?
  - Keyword overlap between topic and report body
  - Score: `matching_keywords / topic_keywords`

  **Loop efficiency** (0–1):
  - Did the pipeline use the minimum loops needed?
  - Score: `1.0` if `loop_count == 1`, `0.5` if `loop_count == 2`

- [ ] Print a summary table:
  ```
  Topic                          | Source | Coverage | Efficiency | Total
  ------------------------------------------------------------------
  LLMs on developer productivity |  0.90  |   0.85   |    1.00    | 0.92
  Multi-agent AI systems         |  0.85  |   0.90   |    0.50    | 0.75
  ...
  Average                        |  0.88  |   0.87   |    0.75    | 0.83
  ```

#### Cost tracking (`graph.py` + all agent files)

- [ ] Extract actual token usage from Claude API response:
  ```python
  usage = response.response_metadata.get("usage", {})
  input_tokens  = usage.get("input_tokens", 0)
  output_tokens = usage.get("output_tokens", 0)
  ```
- [ ] Store per-node timing using `time.perf_counter()` — record start and
      end time for each node, store elapsed seconds in state metadata
- [ ] Add a `print_cost_summary()` function that prints:
  ```
  Node              | Tokens (in/out) | Time   | Est. Cost
  ---------------------------------------------------------
  search_agent      | 2400 / 800      | 4.2s   | $0.012
  synthesis_agent   | 3100 / 600      | 3.8s   | $0.010
  report_agent      | 2800 / 1200     | 5.1s   | $0.014
  ---------------------------------------------------------
  Total             | 8300 / 2600     | 13.1s  | $0.036
  ```
  Use claude-sonnet-4-6 pricing: `$3/M input, $15/M output`

#### README.md

Write a README that covers:
- [ ] What the project does (2 sentences)
- [ ] Architecture diagram (link to the mermaid file or embed as text)
- [ ] How to run it:
  ```bash
  export ANTHROPIC_API_KEY=...
  pip install -r requirements.txt
  python run_pipeline.py --topic "your topic" --format deep_dive
  ```
- [ ] One real worked example: include the actual output report from one
      of your 5 eval runs (copy the markdown into the README)
- [ ] What broke and how you fixed it (at least 2 real debugging stories
      from your build process — this is what makes a portfolio project
      credible vs a tutorial copy)
- [ ] Week-by-week what you learned (short, 1–2 sentences per week)

#### Final checks

- [ ] All tests pass: `pytest tests/ -v`
- [ ] Eval script runs: `python evals/eval.py`
- [ ] Cost summary prints for any run
- [ ] `python run_pipeline.py --topic "test" --format executive_brief`
      completes in under 60 seconds
- [ ] README is readable by a non-technical person

### Acceptance criteria

```bash
pytest tests/ -v                          # 0 failures
python evals/eval.py                      # prints scores table
python run_pipeline.py \
  --topic "LangGraph best practices" \
  --format executive_brief \
  --auto-approve                          # Status: COMPLETE, Errors: none
```

---

## Constraints that apply every week

- **Python version**: 3.11+
- **Type hints**: all functions must be fully typed
- **Error handling**: every LLM call wrapped in try/except with
  `state.with_error()` on failure — no unhandled exceptions
- **No global mutable state** outside of `MemorySaver`
- **Temperature**: always `0` for structured output calls
- **Max loops**: never hardcode `2` inside agent logic —
  always read from `state.max_loops`
- **Tests**: run `pytest tests/ -v` before moving to the next week.
  If any test fails, fix it before proceeding.
- **Commits**: commit after completing each week's acceptance criteria
  with message: `week-N: <one line description>`

---

## Quick reference: key patterns

### Forcing a tool call (use this everywhere)
```python
llm_with_tools = llm.bind(
    tools=[MY_TOOL],
    tool_choice={"type": "tool", "name": "my_tool_name"},
)
```

### Corrective retry on validation failure
```python
# Append to messages — do NOT retry with the same conversation
messages = messages + [
    response,                      # model's bad attempt
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
        "search_agent":  "search_agent",
        "human_review":  "human_review",
    },
)
```

### Resuming from a checkpoint
```python
config = {"configurable": {"thread_id": "my-thread"}}
saved  = graph.get_state(config)          # inspect paused state
graph.update_state(config, human_input)   # inject human response
graph.invoke(None, config=config)         # resume from checkpoint
```

---

## Done when

A technical person can clone the repo, set `ANTHROPIC_API_KEY`, run
`python run_pipeline.py --topic "X" --format deep_dive`, and receive a
well-cited markdown report in under 90 seconds with no errors.
