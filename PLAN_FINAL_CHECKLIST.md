# PLAN_FINAL Execution Checklist

## Week 1

- [ ] Add `config.py`
- [ ] Finalize `ResearchState` and supporting models
- [ ] Add computed helpers and error helper
- [ ] Wire stub graph with conditional routing
- [ ] Add deterministic stub timing and token values
- [ ] Add `.env.example`
- [ ] Split tests into `tests/test_state.py` and `tests/test_graph.py`
- [ ] Verify `python graph.py`
- [ ] Verify `pytest`

## Week 2

- [ ] Build `tools/web.py`
- [ ] Support one real search provider
- [ ] Add `dev`-only mock fallback
- [ ] Implement `agents/search.py`
- [ ] Add structured output validation and retry
- [ ] Track real token usage when available
- [ ] Add search-agent tests

## Week 3

- [ ] Implement `agents/synthesis.py`
- [ ] Add actionable gap detection
- [ ] Refine loop routing logic
- [ ] Record limitations when loop cap is reached
- [ ] Add synthesis-loop tests

## Week 4

- [ ] Implement `agents/report.py`
- [ ] Add `run_pipeline.py`
- [ ] Persist completed runs as JSON
- [ ] Enforce citation integrity
- [ ] Add report and persistence tests

## Week 5

- [ ] Implement `agents/human_review.py` with `interrupt(...)`
- [ ] Add `cli_review.py`
- [ ] Support approve, edit, query, reject flows
- [ ] Choose persistence model and document it
- [ ] Add checkpoint and resume tests

## Week 6

- [ ] Implement `evals/eval.py`
- [ ] Save 5 real eval runs
- [ ] Add per-node timing, token, and cost summaries
- [ ] Update `README.md`
- [ ] Add eval tests
- [ ] Verify end-to-end runs in `dev`, `live`, and `eval`
