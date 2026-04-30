# Research Console — Web UI Implementation Plan

Design bundle: `/tmp/design_fetch/research-assistant-with-human-in-the-loop/` (fetched from Claude Design, 2026-04-19).

## Scope

Add a browser-based "Research Console" cockpit on top of the existing LangGraph pipeline (`graph.py`, `state.py`, agents). Paper-and-ink aesthetic, Instrument Serif + Inter + JetBrains Mono, vermillion accent reserved for the HITL interrupt moment.

Target stack (from handoff README):
- Frontend: **Vite + React + TypeScript**, plain CSS (tokens file), no Tailwind.
- Backend bridge: `server.py` FastAPI wrapping `graph.py` with SSE.
- Location: new `web/` folder at repo root, new `server.py` alongside existing `graph.py`. Do not modify `state.py`, `graph.py`, or agents.

## Starter slice (this pass)

Phase 1 only — frontend scaffold + static layout against fixture data. No backend yet, no SSE, no real pipeline wiring. The goal: a runnable `npm run dev` that renders the full cockpit layout with realistic mock data so the design is verifiable end-to-end before wiring reality.

### In-scope for starter slice

1. **Scaffold** `web/` — Vite + React + TS, package.json, vite.config, index.html, main.tsx.
2. **Design tokens** — `styles/tokens.css` (paper/ink palette, semantic colors, terminal colors) + `styles/fonts.css` (Google Fonts import) + `styles/global.css` (reset + paper grain).
3. **Type system + fixtures** — port `data.jsx` to `api/fixtures.ts` + `api/types.ts` matching `state.py` shape.
4. **Primitives** — `components/primitives.tsx`: `Dot`, `Pill`, `Label`, `Corner`, `Rule`, `ScoreDial`.
5. **TopBar** — caps chip, phase pill, topic h1 in serif, meta row, Reset/New Topic buttons.
6. **PipelineGraph** — 900×220 SVG, 4 nodes, animated active edge dot, dashed interrupt overlay on `human_review`, loop-back arc, reject exit, metrics strip.
7. **ReviewPanel (paused state)** — paper-tape warning header, live clock, four decision cards (A/Q/E/R), detail area for each decision (queries rows + gap chips, edit textarea, reject reason).
8. **Sidebar** — runs list with ScoreDial + status pill + cost, cost summary block.
9. **App shell** — tab bar (Human Review / Draft & Sources / Evaluation / Log), static state machine fixed at `paused_interrupt`.

### Explicitly deferred (future passes)

- **Tab 2 (Draft & Sources)**: citation hover-sync — placeholder only.
- **Tab 3 (Evaluation)**: meter bars — placeholder only.
- **Tab 4 (Log)**: terminal pane — placeholder only.
- **InspectorRow** (state table + log pane below tabs) — placeholder only.
- **Keyboard shortcuts** (A/Q/E/R/Enter/Esc) — skip; click-only.
- **Tweaks panel** — skip (v2).
- **`usePipelineStream` hook** + SSE — skip; static fixtures only.
- **`server.py`** FastAPI — skip entirely.
- **Real run persistence** (localStorage) — skip.

## Tasks (tracked in TaskList)

1. Scaffold `web/` with Vite + React + TS + npm scripts
2. Write design tokens, fonts, global CSS
3. Port fixtures + TypeScript types
4. Implement primitives (Dot/Pill/Label/Corner/Rule/ScoreDial)
5. Implement TopBar
6. Implement PipelineGraph SVG with animations
7. Implement Sidebar (runs list + cost summary)
8. Implement ReviewPanel with four decision cards + detail areas
9. Wire App shell (tab bar + layout grid) with placeholders for deferred tabs
10. Verify `npm install && npm run dev` runs cleanly

## Open questions / deferred decisions

- FastAPI shape and SSE event schema — locked by handoff README when we build phase 2.
- Whether to colocate `server.py` or put it under `api/` — TBD at phase 2.
- Whether to regenerate TS types from Pydantic via `datamodel-code-generator` or hand-sync — hand-sync for now (simpler, smaller surface).
