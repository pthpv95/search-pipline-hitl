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
                          |  |  HITL checkpoint |
                          |  |  (auto-approves  |
                          |  |   for now)       |
                          |  +-------+----------+
                          |          |
                          |          v
                          |  +-------+----------+
                          |  |  report_agent    |
                          |  |                  |
                          |  |  Writes final    |
                          |  |  report from     |
                          |  |  approved draft  |
                          |  +-------+----------+
                          |          |
                          |          v
                          |      +---+---+
                          |      |  END  |
                          |      +-------+
                          |
                          +----> (back to search_agent)
```

## Example: max_loops = 2

```
Loop 1:  search_agent --> synthesis_agent --> needs more? YES
Loop 2:  search_agent --> synthesis_agent --> needs more? NO (hit max)
         --> human_review --> report_agent --> END
```

## State Ownership (which node writes what)

```
+-------------------+--------------------------------------------------+
| Node              | Fields it writes                                 |
+-------------------+--------------------------------------------------+
| search_agent      | search_results, loop_count, token_usage, status  |
| synthesis_agent   | synthesis_draft, current_queries, status          |
| human_review      | human_review, status                             |
| report_agent      | final_report, status                             |
+-------------------+--------------------------------------------------+
```

## State Model (state.py)

```
ResearchState
|
|-- topic                  (input)
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
|   +-- needs_more_search      controls the loop
|
|-- human_review           HumanReview
|   |-- approved
|   |-- edited_draft           optional edits
|   |-- additional_queries[]
|   +-- notes
|
|-- final_report           FinalReport
|   |-- title, executive_summary, body
|   |-- sources[], format, word_count
|
+-- status                 tracks current phase (searching/synthesizing/...)
```

## Stub Replacement Roadmap

All nodes are stubs today (Day 1). Each gets replaced in a future week:

| Week | Node             | What changes                          |
|------|------------------|---------------------------------------|
| 2    | search_agent     | Real Claude calls + web search tools  |
| 3    | synthesis_agent  | Multi-turn Claude synthesis           |
| 4    | human_review     | langgraph.interrupt() for real HITL   |
| 5    | report_agent     | Claude-powered report writing         |
