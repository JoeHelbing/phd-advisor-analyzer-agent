import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.gemini_url_context import (  # noqa: E402
    GeminiPaperReviewConfig,
    GeminiPaperReviewService,
    GeminiSummaryResult,
)


class FakeResponse:
    def __init__(self, text, metadata):
        self.text = text
        self._metadata = metadata

    def model_dump(self):
        return self._metadata


class FakeModels:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def generate_content(self, *args, **kwargs):
        response = self.responses[self.calls]
        self.calls += 1

        async def _runner():
            return response

        return _runner()


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_summarize_paper_handles_success():
    """Test successful paper summary via service."""
    response_dump = {
        "url_context_metadata": {"url_metadata": [{"url_retrieval_status": "URL_RETRIEVAL_STATUS_SUCCESS"}]},  # noqa: E501
    }
    fake_client = FakeClient([FakeResponse("summary", response_dump)])

    # Create service with test config
    config = GeminiPaperReviewConfig(
        max_attempts=1,
        fallback_bytes=False,
    )
    service = GeminiPaperReviewService(fake_client, config)

    result: GeminiSummaryResult = run(
        service.summarize_paper(
            title="Paper",
            url="https://example.com/paper.pdf",
            interests="interests",
        )
    )

    assert result.text == "summary"
    assert result.status == "URL_RETRIEVAL_STATUS_SUCCESS"
    assert result.strategy == "url_context"
    assert isinstance(result.usage, object)


def test_summarize_paper_uses_fallback(monkeypatch):
    """Test fallback to inline PDF."""
    failures = {
        "url_context_metadata": {"url_metadata": [{"url_retrieval_status": "URL_RETRIEVAL_STATUS_ERROR"}]},  # noqa: E501
    }
    success = {
        "url_context_metadata": {"url_metadata": [{"url_retrieval_status": "URL_RETRIEVAL_STATUS_SUCCESS"}]},  # noqa: E501
    }
    fake_client = FakeClient([FakeResponse("", failures), FakeResponse("from-bytes", success)])

    config = GeminiPaperReviewConfig(
        max_attempts=1,
        fallback_bytes=True,
    )
    service = GeminiPaperReviewService(fake_client, config)

    async def fake_download(_url):
        return b"%PDF-1.4"

    # Monkeypatch the instance method
    service._download_pdf_bytes = fake_download

    result: GeminiSummaryResult = run(
        service.summarize_paper(
            title="Paper",
            url="https://example.com/paper.pdf",
            interests="interests",
        )
    )

    assert result.text == "from-bytes"
    assert result.strategy == "fallback_inline_pdf"
    assert result.error is None
