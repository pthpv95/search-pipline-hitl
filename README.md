# Research Assistant with Human-in-the-Loop

A LangGraph-based research pipeline that orchestrates search, synthesis, human review, and report generation.

## How it works

```
search_agent → synthesis_agent → [need more?] → human_review → report_agent → END
                                      ↓
                                 search_agent (loop)
```

All agents are currently stubs — no LLM calls. They will be replaced incrementally week by week.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run the graph end-to-end
python graph.py

# Run tests
pytest test_graph.py -v
```

## Project Structure

| File              | Purpose                                    |
|-------------------|--------------------------------------------|
| `state.py`        | Pydantic state schema and sub-models       |
| `graph.py`        | LangGraph nodes, edges, and graph builder  |
| `test_graph.py`   | Tests                                      |
| `architecture.md` | Detailed architecture diagram              |
