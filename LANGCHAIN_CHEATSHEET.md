# LangChain Cheatsheet

A quick-reference overview of LangChain, oriented around how this repo uses it.

## What it is

LangChain is a Python/JS framework for building applications around LLMs. It standardizes the **components** you stitch together (models, prompts, parsers, tools, retrievers) and the **runtime** that connects them. Think of it as the "glue layer" between your app code and any LLM provider.

## The mental model: Runnables

Everything in modern LangChain is a **Runnable** — an object with a uniform interface:

```python
chain = prompt | model | parser
chain.invoke({"topic": "bees"})
```

The `|` operator (LCEL — LangChain Expression Language) composes Runnables into pipelines. Every Runnable supports `.invoke()`, `.stream()`, `.batch()`, and async variants for free. Once you "get" Runnables, the rest is just specific implementations.

## Core building blocks

| Component | What it does | Example |
|---|---|---|
| **Chat models** | Provider-agnostic LLM interface | `ChatAnthropic`, `ChatOpenAI` |
| **Prompt templates** | Parameterized messages | `ChatPromptTemplate.from_messages([...])` |
| **Output parsers** | Coerce LLM text to structured data | `PydanticOutputParser`, `StrOutputParser` |
| **Tools** | Functions the LLM can call | `@tool` decorator, or `Tool.from_function` |
| **Retrievers** | Pull docs from a vector store / search | `vectorstore.as_retriever()` |
| **Memory** | Carry state across turns | legacy — modern code passes history explicitly |

## Structured output (the most-used feature)

```python
from pydantic import BaseModel

class Answer(BaseModel):
    summary: str
    confidence: float

structured_llm = model.with_structured_output(Answer)
result: Answer = structured_llm.invoke("Summarize bees")
```

This is how `agents/search.py`, `synthesis.py`, and `report.py` get typed dicts back from Claude — `with_structured_output()` handles tool-calling under the hood.

## Package layout (post-v0.1 split)

LangChain was monolithic, then split into separate packages to keep installs lean:

- **`langchain-core`** — Runnables, base classes, prompt templates. Stable, minimal deps.
- **`langchain`** — High-level chains, agents, helpers. Imports from core.
- **`langchain-community`** — Third-party integrations contributed by the community.
- **`langchain-anthropic`**, **`langchain-openai`**, etc. — One package per provider.
- **`langgraph`** — Separate library for stateful, graph-based agent orchestration. **This is what this repo uses.** It's not really "LangChain" — it's a sibling library that consumes LangChain's model interfaces.

## LangChain vs LangGraph

- **LangChain** is best for **linear pipelines**: prompt → model → parser → done. LCEL chains, RAG over a vector store, single tool-calling loops.
- **LangGraph** is best for **stateful, branching, looping** workflows: multi-step agents, human-in-the-loop, conditional edges, checkpointing. `graph.py` uses it precisely because the research pipeline loops (`search → synthesis → maybe loop back`) and pauses for human review.

You can — and this repo does — use LangGraph for orchestration while still using LangChain's `ChatAnthropic` + `with_structured_output` inside each node.

## Ecosystem siblings

- **LangSmith** — hosted observability/tracing. Set `LANGCHAIN_TRACING_V2=true` and every Runnable invocation shows up in a UI. Great for debugging chains.
- **LangServe** — wraps a Runnable as a FastAPI endpoint.

## What to be skeptical of

- **Old agents (`AgentExecutor`, `initialize_agent`)** — deprecated in favor of LangGraph. Don't learn them; they're legacy.
- **Memory classes** — also being phased out; modern code passes message history explicitly.
- **Heavy abstractions** — LangChain has earned a reputation for over-wrapping simple things. For a single API call, the raw `anthropic` SDK is often cleaner. LangChain shines when you need provider-swapping, structured output, or composition.

## How it maps to this repo

| This code | LangChain piece |
|---|---|
| `ChatAnthropic(model=...)` in agents | `langchain-anthropic` chat model |
| `.with_structured_output(SearchOutput)` | Core structured-output helper |
| `response.response_metadata["usage"]` | Standard LangChain response metadata shape |
| `StateGraph`, `add_node`, `interrupt()` | **LangGraph**, not LangChain proper |

## TL;DR

> LangChain gives you a standard interface for LLM components (`Runnable`, `with_structured_output`, prompt templates). LangGraph gives you a state machine to orchestrate them. This project uses both — LangGraph for the pipeline shape, LangChain for the per-node Claude calls.

If you only learn three things: **Runnables + LCEL**, **`with_structured_output`**, and **how LangGraph differs from LangChain.**
