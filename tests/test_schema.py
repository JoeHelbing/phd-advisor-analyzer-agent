"""Tests for schema models."""

import sys
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.schema import (
    ExtractedLink,
    FacultyPageExtraction,
    PaperFailure,
    PaperMetadata,
    PaperReview,
    PaperSelection,
    RecruitingInsight,
    ResearchDeps,
    ResearchPlan,
    ResearchReport,
    ResearchSynthesis,
)


class TestExtractedLink:
    def test_valid_link(self):
        link = ExtractedLink(
            label="Google Scholar",
            url="https://scholar.google.com/citations?user=abc123",
            category="papers",
            source="faculty_profile",
        )
        assert link.label == "Google Scholar"
        assert str(link.url) == "https://scholar.google.com/citations?user=abc123"
        assert link.category == "papers"
        assert link.source == "faculty_profile"

    def test_invalid_url_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedLink(
                label="Bad Link",
                url="not-a-url",
                category="other",
                source="faculty_profile",
            )


class TestFacultyPageExtraction:
    def test_minimal_extraction(self):
        extraction = FacultyPageExtraction(
            faculty_page_url="https://profiles.stanford.edu/jane-doe",
            name="Jane Doe",
            institution="Stanford University",
            pages_crawled=["https://profiles.stanford.edu/jane-doe"],
        )
        assert extraction.name == "Jane Doe"
        assert extraction.department is None
        assert extraction.google_scholar_url is None
        assert extraction.other_links == []

    def test_full_extraction(self):
        extraction = FacultyPageExtraction(
            faculty_page_url="https://profiles.stanford.edu/jane-doe",
            name="Jane Doe",
            institution="Stanford University",
            department="Computer Science",
            email="jane@stanford.edu",
            bio_summary="Expert in NLP",
            research_areas=["NLP", "ML"],
            personal_homepage="https://janedoe.github.io",
            google_scholar_url="https://scholar.google.com/citations?user=abc",
            semantic_scholar_url="https://semanticscholar.org/author/123",
            dblp_url="https://dblp.org/pid/123/456",
            orcid_url="https://orcid.org/0000-0001-2345-6789",
            arxiv_author_url="https://arxiv.org/a/doe_j_1",
            other_links=[
                ExtractedLink(
                    label="NLP Lab",
                    url="https://nlp.stanford.edu",
                    category="lab",
                    source="faculty_profile",
                )
            ],
            pages_crawled=[
                "https://profiles.stanford.edu/jane-doe",
                "https://janedoe.github.io",
            ],
        )
        assert extraction.department == "Computer Science"
        assert len(extraction.other_links) == 1
        assert len(extraction.pages_crawled) == 2


def test_paper_selection_includes_failures():
    review = PaperReview(
        metadata=PaperMetadata(
            title="Example",
            source="Scholar",
            url="https://example.com/paper.pdf",
            authors="A",
            venue="Conf",
            published_at="2024",
        ),
        confirmed_author=True,
        affiliation_match=True,
        abstract="Abstract text",
        summary_for_user="Summary",
        url_context_status="URL_RETRIEVAL_STATUS_SUCCESS",
        url_context_strategy="url_context",
        url_context_metadata={"attempts": 1},
    )
    failure = PaperFailure(
        index=2,
        title="Missing PDF",
        url="https://example.com/missing.pdf",
        status="URL_RETRIEVAL_STATUS_ERROR",
        reason="403 Forbidden",
    )

    selection = PaperSelection(
        selected=[review],
        selected_count=1,
        skipped_no_pdf=0,
        failures=[failure],
    )

    assert selection.failures[0].reason == "403 Forbidden"


def test_research_report_accepts_failures():
    target = FacultyPageExtraction(
        faculty_page_url="https://example.edu/jane-doe",
        name="Jane Doe",
        institution="Stanford University",
        pages_crawled=["https://example.edu/jane-doe"],
    )
    plan = ResearchPlan(
        objectives=["obj"],
        prioritized_sources=["source"],
        information_targets=["advising style"],
    )
    review = PaperReview(
        metadata=PaperMetadata(
            title="Example",
            source="gemini_url_context",
            url="https://example.com/paper.pdf",
            authors="",
        ),
        confirmed_author=False,
        affiliation_match=False,
        abstract="",
        summary_for_user="Summary",
    )
    failure = PaperFailure(
        index=1,
        title="Missing PDF",
        url="https://example.com/missing.pdf",
        status="URL_RETRIEVAL_STATUS_ERROR",
        reason="403",
    )
    recruiting = RecruitingInsight(
        source_url="https://example.edu/recruiting",
        verbatim_text="I am recruiting PhD students.",
        is_recruiting=True,
        confidence=0.9,
    )
    synthesis = ResearchSynthesis(
        score=85.0,
        verdict="Good fit for NLP research.",
        research_fit="Strong alignment with NLP interests.",
        recruiting=recruiting,
        activity="Active publication record.",
        plan=plan,
    )
    report = ResearchReport(
        professor=target,
        synthesis=synthesis,
        paper_reviews=[review],
        paper_failures=[failure],
        created_at=datetime.utcnow(),
    )

    assert len(report.paper_failures) == 1
    assert report.paper_failures[0].reason == "403"


def test_research_deps_accepts_sop_text():
    from unittest.mock import MagicMock
    import httpx
    from crawl4ai import AsyncWebCrawler

    deps = ResearchDeps(
        http_client=MagicMock(spec=httpx.AsyncClient),
        crawler=MagicMock(spec=AsyncWebCrawler),
        google_api_key="key",
        google_cse_id="cse",
        sop_text="interests",
    )
    assert deps.sop_text == "interests"
