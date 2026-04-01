from state import (
    Finding,
    GraphStatus,
    ResearchState,
    RunMode,
    SearchResult,
    Source,
    SynthesisDraft,
    TokenUsage,
)


def test_default_state_is_valid():
    state = ResearchState(topic="anything")
    assert state.mode == RunMode.DEV
    assert state.status == GraphStatus.INITIALIZING
    assert state.loop_count == 0
    assert state.errors == []
    assert state.search_results == []


def test_all_findings_flattens_across_rounds():
    finding_one = Finding(content="a", source_url="http://a.com")
    finding_two = Finding(content="b", source_url="http://b.com")
    round_one = SearchResult(findings=[finding_one])
    round_two = SearchResult(findings=[finding_two])
    state = ResearchState(topic="topic", search_results=[round_one, round_two])
    assert len(state.all_findings) == 2


def test_all_sources_deduplicates_by_url():
    shared_source = Source(url="http://same.com", title="Same", snippet="...")
    round_one = SearchResult(sources=[shared_source])
    round_two = SearchResult(sources=[shared_source])
    state = ResearchState(topic="topic", search_results=[round_one, round_two])
    assert len(state.all_sources) == 1


def test_should_search_again_respects_loop_cap_and_gaps():
    draft = SynthesisDraft(
        draft="draft",
        remaining_gaps=["gap"],
        needs_more_search=True,
    )
    capped_state = ResearchState(
        topic="topic",
        synthesis_draft=draft,
        loop_count=2,
        max_loops=2,
    )
    open_state = ResearchState(
        topic="topic",
        synthesis_draft=draft,
        loop_count=1,
        max_loops=2,
    )

    assert capped_state.should_search_again is False
    assert open_state.should_search_again is True


def test_with_error_returns_failed_copy():
    state = ResearchState(topic="topic")
    failed = state.with_error("boom")
    assert failed.status == GraphStatus.FAILED
    assert failed.errors == ["boom"]
    assert state.status == GraphStatus.INITIALIZING


def test_token_usage_total():
    usage = TokenUsage(search_agent=500, synthesis_agent=300, report_agent=200)
    assert usage.total == 1000
