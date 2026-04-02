"""
tools/web.py — Web search and page fetching.

Supports Tavily for live search and a mock fallback for dev mode.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from state import RunMode, Source


@dataclass
class RawSearchHit:
    """Normalized search hit from any provider."""

    url: str
    title: str
    snippet: str
    score: float


def web_search(
    query: str,
    *,
    mode: RunMode,
    tavily_api_key: str = "",
    max_results: int = 5,
) -> tuple[list[RawSearchHit], str]:
    """Search the web. Returns (hits, source_type).

    In dev mode without a Tavily key, returns mock results.
    In eval mode, raises if credentials are missing.
    """
    has_key = bool(tavily_api_key)

    if mode == RunMode.EVAL and not has_key:
        raise RuntimeError("eval mode requires a real search provider; TAVILY_API_KEY is missing")

    if has_key:
        return _tavily_search(query, tavily_api_key, max_results), "live"

    if mode == RunMode.DEV:
        return _mock_search(query), "mock"

    raise RuntimeError(f"No search credentials available for mode={mode.value}")


def _tavily_search(query: str, api_key: str, max_results: int) -> list[RawSearchHit]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=max_results)
    return [
        RawSearchHit(
            url=r["url"],
            title=r.get("title", ""),
            snippet=r.get("content", ""),
            score=r.get("score", 0.5),
        )
        for r in response.get("results", [])
    ]


def _mock_search(query: str) -> list[RawSearchHit]:
    return [
        RawSearchHit(
            url="https://example.com/mock-1",
            title=f"Mock result for: {query}",
            snippet=f"This is a mock search result about {query}. Used for local dev only.",
            score=0.85,
        ),
        RawSearchHit(
            url="https://example.com/mock-2",
            title=f"Mock secondary result for: {query}",
            snippet=f"A second mock result providing additional context on {query}.",
            score=0.72,
        ),
    ]


def hits_to_sources(hits: list[RawSearchHit], source_type: str) -> list[Source]:
    """Convert raw search hits to Source models."""
    return [
        Source(
            url=h.url,
            title=h.title,
            snippet=h.snippet,
            relevance_score=h.score,
            source_type=source_type,
        )
        for h in hits
    ]


def fetch_page(url: str, *, timeout: float = 10.0) -> str:
    """Fetch a page's text content. Returns empty string on failure."""
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text[:10_000]  # cap to avoid blowing context
    except (httpx.HTTPError, httpx.InvalidURL):
        return ""
