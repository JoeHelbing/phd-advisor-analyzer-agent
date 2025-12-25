"""Tests for agent definitions."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.usage import RequestUsage

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src import agents, tools
from src.agents import faculty_extractor_agent
from src.schema import (
    FacultyPageExtraction,
    PaperSelection,
)
from src.gemini_url_context import GeminiSummaryResult


def test_faculty_extractor_agent_exists():
    assert faculty_extractor_agent is not None


def test_faculty_extractor_agent_output_type():
    # Check the agent is configured with correct output type
    assert faculty_extractor_agent._output_type is FacultyPageExtraction


@pytest.mark.skip(reason="downselect_papers function does not exist as a standalone tool")
def test_downselect_papers_includes_scholar_url(monkeypatch):
    async def fake_run(prompt, deps=None, usage=None):
        fake_run.prompt = prompt
        return SimpleNamespace(
            output=PaperSelection(selected=[], selected_count=0, skipped_no_pdf=0)
        )

    monkeypatch.setattr(agents, "downselector_agent", SimpleNamespace(run=fake_run))

    ctx = SimpleNamespace(deps=SimpleNamespace(sop_text="My SOP text"), usage=None)
    professor = FacultyPageExtraction(
        faculty_page_url="https://example.edu/jane-doe",
        name="Jane Doe",
        institution="Stanford University",
        google_scholar_url="https://scholar.google.com/citations?user=abc",
        pages_crawled=["https://example.edu/jane-doe"],
    )

    result = asyncio.run(tools.downselect_papers(ctx, professor))
    assert result.selected_count == 0
    assert "Google Scholar:" in fake_run.prompt
    assert "https://scholar.google.com/citations?user=abc" in fake_run.prompt
    assert "My SOP text" in fake_run.prompt


def test_review_paper_pdf_uses_gemini_service():
    """Test that review_paper_pdf uses GeminiPaperReviewService."""
    fake_result = GeminiSummaryResult(
        text="summary",
        status="URL_RETRIEVAL_STATUS_SUCCESS",
        strategy="url_context",
        metadata={"attempts": 1},
        usage=RequestUsage(),
        error=None,
    )

    captured = {}

    class FakeService:
        async def summarize_paper(self, **kwargs):
            captured["kwargs"] = kwargs
            return fake_result

    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            sop_text="interests",
            gemini_service=FakeService(),
            debug_skip_reviews=False,
        ),
        usage=None,
    )

    review = asyncio.run(
        tools.review_paper_pdf(
            ctx,
            "https://example.com/paper.pdf",
            "Example Paper",
        )
    )

    assert review.summary_for_user == "summary"
    assert review.url_context_status == "URL_RETRIEVAL_STATUS_SUCCESS"
    assert captured["kwargs"]["interests"] == "interests"
    assert captured["kwargs"]["title"] == "Example Paper"
    assert captured["kwargs"]["url"] == "https://example.com/paper.pdf"


def test_review_paper_pdf_raises_when_gemini_service_fails():
    """Test that review_paper_pdf raises RuntimeError when service returns error."""
    fake_result = GeminiSummaryResult(
        text="",
        status="URL_RETRIEVAL_STATUS_ERROR",
        strategy="url_context",
        metadata={},
        usage=RequestUsage(),
        error="403 Forbidden",
    )

    class FakeService:
        async def summarize_paper(self, **_kwargs):
            return fake_result

    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            sop_text="interests",
            gemini_service=FakeService(),
            debug_skip_reviews=False,
        ),
        usage=None,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            tools.review_paper_pdf(
                ctx,
                "https://example.com/paper.pdf",
                "Example Paper",
            )
        )
