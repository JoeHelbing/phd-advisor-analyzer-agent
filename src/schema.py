from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx
from crawl4ai import AsyncWebCrawler
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ResearchDeps(BaseModel):
    """Shared dependencies for all agents."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    http_client: httpx.AsyncClient
    crawler: AsyncWebCrawler
    google_api_key: str
    google_cse_id: str
    sop_text: str = ""
    gemini_service: Any | None = None  # GeminiPaperReviewService for paper reviews

    # Debug flags
    debug_skip_reviews: bool = False

    # Fetch cache: maps URL to cached fetch results with metadata
    fetch_cache: dict[str, CachedFetchResult] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Tool Result Types
# These schemas define the return types for tool functions in src/tools.py
# --------------------------------------------------------------------------


class SearchResult(BaseModel):
    """A single web search result.

    Used by: tools.web_search()
    Consumed by: main_agent, recruiting_agent (via web_search tool)
    """

    title: str
    url: str
    snippet: str


class SearchResults(BaseModel):
    """Collection of web search results.

    Used by: tools.web_search() (return type)
    Consumed by: main_agent, recruiting_agent (via web_search tool)
    Flow: Google Custom Search API → web_search() → agent tools
    """

    query: str
    results: list[SearchResult]
    total_results: int


class FetchResult(BaseModel):
    """Result of fetching a URL.

    Used by: tools.fetch_url() (return type)
    Consumed by: main_agent, faculty_extractor_agent (via fetch_url tool)
    Flow: Crawl4AI → fetch_url() → agent tools
    """

    url: str
    success: bool
    content: str
    error: str | None = None


class CachedFetchResult(BaseModel):
    """Cached result of a fetch_url call with metadata.

    Used by: ResearchDeps.fetch_cache (storage)
    Purpose: Store fetched URL content to avoid redundant crawls
    """

    url: str
    content: str
    success: bool
    error: str | None = None
    character_count: int
    fetched_at: datetime


class ScholarRequestPacer(BaseModel):
    """Distributes Scholar HTTP calls across a minimum duration.

    Used by: tools.fetch_scholar_papers() (internal rate limiting)
    Purpose: Prevents Google Scholar throttling by pacing requests
    Flow: Created per fetch_scholar_papers() call → coordinates timing
          of Scholar API requests
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    total_calls: int
    target_duration: float = 60.0
    start_time: float = Field(default_factory=time.perf_counter)
    completed_calls: int = 0

    def update_total_calls(self, total_calls: int) -> None:
        self.total_calls = max(total_calls, self.completed_calls or 1)

    async def mark_call_complete(self) -> None:
        self.completed_calls += 1
        if self.completed_calls > self.total_calls:
            self.total_calls = self.completed_calls
        await self._sync_to_schedule(self.completed_calls)

    async def finalize(self) -> None:
        await self._sync_to_schedule(max(self.total_calls, self.completed_calls))

    async def _sync_to_schedule(self, slot: int) -> None:
        if self.total_calls <= 0:
            return
        ideal_elapsed = self.target_duration * (slot / self.total_calls)
        actual_elapsed = time.perf_counter() - self.start_time
        delay = ideal_elapsed - actual_elapsed
        if delay > 0:
            import asyncio

            await asyncio.sleep(delay)


# --------------------------------------------------------------------------
# Research Target & Metadata Types
# --------------------------------------------------------------------------


class PaperMetadata(BaseModel):
    title: str
    source: str
    url: str
    authors: str
    venue: str | None = None
    published_at: str | None = None
    citation_count: int | None = None


class PaperReview(BaseModel):
    metadata: PaperMetadata
    confirmed_author: bool
    affiliation_match: bool
    abstract: str
    summary_for_user: str
    url_context_status: str | None = None
    url_context_strategy: str | None = None
    url_context_metadata: dict | None = None
    usage_metadata: dict | None = None


class PaperFailure(BaseModel):
    index: int
    title: str
    url: str | None = None
    status: str | None = None
    reason: str


class PaperSelection(BaseModel):
    selected: list[PaperReview]
    selected_count: int
    skipped_no_pdf: int
    failures: list[PaperFailure] = Field(default_factory=list)


class ScholarPaperCandidate(BaseModel):
    title: str
    authors: str
    venue: str
    year: str
    citation_url: str
    pdf_url: str
    abstract: str
    citation_count: int | None = None


class ScholarPaperResults(BaseModel):
    query: str
    profile_url: str | None = None
    fetch_url: str | None = None  # Actual URL used to fetch (with sorting/pagination)
    papers: list[ScholarPaperCandidate]
    total_results: int


