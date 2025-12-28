import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import src.tools as tools  # noqa: E402
from src.scholar import fetch_scholar_papers  # noqa: E402
from src.tools import fetch_url  # noqa: E402


class DummyCrawler:
    def __init__(self, result):
        self._result = result

    async def arun(self, url, config=None):
        return self._result


def test_fetch_url_returns_raw_markdown():
    markdown = SimpleNamespace(raw_markdown="raw content", fit_markdown="fit content")
    result = SimpleNamespace(success=True, error_message=None, markdown=markdown)
    ctx = SimpleNamespace(deps=SimpleNamespace(crawler=DummyCrawler(result), fetch_cache={}))

    output = asyncio.run(fetch_url(ctx, "https://example.com"))

    assert output.success is True
    assert output.content == "raw content"


def test_fetch_url_caches_results():
    """Test that fetch_url caches results and reuses them on subsequent calls."""
    markdown = SimpleNamespace(raw_markdown="cached content", fit_markdown="fit content")
    result = SimpleNamespace(success=True, error_message=None, markdown=markdown)

    # Create a crawler that tracks how many times it was called
    call_count = {"count": 0}

    class CountingCrawler:
        async def arun(self, url, config=None):
            call_count["count"] += 1
            return result

    ctx = SimpleNamespace(deps=SimpleNamespace(crawler=CountingCrawler(), fetch_cache={}))

    # First call should fetch from crawler
    output1 = asyncio.run(fetch_url(ctx, "https://example.com"))
    assert output1.success is True
    assert output1.content == "cached content"
    assert call_count["count"] == 1

    # Second call should use cache, not crawler
    output2 = asyncio.run(fetch_url(ctx, "https://example.com"))
    assert output2.success is True
    assert output2.content == "cached content"
    assert call_count["count"] == 1  # Should still be 1, not 2

    # Verify cache has the entry
    assert "https://example.com" in ctx.deps.fetch_cache
    assert ctx.deps.fetch_cache["https://example.com"].character_count == len("cached content")


class FakeHttpClient:
    def __init__(self, responses: dict[str, list[httpx.Response]]):
        self._responses = {url: list(resps) for url, resps in responses.items()}

    async def get(self, url: str) -> httpx.Response:
        queue = self._responses.get(url)
        if not queue:
            raise AssertionError(f"No response queued for {url}")
        return queue.pop(0)


class FakeClock:
    def __init__(self):
        self.current = 0.0
        self.sleeps: list[float] = []

    def perf_counter(self) -> float:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if seconds < 0:
            return
        self.current += seconds


def _make_ctx(http_client):
    deps = SimpleNamespace(
        crawler=DummyCrawler(SimpleNamespace(success=True, error_message=None, markdown=None)),
        http_client=http_client,
        google_api_key="test",
        google_cse_id="test",
        fetch_cache={},
    )
    return SimpleNamespace(deps=deps)


def _response(url: str, *, status: int = 200, text: str = "", headers: dict | None = None):
    req = httpx.Request("GET", url)
    return httpx.Response(status, request=req, text=text, headers=headers or {})


@pytest.mark.asyncio
async def test_fetch_scholar_papers_enforces_minimum_duration(monkeypatch):
    import src.scholar as scholar
    import src.schema as schema
    profile_url = "https://scholar.google.com/citations?user=test"
    profile_url_with_params = "https://scholar.google.com/citations?user=test&hl=en&sortby=pubdate&cstart=0&pagesize=1"
    citation_url = (
        "https://scholar.google.com/citations?view_op=view_citation&hl=en"
        "&user=test&citation_for_view=test:1"
    )
    profile_html = """
    <tr class="gsc_a_tr">
        <a class="gsc_a_at" href="/citations?view_op=view_citation&hl=en&user=test&citation_for_view=test:1">Paper</a>
        <div class="gs_gray">Author</div>
        <div class="gs_gray">Venue</div>
        <td class="gsc_a_y"><span>2024</span></td>
    </tr>
    """  # noqa: E501
    citation_html = """
    <div class="gsc_oci_field">Description</div>
    <div>Interesting work</div>
    <a href="https://example.com/paper.pdf"><span class="gsc_vcd_title_ggt">PDF</span></a>
    """
    responses = {
        profile_url_with_params: [_response(profile_url_with_params, text=profile_html)],
        citation_url: [_response(citation_url, text=citation_html)],
    }
    client = FakeHttpClient(responses)
    ctx = _make_ctx(client)

    clock = FakeClock()
    monkeypatch.setattr(scholar.asyncio, "sleep", clock.sleep)
    monkeypatch.setattr(schema.time, "perf_counter", clock.perf_counter)

    result = await fetch_scholar_papers(
        ctx.deps,
        profile_url,
        max_papers=1,
        years_back=5,
    )

    assert len(result.papers) == 1
    assert clock.current >= 60.0


@pytest.mark.asyncio
async def test_fetch_scholar_papers_handles_rate_limits(monkeypatch, caplog):
    import src.scholar as scholar
    import src.schema as schema
    profile_url = "https://scholar.google.com/citations?user=test"
    profile_url_with_params = "https://scholar.google.com/citations?user=test&hl=en&sortby=pubdate&cstart=0&pagesize=1"
    throttled_responses = [
        _response(
            profile_url_with_params,
            status=429,
            text="",
            headers={"Retry-After": "1"},
        )
        for _ in range(4)
    ]
    responses = {profile_url_with_params: throttled_responses}
    client = FakeHttpClient(responses)
    ctx = _make_ctx(client)

    clock = FakeClock()
    monkeypatch.setattr(scholar.asyncio, "sleep", clock.sleep)
    monkeypatch.setattr(schema.time, "perf_counter", clock.perf_counter)

    caplog.set_level(logging.WARNING, logger="src.scholar")

    result = await fetch_scholar_papers(
        ctx.deps,
        profile_url,
        max_papers=1,
        years_back=5,
    )

    assert result.papers == []
    assert "throttled" in caplog.text or "429" in caplog.text
    assert clock.current >= 60.0
