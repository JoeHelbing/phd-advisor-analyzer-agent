"""Google Scholar scraping and paper fetching.

This module handles all Scholar-specific logic including:
- HTML parsing of profile and citation pages
- Rate-limited fetching with retry logic
- Paper metadata extraction
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from rich.pretty import pretty_repr

from src.schema import ResearchDeps, ScholarPaperCandidate, ScholarPaperResults, ScholarRequestPacer

logger = logging.getLogger(__name__)

SCHOLAR_BASE = "https://scholar.google.com"


# --------------------------------------------------------------------------
# HTML Parsing Functions
# --------------------------------------------------------------------------


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


@dataclass
class ScholarPaper:
    title: str
    authors: str
    venue: str
    year: str
    citation_url: str


def parse_profile_html(html: str, max_papers: int) -> list[ScholarPaper]:
    """Parse Scholar profile page HTML to extract paper list."""
    soup = BeautifulSoup(html, "html.parser")
    papers = []
    for row in soup.select("tr.gsc_a_tr")[:max_papers]:
        title_el = row.select_one("a.gsc_a_at")
        if not title_el:
            continue
        title = _clean_text(title_el.get_text())
        href = title_el.get("href", "")
        citation_url = urljoin(SCHOLAR_BASE, str(href) if href else "")
        gray = row.select("div.gs_gray")
        authors = _clean_text(gray[0].get_text()) if len(gray) > 0 else ""
        venue = _clean_text(gray[1].get_text()) if len(gray) > 1 else ""
        year_el = row.select_one("td.gsc_a_y span") or row.select_one("td.gsc_a_y")
        year = _clean_text(year_el.get_text()) if year_el else ""
        papers.append(ScholarPaper(title, authors, venue, year, citation_url))
    return papers


def parse_citation_html(html: str) -> tuple[dict, str, int | None]:
    """Parse Scholar citation page HTML to extract PDF URL, metadata fields, and citation count."""
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}

    for field in soup.select(".gsc_oci_field, .gsc_vcd_field"):
        name = _clean_text(field.get_text())
        value_el = field.find_next_sibling("div")
        value = _clean_text(value_el.get_text()) if value_el else ""
        if name:
            fields[name] = value

    descr = soup.select_one("#gsc_oci_descr") or soup.select_one("#gsc_vcd_descr")
    if descr:
        fields.setdefault("Description", _clean_text(descr.get_text()))

    pdf_span = (
        soup.select_one("a span.gsc_vcd_title_ggt")
        or soup.select_one("a span.gsc_oci_title_ggt")
    )
    pdf_url = ""
    if pdf_span and pdf_span.parent and pdf_span.parent.name == "a":
        href = pdf_span.parent.get("href")
        pdf_url = _clean_text(str(href) if href else "")
    if pdf_url.startswith("/"):
        pdf_url = urljoin(SCHOLAR_BASE, pdf_url)

    # Extract citation count from "Cited by X" link
    citation_count = None
    cited_by_link = soup.find(
        "a", string=lambda text: text is not None and "Cited by" in text  # type: ignore[reportCallIssue,reportArgumentType]
    )
    if cited_by_link:
        cited_text = _clean_text(cited_by_link.get_text())
        # Extract number from "Cited by 32"
        parts = cited_text.split()
        if len(parts) >= 3 and parts[-1].isdigit():
            citation_count = int(parts[-1])

    return fields, pdf_url, citation_count


# --------------------------------------------------------------------------
# Fetch Helpers
# --------------------------------------------------------------------------


def _parse_year(value: str) -> int | None:
    """Extract 4-digit year from string like '2024' or 'Year: 2024'."""
    for token in value.split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return None


def _build_scholar_fetch_url(profile_url: str, max_papers: int) -> str:
    """Build Scholar URL with chronological sorting and pagination."""
    parsed = urlparse(profile_url)
    query_params = parse_qs(parsed.query)
    user_id = (query_params.get("user") or [""])[0]

    if not user_id:
        # Fallback: use original URL if we can't parse user ID
        return profile_url

    # Build URL with chronological sorting and max page size
    return (
        f"https://scholar.google.com/citations?"
        f"user={user_id}&hl=en&sortby=pubdate&cstart=0&pagesize={max_papers}"
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Extract Retry-After header value in seconds."""
    header = response.headers.get("Retry-After")
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


async def _fetch_scholar_page(
    deps: ResearchDeps,
    url: str,
    pacer: ScholarRequestPacer,
    max_attempts: int = 4,
) -> str | None:
    """Fetch a Scholar page with retry logic and rate limiting.

    Handles 429 throttling and 5xx errors with exponential backoff.
    Returns HTML string on success, None on failure.
    """
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            response = await deps.http_client.get(url)
        except httpx.HTTPError as exc:
            await pacer.mark_call_complete()
            last_error = str(exc)
            wait_seconds = min(30.0, 2**attempt)
            logger.warning(
                "Scholar request failed (attempt %s) for %s: %s", attempt, url, exc
            )
            await asyncio.sleep(wait_seconds)
            continue

        await pacer.mark_call_complete()
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            last_error = f"{status}"
            if status == 429 or status >= 500:
                retry_after = _retry_after_seconds(exc.response) or min(30.0, 2**attempt)
                logger.warning(
                    "Scholar request %s throttled (%s). Retrying in %.1fs",
                    url,
                    status,
                    retry_after,
                )
                await asyncio.sleep(retry_after)
                continue

            logger.error(
                "Scholar request %s failed with non-retryable status %s", url, status
            )
            return None

        return response.text

    logger.error(
        "Scholar request %s failed after %s attempts (%s)", url, max_attempts, last_error
    )
    return None