class RecruitingInsight(BaseModel):
    """Recruiting status insight for a professor.

    Used by: recruiting_agent (output type)
    Contains the verbatim text from the professor about PhD recruiting
    and a direct link for manual verification.
    """

    source_url: str = Field(
        ...,
        description="Direct URL where the recruiting statement was found (for user verification)",
    )
    verbatim_text: str = Field(
        ...,
        description=(
            "Exact quote from the professor about PhD student recruiting. "
            "Copy the text verbatim - do not paraphrase or summarize."
        ),
    )
    is_recruiting: bool = Field(
        ...,
        description="True if the professor is actively recruiting PhD students",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) based on recency and clarity of the signal",
    )


class ScholarProfileResult(BaseModel):
    """Result from scholar_finder_agent.

    Used by: scholar_finder_agent (output type)
    Contains only the verified Google Scholar profile URL.
    """

    google_scholar_url: HttpUrl | None = Field(
        None, description="The verified Google Scholar profile URL, or None if not found"
    )
    confidence: str = Field(
        ...,
        description=(
            "Confidence level: 'high' if name/institution match, "
            "'medium' if partial match, 'low' if uncertain, "
            "'not_found' if no profile found"
        ),
    )
    reasoning: str = Field(
        ..., description="Brief explanation of why this URL was selected or why no URL was found"
    )


class ExtractedLink(BaseModel):
    """A discovered link with categorization."""

    label: str
    url: HttpUrl
    category: str  # teaching, lab, social, recruiting, cv, media, papers, other
    source: str  # "faculty_profile" or "personal_homepage"


class FacultyPageExtraction(BaseModel):
    """Structured extraction from faculty profile + homepage."""

    # Input
    faculty_page_url: HttpUrl

    # Basic identity
    name: str
    institution: str
    department: str | None = None
    email: str | None = None

    # Research context
    bio_summary: str | None = None
    research_areas: list[str] = Field(default_factory=list)

    # Known academic profiles (dedicated fields)
    personal_homepage: HttpUrl | None = None
    google_scholar_url: HttpUrl | None = None
    semantic_scholar_url: HttpUrl | None = None
    dblp_url: HttpUrl | None = None
    orcid_url: HttpUrl | None = None
    arxiv_author_url: HttpUrl | None = None

    # All other discovered links
    other_links: list[ExtractedLink] = Field(default_factory=list)

    # Metadata
    pages_crawled: list[HttpUrl]


class ResearchPlan(BaseModel):
    """Research plan for main agent to gather additional information.

    Describes what information the agent needs beyond the faculty data,
    paper reviews, and recruiting info already provided.
    """
    objectives: list[str] = Field(
        ...,
        description=(
            "Research objectives to accomplish. "
            "e.g., 'Verify advising style', 'Assess lab culture', 'Check recent activity'"
        ),
    )
    prioritized_sources: list[str] = Field(
        ...,
        description=(
            "Ordered list of sources to investigate. "
            "e.g., 'personal homepage', 'lab page', 'department news', 'recent talks'"
        ),
    )
    information_targets: list[str] = Field(
        ...,
        description=(
            "Specific pieces of information to find. "
            "e.g., 'advising philosophy', 'lab size', 'recent grants', 'teaching load'"
        ),
    )


# --------------------------------------------------------------------------
# Research Synthesis (Main Agent Output)
# --------------------------------------------------------------------------


class ResearchSynthesis(BaseModel):
    """Main agent output: synthesized research fit analysis."""

    # Core output (for sorting/filtering)
    score: float = Field(..., ge=0, le=100)
    verdict: str = Field(..., description="1-2 sentence summary")
    # Red flags (if any concerns)
    red_flags: str | None = Field(None, description="Any concerns, or None")
    # Research fit - one prose section covering topic/methods/trajectory
    research_fit: str = Field(
        ..., description="Analysis of research alignment with user's interests"
    )
    # 1-2 highlighted papers if super relevant (just titles + why)
    highlighted_papers: str | None = Field(
        None, description="1-2 super relevant papers with brief note on why"
    )
    # Recruiting (structured for the verbatim quote + link)
    recruiting: RecruitingInsight
    # Advising & lab info (combined)
    advising_and_lab: str | None = Field(
        None, description="Advising style, lab size, culture notes if found"
    )
    # Activity - publication rate, funding, visibility
    activity: str = Field(..., description="Recent publications, funding, other activity signals")
    # Research plan (needed for submit_research_plan tool)
    plan: ResearchPlan


class ResearchReport(BaseModel):
    """Final report: synthesis + paper reviews assembled in main.py."""

    professor: FacultyPageExtraction
    synthesis: ResearchSynthesis
    paper_reviews: list[PaperReview] = Field(default_factory=list)
    paper_failures: list[PaperFailure] = Field(default_factory=list)
    created_at: datetime
