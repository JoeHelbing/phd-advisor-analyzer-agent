"""Research tools for the main agent.

These tools provide web search, page fetching, and PDF extraction capabilities.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from crawl4ai import CacheMode, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from pydantic_ai import RunContext
from tenacity import retry, stop_after_attempt, wait_exponential

from src.schema import (
    CachedFetchResult,
    FetchResult,
    PaperFailure,
    PaperMetadata,
    PaperReview,
    RecruitingInsight,
    ResearchDeps,
    ResearchPlan,
    SearchResult,
    SearchResults,
)

if TYPE_CHECKING:
    from crawl4ai import CrawlResult

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Validation Exceptions
# --------------------------------------------------------------------------


class ValidationError(Exception):
    """Base class for validation failures."""

    pass


class NotFacultyPageError(ValidationError):
    """Raised when URL is not an individual faculty page."""

    pass


class NoScholarProfileError(ValidationError):
    """Raised when faculty member has no Google Scholar profile."""

    pass


# --------------------------------------------------------------------------
# Web Search Tool
# --------------------------------------------------------------------------
#TODO: Use the findings from the google search experiment. Look into that more...

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def _google_search(
    client: Any,
    api_key: str,
    cse_id: str,
    query: str,
    num_results: int = 10,
) -> dict:
    """Execute Google Custom Search API request with retry logic."""
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": min(num_results, 10),  # API max is 10 per request
    }
    response = await client.get(
        "https://www.googleapis.com/customsearch/v1",
        params=params,
    )
    response.raise_for_status()
    return response.json()


async def web_search(
    ctx: RunContext[ResearchDeps],
    query: str,
    num_results: int = 10,
) -> SearchResults:
    """Search the web using Google Custom Search.

    Args:
        ctx: The run context with dependencies.
        query: The search query string.
        num_results: Maximum number of results to return (default 10, max 10).

    Returns:
        SearchResults containing the query, results list, and total count.
    """
    logger.info(f"Web search: {query!r}")

    try:
        data = await _google_search(
            client=ctx.deps.http_client,
            api_key=ctx.deps.google_api_key,
            cse_id=ctx.deps.google_cse_id,
            query=query,
            num_results=num_results,
        )

        items = data.get("items", [])
        results = [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in items
        ]

        total = int(data.get("searchInformation", {}).get("totalResults", 0))
        logger.info(f"Search returned {len(results)} results (total: {total})")

        return SearchResults(
            query=query,
            results=results,
            total_results=total,
        )

    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return SearchResults(
            query=query,
            results=[],
            total_results=0,
        )


# --------------------------------------------------------------------------
# Fetch URL Tool
# --------------------------------------------------------------------------


async def fetch_url(
    ctx: RunContext[ResearchDeps],
    url: str,
) -> FetchResult:
    """Fetch a URL and return its content as raw markdown.

    This function maintains a cache of fetched URLs in ctx.deps.fetch_cache
    to avoid redundant crawls across agents.

    Args:
        ctx: The run context with dependencies.
        url: The URL to fetch.

    Returns:
        FetchResult with success status and content/error.
    """
    # Check cache first
    if url in ctx.deps.fetch_cache:
        cached = ctx.deps.fetch_cache[url]
        logger.info(
            f"Using cached fetch for {url} ({cached.character_count} chars, fetched at"
            f" {cached.fetched_at})"
            )
        return FetchResult(
            url=cached.url,
            success=cached.success,
            content=cached.content,
            error=cached.error,
        )

    logger.info(f"Fetching URL: {url}")

    try:
        config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(),
            cache_mode=CacheMode.BYPASS,
        )

        # arun returns CrawlResult for single URL (cast for type checker)
        result = cast("CrawlResult", await ctx.deps.crawler.arun(url, config=config))

        if not result.success:
            logger.warning(f"Fetch failed for {url}: {result.error_message}")
            fetch_result = FetchResult(
                url=url,
                success=False,
                content="",
                error=result.error_message,
            )

            # Cache failed fetch to avoid retrying
            ctx.deps.fetch_cache[url] = CachedFetchResult(
                url=url,
                content="",
                success=False,
                error=result.error_message,
                character_count=0,
                fetched_at=datetime.now(),
            )

            return fetch_result

        content = ""
        if result.markdown:
            if hasattr(result.markdown, "raw_markdown"):
                content = result.markdown.raw_markdown or ""
            else:
                content = str(result.markdown)
        logger.info(f"Fetched {len(content)} chars from {url}")

        # Cache successful fetch
        ctx.deps.fetch_cache[url] = CachedFetchResult(
            url=url,
            content=content,
            success=True,
            error=None,
            character_count=len(content),
            fetched_at=datetime.now(),
        )

        return FetchResult(
            url=url,
            success=True,
            content=content,
        )

    except Exception as e:
        logger.error(f"Fetch error for {url}: {e}")
        fetch_result = FetchResult(
            url=url,
            success=False,
            content="",
            error=str(e),
        )

        # Cache exception to avoid retrying
        ctx.deps.fetch_cache[url] = CachedFetchResult(
            url=url,
            content="",
            success=False,
            error=str(e),
            character_count=0,
            fetched_at=datetime.now(),
        )

        return fetch_result


# --------------------------------------------------------------------------
# Paper Review Tool (Gemini URL Context)
# --------------------------------------------------------------------------


async def review_paper_pdf(
    ctx: RunContext[ResearchDeps],
    paper_url: str,
    paper_title: str,
    authors: str | None = None,
    venue: str | None = None,
    year: str | None = None,
    abstract: str | None = None,
    citation_count: int | None = None,
) -> PaperReview | PaperFailure:
    """Review a single academic paper from a PDF URL.

    The Scholar metadata (authors, venue, year, abstract, citation_count) is
    passed through verbatim from the Scholar scrape and attached to the
    PaperReview. This metadata is NOT sent to Gemini - only the URL and
    research interests are used for the AI summary.

    Args:
        ctx: The run context with dependencies.
        paper_url: Direct URL to the paper PDF.
        paper_title: Title of the paper.
        authors: Author names from Scholar (comma-separated string).
        venue: Publication venue (from Scholar scrape).
        year: Publication year (from Scholar scrape).
        abstract: Paper abstract (from Scholar scrape).
        citation_count: Number of citations (from Scholar scrape).

    Returns:
        PaperReview on success, PaperFailure if PDF cannot be accessed or processed.
    """
    # Debug mode: return mock data without calling Gemini
    if ctx.deps and ctx.deps.debug_skip_reviews:
        logger.info(f"[DEBUG] Skipping Gemini review for: {paper_title}")
        metadata = PaperMetadata(
            title=paper_title,
            source="debug_mock",
            url=paper_url,
            authors=authors or "Mock Author",
            venue=venue,
            published_at=year,
            citation_count=citation_count,
        )
        return PaperReview(
            metadata=metadata,
            confirmed_author=True,
            affiliation_match=True,
            abstract=abstract or "[DEBUG MODE] This is a mock abstract for debugging purposes.",
            summary_for_user="[DEBUG MODE] Mock paper summary. Gemini API was not called.",
            url_context_status="debug_skip",
        )

    service = ctx.deps.gemini_service
    assert service is not None, "gemini_service must exist when not in debug mode"
    logger.info(f"Reviewing paper: {paper_title}")

    try:
        summary = await service.summarize_paper(
            title=paper_title,
            url=paper_url,
            interests=ctx.deps.research_interests,
        )

        # If Gemini service returned an error, return PaperFailure instead of raising
        if summary.error:
            logger.warning(
                f"Paper review failed for '{paper_title}': {summary.error} "
                f"(status: {summary.status or 'unknown'})"
            )
            return PaperFailure(
                title=paper_title,
                url=paper_url,
                status=summary.status,
                reason=summary.error,
            )

        metadata = PaperMetadata(
            title=paper_title,
            source="gemini_url_context",
            url=paper_url,
            authors=authors or "",
            venue=venue,
            published_at=year,
            citation_count=citation_count,
        )
        usage = {
            "input_tokens": summary.usage.input_tokens,
            "output_tokens": summary.usage.output_tokens,
            "cache_read_tokens": summary.usage.cache_read_tokens,
            "details": summary.usage.details,
        }
        usage = {k: v for k, v in usage.items() if v}
        return PaperReview(
            metadata=metadata,
            confirmed_author=False,
            affiliation_match=False,
            abstract=abstract or "",
            summary_for_user=summary.text or "",
            url_context_status=summary.status,
            url_context_strategy=summary.strategy,
            url_context_metadata=summary.metadata,
            usage_metadata=usage if usage else None,
        )

    except Exception as e:
        # Catch any other errors (network issues, unexpected exceptions, etc.)
        logger.error(f"Unexpected error reviewing paper '{paper_title}': {e}")
        return PaperFailure(
            title=paper_title,
            url=paper_url,
            status=None,
            reason=f"Unexpected error: {str(e)}",
        )


# --------------------------------------------------------------------------
# Research Planning Tool
# --------------------------------------------------------------------------


async def submit_research_plan(
    ctx: RunContext[ResearchDeps],
    objectives: list[str],
    prioritized_sources: list[str],
    information_targets: list[str],
) -> str:
    """Submit a research plan outlining what additional information is needed.

    The agent should call this after reviewing the faculty extraction, paper
    reviews, and recruiting data, but before conducting additional research.
    This helps ensure a systematic approach to gathering missing information.

    Args:
        ctx: The run context with dependencies.
        objectives: List of research objectives to accomplish.
            e.g., "Verify advising style", "Assess lab culture", "Check recent activity"
        prioritized_sources: Ordered list of sources to investigate.
            e.g., "personal homepage", "lab page", "department news"
        information_targets: Specific pieces of information to find.
            e.g., "advising philosophy", "lab size", "recent grants"

    Returns:
        Confirmation message with next steps.
    """
    # Validate and construct the plan
    ResearchPlan(
        objectives=objectives,
        prioritized_sources=prioritized_sources,
        information_targets=information_targets,
    )

    logger.info(f"Research plan submitted with {len(objectives)} objectives")
    logger.debug(f"Objectives: {objectives}")
    logger.debug(f"Sources: {prioritized_sources}")
    logger.debug(f"Information targets: {information_targets}")

    sources_preview = (
        ", ".join(prioritized_sources[:3]) if prioritized_sources else "available sources"
    )
    return (
        f"Research plan accepted. Proceed with {len(objectives)} objectives. "
        f"Prioritize investigating: {sources_preview}."
    )


# --------------------------------------------------------------------------
# Recruiting Check Tool
# --------------------------------------------------------------------------


async def check_recruiting(
    ctx: RunContext[ResearchDeps],
    professor_name: str,
    institution: str,
    recruiting_url: str | None = None,
) -> RecruitingInsight:
    """Check if professor is recruiting students this cycle.

    Args:
        ctx: The run context with dependencies.
        professor_name: Full name of the professor.
        institution: Professor's institution name.
        recruiting_url: Optional direct URL to recruiting page (if known).

    Returns:
        RecruitingInsight with recruiting status and details.
    """
    # Import here to avoid circular dependency
    from src.agents import recruiting_agent

    if recruiting_url:
        prompt = (
            f"Check this page for recruiting info: {recruiting_url}\n"
            f"Professor: {professor_name}"
        )
    else:
        prompt = (
            f"Search for recruiting signals for: {professor_name} at {institution}"
        )

    result = await recruiting_agent.run(
        prompt,
        deps=ctx.deps,
        usage=ctx.usage,
    )
    return result.output


# --------------------------------------------------------------------------
# Tool registration helper
# --------------------------------------------------------------------------


def register_tools(agent):
    """Register basic research tools with an agent.

    This adds web_search and fetch_url as tools that the agent can call
    during its run.

    Args:
        agent: A PydanticAI Agent instance to register tools with.
    """
    agent.tool(web_search)
    agent.tool(fetch_url)


# --------------------------------------------------------------------------
# Validation Error Tools
# --------------------------------------------------------------------------


def raise_not_faculty_page_error(
    ctx: RunContext[ResearchDeps],
    reason: str,
) -> None:
    """Raise an error indicating the page is not an individual faculty page.

    Call this tool if the provided URL is not an individual faculty member's
    profile page (e.g., it's a department directory, listing page, etc.).

    Args:
        ctx: The run context with dependencies.
        reason: Brief explanation of why this is not an individual faculty page.

    Raises:
        NotFacultyPageError: Always raises this exception to stop processing.
    """
    raise NotFacultyPageError(
        f"The provided URL is not an individual faculty page. {reason}"
    )


def raise_no_scholar_profile_error(
    ctx: RunContext[ResearchDeps],
    name: str,
    institution: str,
) -> None:
    """Raise an error indicating no Google Scholar profile could be found.

    Call this tool if you cannot find a Google Scholar profile for the faculty
    member after thoroughly searching (both on their pages and via web search).

    Args:
        ctx: The run context with dependencies.
        name: The faculty member's name.
        institution: The faculty member's institution.

    Raises:
        NoScholarProfileError: Always raises this exception to stop processing.
    """
    raise NoScholarProfileError(
        f"Could not find a Google Scholar profile for {name} at {institution}. "
        f"This tool requires a Scholar profile to analyze research output."
    )


def register_main_agent_tools(agent):
    """Register tools specific to the main research agent.

    This adds submit_research_plan for the main agent's research workflow.
    Note: check_recruiting is now run as a separate pipeline step, not a tool.

    Args:
        agent: A PydanticAI Agent instance to register tools with.
    """
    agent.tool(submit_research_plan)


def register_downselector_tools(agent):
    """Register downselector-specific tools.

    This adds review_paper_pdf for the downselector agent to use when
    reviewing selected papers.

    Args:
        agent: A PydanticAI Agent instance to register tools with.
    """
    agent.tool(review_paper_pdf)


def register_faculty_extractor_tools(agent):
    """Register faculty-extractor-specific validation tools.

    This adds validation error tools that the faculty extractor agent can call
    to stop processing when encountering invalid input.

    Args:
        agent: A PydanticAI Agent instance to register tools with.
    """
    agent.tool(raise_not_faculty_page_error)
    agent.tool(raise_no_scholar_profile_error)