# --------------------------------------------------------------------------
# Main Fetch Function
# --------------------------------------------------------------------------


async def fetch_scholar_papers(
    deps: ResearchDeps,
    google_scholar_url: str,
    max_papers: int = 100,
    years_back: int = 4,
) -> ScholarPaperResults:
    """Fetch PDF-linked papers from a Google Scholar profile.

    This is NOT a tool - it's called directly by orchestration code.
    Papers are then passed to agents as data in prompts.

    Args:
        deps: Research dependencies.
        google_scholar_url: Google Scholar profile URL.
        max_papers: Max papers to parse from profile.
        years_back: Only include papers within the last N years.
    """
    pacer = ScholarRequestPacer(total_calls=max_papers + 1)

    query = google_scholar_url
    profile_url = google_scholar_url
    total_results = 0

    # Build fetch URL with chronological sorting and pagination
    fetch_url = _build_scholar_fetch_url(profile_url, max_papers)
    profile_html = await _fetch_scholar_page(deps, fetch_url, pacer)
    if not profile_html:
        await pacer.finalize()
        return ScholarPaperResults(
            query=query,
            profile_url=profile_url,
            fetch_url=fetch_url,
            papers=[],
            total_results=total_results,
        )

    raw_papers = parse_profile_html(profile_html, max_papers=max_papers)
    pacer.update_total_calls(1 + min(len(raw_papers), max_papers))

    cutoff_year = date.today().year - (years_back - 1)
    candidates: list[ScholarPaperCandidate] = []

    for paper in raw_papers:
        title_short = paper.title[:60] + "..." if len(paper.title) > 60 else paper.title

        year_value = _parse_year(paper.year)
        if year_value and year_value < cutoff_year:
            logger.debug(
                "  [dim] Skipped (too old):[/dim] [%s] %s",
                paper.year,
                title_short,
            )
            logger.debug("     [dim]Citation URL:[/dim] %s", paper.citation_url)
            continue

        if not paper.citation_url:
            logger.debug(
                "  [dim] Skipped (no citation URL):[/dim] [%s] %s",
                paper.year,
                title_short,
            )
            continue

        citation_html = await _fetch_scholar_page(
            deps,
            paper.citation_url,
            pacer,
        )
        if citation_html is None:
            logger.debug(
                "  [yellow] Failed to fetch citation page:[/yellow] [%s] %s",
                paper.year,
                title_short,
            )
            logger.debug(
                "     [yellow]Citation URL:[/yellow] %s",
                paper.citation_url,
            )
            continue

        fields, pdf_url, citation_count = parse_citation_html(citation_html)
        if not pdf_url:
            logger.debug(
                "  [dim] Skipped (no PDF):[/dim] [%s] %s",
                paper.year,
                title_short,
            )
            logger.debug(
                "     [dim]Citation URL:[/dim] %s",
                paper.citation_url,
            )
            continue

        abstract = fields.get("Description", "")

        candidate = ScholarPaperCandidate(
            title=paper.title,
            authors=paper.authors,
            venue=paper.venue,
            year=paper.year,
            citation_url=paper.citation_url,
            pdf_url=pdf_url,
            abstract=abstract,
            citation_count=citation_count,
        )

        title = candidate.title if len(candidate.title) <= 80 else f"{candidate.title[:77]}..."
        abstract_info = f"{len(candidate.abstract)} chars" if candidate.abstract else "No abstract"
        cite_info = f"{citation_count}" if citation_count is not None else "N/A"

        logger.info("     [bold cyan]Year: [%s] Title: [%s][/bold cyan]  %s", candidate.year, title)
        logger.debug("     [dim]Authors:[/dim] %s...", candidate.authors[:100])
        logger.debug("     [dim]Venue:[/dim] %s", candidate.venue)
        logger.debug("     [dim]Citations:[/dim] %s", cite_info)
        logger.debug("     [dim]Abstract:[/dim] %s", abstract_info)
        logger.info("     [dim]PDF:[/dim] %s...", candidate.pdf_url[:80])

        candidates.append(candidate)

    await pacer.finalize()

    results = ScholarPaperResults(
            query=query,
            profile_url=profile_url,
            fetch_url=fetch_url,
            papers=candidates,
            total_results=total_results,
        )

    logger.debug("\n[bold magenta]Scholar Results:[/bold magenta]\n%s", pretty_repr(results))

    return results
