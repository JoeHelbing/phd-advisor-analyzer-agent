"""Integration test for the research-url CLI flow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from crawl4ai import AsyncWebCrawler as BaseCrawler
from pydantic import HttpUrl
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src import main as cli_main
from src.schema import (
    ExtractedLink,
    FacultyPageExtraction,
    RecruitingInsight,
    ResearchPlan,
    ResearchSynthesis,
    ScoreBreakdown,
    ScoreComponent,
)


class DummyCrawler(BaseCrawler):
    def __init__(self, *args, **kwargs):
        # Skip parent initialization entirely
        self.config = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def arun(self, *_args, **_kwargs):
        return SimpleNamespace(success=True, markdown=None)



class FakeAgentResult:
    def __init__(self, output, label: str):
        self.output = output
        self._label = label

    def all_messages(self):
        return [
            ModelRequest(parts=[UserPromptPart(f"{self._label} prompt")]),
            ModelResponse(parts=[TextPart(content=f"{self._label} response")]),
        ]

    async def stream(self):
        # Simulate a single item stream
        yield None

    async def get_output(self):
        return self.output


def test_run_research_url_triggers_main_agent(monkeypatch, capsys, caplog):
    extraction = FacultyPageExtraction(
        faculty_page_url=HttpUrl("https://faculty.example.edu"),
        name="Dr. Example",
        institution="Example University",
        department="CS",
        email="dr@example.edu",
        bio_summary="Focuses on trustworthy AI.",
        research_areas=["AI", "NLP"],
        personal_homepage=HttpUrl("https://example.edu/home"),
        google_scholar_url=HttpUrl("https://scholar.google.com/citations?user=abc"),
        semantic_scholar_url=None,
        dblp_url=None,
        orcid_url=None,
        arxiv_author_url=None,
        other_links=[
            ExtractedLink(
                label="Lab",
                url=HttpUrl("https://example.edu/lab"),
                category="lab",
                source="faculty_profile",
            )
        ],
        pages_crawled=[HttpUrl("https://faculty.example.edu")],
    )

    caplog.set_level("INFO")
    fake_faculty_calls = {}

    async def fake_faculty_run(prompt, deps=None):
        fake_faculty_calls["prompt"] = prompt
        return FakeAgentResult(extraction, "faculty")

    plan = ResearchPlan(
        objectives=["Check advising style", "Verify lab activity"],
        prioritized_sources=["personal homepage", "lab page"],
        information_targets=["advising philosophy", "lab size"],
    )
    recruiting = RecruitingInsight(
        source_url="https://example.edu/recruiting",
        verbatim_text="I am recruiting PhD students.",
        is_recruiting=True,
        confidence=0.9,
    )
    synthesis = ResearchSynthesis(
        score=82.0,
        score_breakdown=ScoreBreakdown(
            research_alignment=ScoreComponent(
                score=20, max_score=25, explanation="Strong alignment."
            ),
            methods_overlap=ScoreComponent(
                score=12, max_score=15, explanation="Good methods overlap."
            ),
            publication_quality=ScoreComponent(
                score=12, max_score=15, explanation="Solid publication quality."
            ),
            recent_activity=ScoreComponent(
                score=8, max_score=10, explanation="Active publication record."
            ),
            funding=ScoreComponent(
                score=7, max_score=10, explanation="Some funding."
            ),
            recruiting_status=ScoreComponent(
                score=13, max_score=15, explanation="Actively recruiting."
            ),
            advising_and_lab=ScoreComponent(
                score=4, max_score=5, explanation="Good lab environment."
            ),
            program_fit=ScoreComponent(
                score=5, max_score=5, explanation="Good program fit."
            ),
            red_flags=ScoreComponent(
                score=1, max_score=0, explanation="Minor concerns."
            ),
        ),
        verdict="Strong fit for trustworthy AI research.",
        red_flags=None,
        research_fit="Solid alignment with user interests.",
        highlighted_papers=None,
        recruiting=recruiting,
        advising_and_lab=None,
        activity="Active publication record.",
        plan=plan,
    )

    fake_main_calls = {}

    async def fake_main_run(prompt, deps=None):
        fake_main_calls["prompt"] = prompt
        return FakeAgentResult(synthesis, "main")

    # Mock downselector agent
    from src.schema import PaperSelection
    paper_selection = PaperSelection(
        selected=[],
        selected_count=0,
        skipped_no_pdf=0,
        failures=[],
    )

    async def fake_downselector_run(prompt, deps=None):
        return FakeAgentResult(paper_selection, "downselector")

    # Mock recruiting agent
    async def fake_recruiting_run(prompt, deps=None):
        return FakeAgentResult(recruiting, "recruiting")

    fake_faculty_agent = SimpleNamespace(run=fake_faculty_run)
    fake_downselector_agent = SimpleNamespace(run=fake_downselector_run)
    fake_recruiting_agent = SimpleNamespace(run=fake_recruiting_run)
    fake_main_agent = SimpleNamespace(run=fake_main_run)

    monkeypatch.setattr("src.main.faculty_extractor_agent", fake_faculty_agent)
    monkeypatch.setattr("src.main.downselector_agent", fake_downselector_agent)
    monkeypatch.setattr("src.main.recruiting_agent", fake_recruiting_agent)
    monkeypatch.setattr("src.main.main_agent", fake_main_agent)
    monkeypatch.setattr("crawl4ai.AsyncWebCrawler", DummyCrawler)

    # Mock fetch_scholar_papers to avoid actual Scholar scraping
    from src.schema import ScholarPaperResults
    async def fake_fetch_scholar_papers(deps, google_scholar_url):
        return ScholarPaperResults(
            query=google_scholar_url,
            profile_url=google_scholar_url,
            fetch_url=google_scholar_url,
            papers=[],
            total_results=0,
        )
    monkeypatch.setattr("src.main.fetch_scholar_papers", fake_fetch_scholar_papers)

    asyncio.run(cli_main._run_research_url("https://faculty.example.edu"))

    # Verify the agents were called with the right data
    assert "Dr. Example" in fake_main_calls["prompt"]
    assert "https://example.edu/home" in fake_main_calls["prompt"]
