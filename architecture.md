# Research Assistant — Architecture Diagram

## High-Level Flow

```
                        +----------------+
                        |   INPUT        |
                        |  topic,        |
                        |  report_format,|
                        |  max_loops     |
                        +-------+--------+
                                |
                                v
                     +----------+----------+
                     |    search_agent     |
                     |                     |
                     |  Searches for info  |
                     |  Returns: findings, |
                     |  sources, gaps      |
                     +----------+----------+
                                |
                                v
                     +----------+----------+
                     |  synthesis_agent    |
                     |                     |
                     |  Combines findings  |
                     |  into a draft       |
                     +----------+----------+
                                |
                                v
                       +--------+--------+
                      / should_search    \
                     /  _again?           \
                    +---------------------+
                    |  loop_count          |
                    |   < max_loops        |
                    |  AND                 |
                    |  needs_more_search   |
                    +-----+----------+----+
                          |          |
                     YES  |          |  NO
                          |          |
            (loop back)   |          v
                          |  +-------+---------+
                          |  |  human_review    |
                          |  |                  |
                          |  |  interrupt() for |
                          |  |  HITL review     |
                          |  +-------+----------+
                          |          |
                          |     +----+----+
                          |    / review    \
                          |   /  outcome?   \
                          |  +--------------+
                          |  |              |
                          |  | APPROVE      | APPROVE         REJECT
                          |  | (no queries) | + queries       |
                          |  |              | (under cap)     v
                          |  |              |             +---+---+
                          |  |              +--+          |  END  |
                          |  v                 |          | FAILED|
                          |  +-------+----+    |          +-------+
                          |  | report_agent|   |
                          |  |             |   |
                          |  | Writes final|   |
                          |  | cited report|   |
                          |  +-------+-----+   |
                          |          |         |
                          |          v         |
                          |      +---+---+     |
                          |      |  END  |     |
                          |      +-------+     |
                          |                    |
                          +--------------------+
                          (back to search_agent)
```

## Example: max_loops = 2

```
Loop 1:  search_agent --> synthesis_agent --> needs more? YES
Loop 2:  search_agent --> synthesis_agent --> needs more? NO (hit max)
         --> human_review (interrupt) --> approve --> report_agent --> END
```

## Entry Points

| Runner           | File              | Review mode                |
|------------------|-------------------|----------------------------|
| `run_pipeline.py`| Non-interactive   | Auto-approves at interrupt |
| `cli_review.py`  | Interactive CLI   | Prompts for approve/edit/query/reject |
| `graph.py`       | Smoke test        | Auto-approves at interrupt |

## State Ownership (which node writes what)

```
+-------------------+----------------------------------------------------------+
| Node              | Fields it writes                                         |
+-------------------+----------------------------------------------------------+
| search_agent      | search_results, loop_count, current_queries,             |
|                   | token_usage, node_timings, status, errors                |
+-------------------+----------------------------------------------------------+
| synthesis_agent   | synthesis_draft, current_queries,                         |
|                   | token_usage, node_timings, status, errors                |
+-------------------+----------------------------------------------------------+
| human_review      | human_review, current_queries (if additional_queries),    |
|                   | node_timings, status, errors                             |
+-------------------+----------------------------------------------------------+
| report_agent      | final_report, token_usage, node_timings, status, errors  |
+-------------------+----------------------------------------------------------+
```

## State Model (state.py)

```
ResearchState
|
|-- topic                  (input)
|-- mode                   (dev | live | eval)
|-- report_format          (input: "deep_dive" | "executive_brief")
|-- max_loops              (input: default 2)
|
|-- search_results[]       SearchResult
|   |-- findings[]             Finding { content, source_url, confidence }
|   |-- gaps[]                 unanswered questions
|   |-- follow_up_queries[]    queries for next loop
|   |-- sources[]              Source { url, title, snippet, relevance_score }
|   +-- tokens_used
|
|-- synthesis_draft        SynthesisDraft
|   |-- draft                  markdown text
|   |-- remaining_gaps[]       what's still unanswered
|   |-- confidence
|   |-- needs_more_search      controls the loop
|   |-- follow_up_queries[]    refined queries for next loop
|   +-- limitations[]          recorded when loop cap blocks further search
|
|-- human_review           HumanReview
|   |-- approved
|   |-- rejected
|   |-- rejection_reason
|   |-- edited_draft           optional edits (preserved through query loops)
|   |-- additional_queries[]   triggers extra search cycle if under loop cap
|   +-- notes
|
|-- final_report           FinalReport
|   |-- title, executive_summary, body
|   |-- sources[], format, word_count
|
|-- token_usage            TokenUsage { search_agent, synthesis_agent, report_agent, total }
|-- node_timings           NodeTiming { search_agent, synthesis_agent, report_agent, human_review, total }
|-- run_metadata           RunMetadata { model_name, search_provider, thread_id }
|-- errors[]               accumulated error messages
+-- status                 tracks current phase (searching/synthesizing/...)
```

## Implementation Status

| Week | Node             | What was implemented                                  |
|------|------------------|-------------------------------------------------------|
| 1    | (all)            | Stub graph, state schema, config, conditional routing |
| 2    | search_agent     | Real Claude calls + Tavily web search, structured output, retry |
| 3    | synthesis_agent  | Structured synthesis, gap detection, loop control     |
| 4    | report_agent     | Cited reports (deep dive + executive brief), run persistence |
| 5    | human_review     | interrupt() HITL, cli_review.py, approve/edit/query/reject |

## Persistence

- **In-process**: `MemorySaver` checkpointer — supports interrupt/resume within a single process
- **Run artifacts**: `save_run()` persists completed runs as JSON in `runs/` directory
- Cross-process restart is not supported (Option A from PLAN_FINAL)
