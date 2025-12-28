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
    ScoreBreakdown,
    ScoreComponent,
)


class TestExtractedLink:
    def test_valid_link(self):
        link = ExtractedLink(
            label="Google Scholar",
            url=HttpUrl("https://scholar.google.com/citations?user=abc123"),
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
            faculty_page_url=HttpUrl("https://profiles.stanford.edu/jane-doe"),
            name="Jane Doe",
            institution="Stanford University",
            pages_crawled=[HttpUrl("https://profiles.stanford.edu/jane-doe")],
        )
        assert extraction.name == "Jane Doe"
        assert extraction.department is None
        assert extraction.google_scholar_url is None
        assert extraction.other_links == []

    def test_full_extraction(self):
        extraction = FacultyPageExtraction(
            faculty_page_url=HttpUrl("https://profiles.stanford.edu/jane-doe"),
            name="Jane Doe",
            institution="Stanford University",
            department="Computer Science",
            email="jane@stanford.edu",
            bio_summary="Expert in NLP",
            research_areas=["NLP", "ML"],
            personal_homepage=HttpUrl("https://janedoe.github.io"),
            google_scholar_url=HttpUrl("https://scholar.google.com/citations?user=abc"),
            semantic_scholar_url=HttpUrl("https://semanticscholar.org/author/123"),
            dblp_url=HttpUrl("https://dblp.org/pid/123/456"),
            orcid_url=HttpUrl("https://orcid.org/0000-0001-2345-6789"),
            arxiv_author_url=HttpUrl("https://arxiv.org/a/doe_j_1"),
            other_links=[
                ExtractedLink(
                    label="NLP Lab",
                    url=HttpUrl("https://nlp.stanford.edu"),
                    category="lab",
                    source="faculty_profile",
                )
            ],
            pages_crawled=[
                HttpUrl("https://profiles.stanford.edu/jane-doe"),
                HttpUrl("https://janedoe.github.io"),
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
        faculty_page_url=HttpUrl("https://example.edu/jane-doe"),
        name="Jane Doe",
        institution="Stanford University",
        pages_crawled=[HttpUrl("https://example.edu/jane-doe")],
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
    breakdown = ScoreBreakdown(
        research_alignment=ScoreComponent(
            score=22, max_score=25, explanation="Strong NLP alignment with SOP."
        ),
        methods_overlap=ScoreComponent(
            score=13, max_score=15, explanation="Core NLP methods match."
        ),
        publication_quality=ScoreComponent(
            score=14, max_score=15, explanation="Top NLP venues."
        ),
        recent_activity=ScoreComponent(
            score=9, max_score=10, explanation="Active in last 2 years."
        ),
        funding=ScoreComponent(
            score=8, max_score=10, explanation="Active grants."
        ),
        recruiting_status=ScoreComponent(
            score=13, max_score=15, explanation="Recruiting with high confidence."
        ),
        advising_and_lab=ScoreComponent(
            score=4, max_score=5, explanation="Good lab signals."
        ),
        program_fit=ScoreComponent(
            score=5, max_score=5, explanation="No constraints."
        ),
        red_flags=ScoreComponent(
            score=-3, max_score=0, explanation="Moderate concern about lab size."
        ),
    )
    # Total: 22+13+14+9+8+13+4+5-3 = 85
    synthesis = ResearchSynthesis(
        score=85.0,
        score_breakdown=breakdown,
        verdict="Good fit for NLP research.",
        red_flags=None,
        research_fit="Strong alignment with NLP interests.",
        highlighted_papers=None,
        recruiting=recruiting,
        advising_and_lab=None,
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


class TestScoreComponent:
    def test_valid_score_component(self):
        """Test ScoreComponent field validation."""
        component = ScoreComponent(
            score=25.0,
            max_score=35.0,
            explanation="Strong alignment with SOP research topics and methodology.",
        )
        assert component.score == 25.0
        assert component.max_score == 35.0
        assert len(component.explanation) >= 10

    def test_explanation_too_short_rejected(self):
        """Test explanation length constraints."""
        with pytest.raises(ValidationError):
            ScoreComponent(score=25.0, max_score=35.0, explanation="Too short")

    def test_explanation_too_long_rejected(self):
        """Test explanation maximum length."""
        with pytest.raises(ValidationError):
            ScoreComponent(
                score=25.0,
                max_score=35.0,
                explanation="x" * 301,  # > 300 chars
            )


class TestScoreBreakdown:
    def test_total_score_calculation(self):
        """Test ScoreBreakdown total_score property."""
        breakdown = ScoreBreakdown(
            research_alignment=ScoreComponent(
                score=23, max_score=25, explanation="Strong topic alignment with SOP research interests."  # noqa: E501
            ),
            methods_overlap=ScoreComponent(
                score=13, max_score=15, explanation="Core technical methods match perfectly."
            ),
            publication_quality=ScoreComponent(
                score=14, max_score=15, explanation="Top venues with strong citations."
            ),
            recent_activity=ScoreComponent(
                score=9, max_score=10, explanation="Very active in last 2 years."
            ),
            funding=ScoreComponent(
                score=9, max_score=10, explanation="NSF CAREER and Sloan Fellow."
            ),
            recruiting_status=ScoreComponent(
                score=13, max_score=15, explanation="Recruiting with high confidence."
            ),
            advising_and_lab=ScoreComponent(
                score=5, max_score=5, explanation="Excellent lab culture signals."
            ),
            program_fit=ScoreComponent(
                score=5, max_score=5, explanation="Not applicable - no constraints."
            ),
            red_flags=ScoreComponent(
                score=-2, max_score=0, explanation="Minor industry consulting concern."
            ),
        )
        assert breakdown.total_score == 89.0
        assert breakdown.validate_total(89.0, tolerance=0.5)
        assert not breakdown.validate_total(85.0, tolerance=0.5)


class TestResearchSynthesisScoring:
    def test_score_consistency_validation_passes(self):
        """Test ResearchSynthesis accepts matching score and breakdown."""
        plan = ResearchPlan(
            objectives=["obj"],
            prioritized_sources=["source"],
            information_targets=["info"],
        )
        recruiting = RecruitingInsight(
            source_url="https://example.edu/recruiting",
            verbatim_text="I am recruiting.",
            is_recruiting=True,
            confidence=0.9,
        )
        breakdown = ScoreBreakdown(
            research_alignment=ScoreComponent(
                score=20, max_score=25, explanation="Good alignment with SOP topics."
            ),
            methods_overlap=ScoreComponent(
                score=12, max_score=15, explanation="Strong methods overlap."
            ),
            publication_quality=ScoreComponent(
                score=12, max_score=15, explanation="Strong venues and citations."
            ),
            recent_activity=ScoreComponent(
                score=8, max_score=10, explanation="Active publication record."
            ),
            funding=ScoreComponent(
                score=7, max_score=10, explanation="Active grants visible."
            ),
            recruiting_status=ScoreComponent(
                score=12, max_score=15, explanation="Recruiting with confidence."
            ),
            advising_and_lab=ScoreComponent(
                score=4, max_score=5, explanation="Good lab signals."
            ),
            program_fit=ScoreComponent(
                score=5, max_score=5, explanation="No constraints."
            ),
            red_flags=ScoreComponent(
                score=-2, max_score=0, explanation="Minor concern."
            ),
        )
        # Total: 20+12+12+8+7+12+4+5-2 = 78
        synthesis = ResearchSynthesis(
            score=78.0,
            score_breakdown=breakdown,
            verdict="Good fit.",
            red_flags=None,
            research_fit="Alignment analysis.",
            highlighted_papers=None,
            recruiting=recruiting,
            advising_and_lab=None,
            activity="Active.",
            plan=plan,
        )
        assert synthesis.score == 78.0
        assert synthesis.score_breakdown.total_score == 78.0

    def test_score_consistency_validation_fails(self):
        """Test ResearchSynthesis rejects mismatched score and breakdown."""
        plan = ResearchPlan(
            objectives=["obj"],
            prioritized_sources=["source"],
            information_targets=["info"],
        )
        recruiting = RecruitingInsight(
            source_url="https://example.edu/recruiting",
            verbatim_text="I am recruiting.",
            is_recruiting=True,
            confidence=0.9,
        )
        breakdown = ScoreBreakdown(
            research_alignment=ScoreComponent(
                score=20, max_score=25, explanation="Good alignment."
            ),
            methods_overlap=ScoreComponent(
                score=12, max_score=15, explanation="Strong methods."
            ),
            publication_quality=ScoreComponent(
                score=12, max_score=15, explanation="Strong venues."
            ),
            recent_activity=ScoreComponent(
                score=8, max_score=10, explanation="Active record."
            ),
            funding=ScoreComponent(
                score=7, max_score=10, explanation="Active grants."
            ),
            recruiting_status=ScoreComponent(
                score=12, max_score=15, explanation="Recruiting."
            ),
            advising_and_lab=ScoreComponent(
                score=4, max_score=5, explanation="Good lab signals found."
            ),
            program_fit=ScoreComponent(
                score=5, max_score=5, explanation="No constraints."
            ),
            red_flags=ScoreComponent(
                score=-2, max_score=0, explanation="Minor concern."
            ),
        )
        # Breakdown totals to 78, but we claim score is 85
        with pytest.raises(ValidationError, match="does not match breakdown total"):
            ResearchSynthesis(
                score=85.0,  # Mismatch!
                score_breakdown=breakdown,
                verdict="Good fit.",
                red_flags=None,
                research_fit="Alignment.",
                highlighted_papers=None,
                recruiting=recruiting,
                advising_and_lab=None,
                activity="Active.",
                plan=plan,
            )
