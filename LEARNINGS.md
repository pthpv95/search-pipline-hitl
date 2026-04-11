# What I Learned Building a Research Pipeline

Notes distilled from the build session on 2026-04-09.

---

## What is a Synthesis Report?

A synthesis report is **not a summary**. The difference:

- **Summary**: "Source A says X, Source B says Y"
- **Synthesis**: "X and Y together mean Z, and here's what's missing"

It connects dots across sources, identifies patterns, contradictions, and gaps. It compares options on the **same dimensions** and arrives at recommendations with cited evidence.

A good synthesis report answers three questions:
1. What are my options?
2. What are the tradeoffs?
3. What should I do given my constraints?

---

## Why Build This as an Agentic Workflow?

### The problem it solves
Decision-makers don't have time to read 10 articles. Analysts spend 4-8 hours manually googling, reading, comparing, and writing. This pipeline does it in ~2.5 minutes for ~$0.20.

### Who it serves
- **Analysts/researchers** — automates the mechanical work (search, extract, structure, cite)
- **Decision-makers** — PMs, leads, VPs who need research before the meeting, not after
- **Consulting/advisory teams** — firms that sell research as a service
- **Product teams** — competitive analysis at scale
- **Due diligence workflows** — VC, M&A, procurement

### Core value proposition

| Dimension     | Manual                  | This pipeline          |
|---------------|-------------------------|------------------------|
| Speed         | Half a day              | ~2.5 minutes           |
| Cost          | Hours of analyst salary | ~$0.20/report          |
| Consistency   | Varies by person        | Same structure every time |
| Auditability  | Usually none            | Every claim cited, every run scored |

### What makes the HITL design matter
- **Fully automated** research is cheap but untrustworthy
- **Fully manual** is trustworthy but expensive
- **Human-in-the-loop** is the sweet spot: agent does heavy lifting, human approves/edits/redirects before the final report ships

---

## The Five Eval Dimensions

Each run is scored on five dimensions (0.0-1.0):

### 1. Citation Integrity (avg: 0.94)
Does every `[N]` marker in the report map to an actual source?

- A broken citation is worse than no citation — it gives false confidence
- Failures usually come from the LLM hallucinating a citation number out of range
- **Fix**: tighter prompting in the report agent

### 2. Source Validity (avg: 1.00)
Does every source URL have a valid scheme and hostname?

- Structural check, not a liveness check (won't catch 404s)
- The minimum bar for a research deliverable
- Tavily returns real URLs so this is basically free right now

### 3. Topical Coverage (avg: 1.00)
Do the topic's keywords appear in the report body?

- Penalty: if pipeline ran extra loops but didn't record limitations, score is capped at 0.85
- **Honest weakness**: keyword matching, not semantic understanding. A report could mention every keyword while saying nothing meaningful.

### 4. Unsupported Claim Rate (avg: 0.71 -- the weak spot)
What fraction of body paragraphs contain at least one citation?

- **Most important dimension for trust**
- An uncited paragraph = an unsupported claim the reader can't verify
- Some runs have ~45% of paragraphs uncited
- **Root cause**: LLMs write confident analytical prose without anchoring to sources
- **Fix**: report agent prompt needs "every factual paragraph MUST include at least one citation"

### 5. Loop Discipline (avg: 1.00)
Did the pipeline stay within the loop cap? If it looped, did it justify the extra work?

- Each loop costs tokens, time, and money
- Pipeline correctly identifies gaps on first pass, does targeted second search, documents what remains unresolved

### The Overall Score

Simple average of all five. Our 10-run average: **0.93**

Honest breakdown of what's carrying vs dragging:

| Dimension            | Avg  | Reality                              |
|----------------------|------|--------------------------------------|
| Source validity       | 1.00 | Free win (Tavily gives real URLs)    |
| Topical coverage     | 1.00 | Free win (keyword matching is easy)  |
| Loop discipline      | 1.00 | Well-engineered pipeline             |
| Citation integrity   | 0.94 | Genuinely strong                     |
| Unsupported claims   | 0.71 | **The real problem**                 |

The 0.93 looks great but masks that ~30% of paragraphs make claims without citing evidence.

---

## What the Eval Framework Gives You

Things most AI tools can't answer:

- **Regression detection**: Run same topics after a prompt change. Did scores go up or down?
- **Per-dimension diagnostics**: Know *which* dimension dropped, pointing directly at which agent to fix
- **Cost-quality tradeoff**: Every run tracks tokens and cost alongside scores. Can answer "if I drop to 1 loop, how much quality do I lose?"
- **Cross-topic comparison**: Some topics consistently score lower on certain dimensions — signals where human review matters most

---

## The Honest Limitation

The pipeline automates **mechanical work** (searching, extracting, structuring, citing). It cannot replace analyst judgment:

- Is this source credible or just SEO spam?
- Does this conclusion logically follow from the evidence?
- What's missing that the search didn't find?
- Is this framing useful for the reader?

That's what the human-in-the-loop step is really for — not a rubber stamp, but where **domain knowledge enters the system**.

The pipeline makes a decent analyst much faster. It doesn't make a non-analyst into an analyst. But building it teaches you what analysts actually do.

---

## Run Results (2026-04-09)

10 eval runs across 5 topics (2 batches):

| Topic                            | Best Overall | Tokens  | Cost    |
|----------------------------------|-------------|---------|---------|
| LangGraph vs CrewAI vs AutoGen   | 0.98        | 43,432  | ~$0.24  |
| LLM impact on developer productivity | 0.94   | 28,299  | ~$0.19  |
| Prompt engineering for structured output | 0.94 | 34,098 | ~$0.21 |
| AI agent memory architectures    | 0.95        | 31,482  | ~$0.20  |
| Multi-agent AI systems in 2025   | 0.91        | 38,408  | ~$0.24  |

**Totals**: 340,858 tokens, ~$2.12, avg overall 0.93

---

## Next Steps to Improve

1. **Report agent prompt** — force citation in every substantive paragraph (biggest ROI)
2. **Synthesis agent** — tighten structured output prompt to avoid Pydantic retry on first attempt
3. **Source credibility** — add a scoring layer that distinguishes primary research from marketing blogs
4. **Internal knowledge** — plug in proprietary data sources beyond web search for niche topics
5. **Suppress deserialization warnings** — add `allowed_msgpack_modules` to checkpointer config
