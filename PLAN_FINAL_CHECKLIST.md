# PLAN_FINAL Execution Checklist

## Week 1

- [x] Add `config.py`
- [x] Finalize `ResearchState` and supporting models
- [x] Add computed helpers and error helper
- [x] Wire stub graph with conditional routing
- [x] Add deterministic stub timing and token values
- [x] Add `.env.example`
- [x] Split tests into `tests/test_state.py` and `tests/test_graph.py`
- [x] Verify `python graph.py`
- [x] Verify `pytest`

## Week 2

- [x] Build `tools/web.py`
- [x] Support one real search provider
- [x] Add `dev`-only mock fallback
- [x] Implement `agents/search.py`
- [x] Add structured output validation and retry
- [x] Track real token usage when available
- [x] Add search-agent tests

## Week 3

- [x] Implement `agents/synthesis.py`
- [x] Add actionable gap detection
- [x] Refine loop routing logic
- [x] Record limitations when loop cap is reached
- [x] Add synthesis-loop tests

## Week 4

- [x] Implement `agents/report.py`
- [x] Add `run_pipeline.py`
- [x] Persist completed runs as JSON
- [x] Enforce citation integrity
- [x] Add report and persistence tests

## Week 5

- [x] Implement `agents/human_review.py` with `interrupt(...)`
- [x] Add `cli_review.py`
- [x] Support approve, edit, query, reject flows
- [x] Choose persistence model and document it
- [x] Add checkpoint and resume tests

## Week 6

- [ ] Implement `evals/eval.py`
- [ ] Save 5 real eval runs
- [ ] Add per-node timing, token, and cost summaries
- [ ] Update `README.md`
- [ ] Add eval tests
- [ ] Verify end-to-end runs in `dev`, `live`, and `eval`
