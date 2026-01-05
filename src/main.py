"""CLI for professor research system."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from textwrap import dedent

import httpx
import typer
from crawl4ai import AsyncWebCrawler

from src.agents import (
    downselector_agent,
    faculty_extractor_agent,
    main_agent,
    recruiting_agent,
    scholar_finder_agent,
)
from src.config import SETTINGS
from src.report_formatter import save_report
from src.schema import ResearchDeps, ResearchReport
from src.scholar import fetch_scholar_papers
from src.tools import NoScholarProfileError, NotFacultyPageError, ValidationError

logger = logging.getLogger(__name__)

app = typer.Typer()


def _load_research_interests_text() -> str:
    research_interests_path = SETTINGS.runtime.research_interests_path
    try:
        return research_interests_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


async def _run_research_url(url: str, debug_skip_reviews: bool = False) -> str:
    research_interests_text = _load_research_interests_text()

    # Create Gemini service if needed (not in debug mode)
    gemini_service = None
    if not debug_skip_reviews:
        from src.gemini_url_context import (
            GeminiPaperReviewConfig,
            GeminiPaperReviewService,
            create_async_client,
        )

        api_key = SETTINGS.google_ai_studio_api_key
        if not api_key:
            raise RuntimeError("Missing Google AI Studio API key for Gemini summaries.")

        client = create_async_client(api_key)
        config = GeminiPaperReviewConfig.from_settings()
        gemini_service = GeminiPaperReviewService(client, config)

    async with AsyncWebCrawler() as crawler:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(headers=headers, timeout=30) as http_client:
            deps = ResearchDeps(
                http_client=http_client,
                crawler=crawler,
                google_api_key=SETTINGS.google_api_key,
                google_cse_id=SETTINGS.google_cse_id,
                research_interests=research_interests_text,
                gemini_service=gemini_service,
                debug_skip_reviews=debug_skip_reviews,
            )

            if debug_skip_reviews:
                logger.debug(
                    "[bold yellow]⚠ Debug mode: Skipping Gemini paper reviews"
                    "[/bold yellow]\n"
                )

            # ============================================================
            # STEP 1: Extract Faculty Information
            # ============================================================
            logger.info("\n[bold cyan]═══ Step 1: Faculty Extraction ═══[/bold cyan]\n")
            result = await faculty_extractor_agent.run(
                f"Extract information from this faculty page: {url}",
                deps=deps,
            )
            extraction = result.output
            logger.info(f"[bold green]✓ Extracted:[/bold green] {extraction.name}")
            logger.info(f"[dim]Institution:[/dim] {extraction.institution}")
            logger.info("Plus gobs of other links and metadata...")
            logger.debug(f"[dim]Department:[/dim] {extraction.department or 'N/A'}")
            logger.debug(
                f"[dim]Scholar URL:[/dim] {extraction.google_scholar_url or 'Not found'}\n"
            )

            # ============================================================
            # STEP 2: Fetch Google Scholar Papers
            # ============================================================
            logger.info("\n[bold cyan]═══ Step 2: Google Scholar Scrape ═══[/bold cyan]\n")

            # Faculty extractor should have found Scholar URL or raised exception
            # This is a safety check that should not normally trigger
            if not extraction.google_scholar_url:
                raise NoScholarProfileError(
                    f"No Google Scholar profile found for {extraction.name} "
                    f"at {extraction.institution}"
                )

            scholar_url_str = str(extraction.google_scholar_url)
            logger.info(f"Extracted Scholar URL: {extraction.google_scholar_url}")
            logger.info("This can take a minute due to rate limiting...")
            logger.info("Searching for papers...")

            # Fetch Scholar papers (pure helper function, not a tool)
            scholar_results = await fetch_scholar_papers(
                deps=deps,
                google_scholar_url=scholar_url_str,
            )
            logger.info(
                f"[bold green]✓ Found {len(scholar_results.papers)} papers with PDFs"
                f"[/bold green]"
            )
            logger.debug(f"[dim]Input URL:[/dim] {scholar_results.query}")
            logger.debug(
                f"[dim]Fetch URL (with sorting):[/dim] {scholar_results.fetch_url}"
            )
            logger.debug(f"[dim]Profile URL:[/dim] {scholar_results.profile_url}")

            # ============================================================
            # STEP 3: Run Downselector Agent
            # ============================================================
            logger.info("\n[bold cyan]═══ Step 3: Paper Downselection ═══[/bold cyan]\n")

            if not scholar_results or not scholar_results.papers:
                logger.debug(
                    "[bold yellow]⚠ No papers to downselect - skipping"
                    "[/bold yellow]\n"
                )
                paper_selection = None
            else:
                # Serialize papers to JSON for the prompt
                papers_data = [
                    {
                        "title": p.title,
                        "authors": p.authors,
                        "venue": p.venue,
                        "year": p.year,
                        "pdf_url": p.pdf_url,
                        "abstract": p.abstract,
                        "citation_url": p.citation_url,
                    }
                    for p in scholar_results.papers
                ]

                # Construct prompt with all relevant information
                prompt = dedent(f"""
                    Select and review papers for {extraction.name} at {extraction.institution}.

                    Faculty Profile URL: {url}
                    Scholar Profile: {scholar_results.profile_url}

                    Research Interests:
                    {research_interests_text}

                    Papers scraped from Google Scholar ({len(papers_data)} papers,
                    chronologically sorted, most recent first):

                    {json.dumps(papers_data, indent=2)}
                """).strip()

                logger.info(
                    f"[dim]Sending {len(scholar_results.papers)} papers to downselector..."
                    "[/dim]"
                )
                result = await downselector_agent.run(prompt, deps=deps)
                paper_selection = result.output
                logger.info(
                    f"[bold green]✓ Selected {paper_selection.selected_count} papers"
                    f"[/bold green]"
                )
                logger.debug(
                    f"[dim]Skipped (no PDF): {paper_selection.skipped_no_pdf}[/dim]"
                )
                logger.debug(
                    f"[dim]Failures: {len(paper_selection.failures)}[/dim]\n"
                )

            # ============================================================
            # STEP 4: Recruiting Status Check
            # ============================================================
            logger.info("\n[bold cyan]═══ Step 4: Recruiting Status ═══[/bold cyan]\n")

            # Pass the full extraction to the recruiting agent
            extraction_dict = extraction.model_dump(mode='json')
            recruiting_prompt = (
                f"Check recruiting status for this professor.\n\n"
                f"Faculty data:\n{json.dumps(extraction_dict, indent=2)}"
            )

            logger.debug(f"[dim]Checking recruiting status for {extraction.name}...[/dim]")
            recruiting_result = await recruiting_agent.run(recruiting_prompt, deps=deps)
            recruiting_insight = recruiting_result.output

            if recruiting_insight.is_recruiting:
                logger.info(
                    f"[bold green]✓ Recruiting:[/bold green] "
                    f"confidence={recruiting_insight.confidence:.2f}"
                )
            else:
                logger.info(
                    f"[bold yellow]✗ Not recruiting:[/bold yellow] "
                    f"confidence={recruiting_insight.confidence:.2f}"
                )
            logger.debug(f"[dim]Source:[/dim] {recruiting_insight.source_url}")
            logger.debug(f"[dim]Quote:[/dim] {recruiting_insight.verbatim_text[:100]}...\n")

            # ============================================================
            # STEP 5: Main Agent Synthesis
            # ============================================================
            logger.info("\n[bold cyan]═══ Step 5: Research Synthesis ═══[/bold cyan]\n")

            prompt = (
                f"Synthesize a research report for this professor.\n\n"
                f"Faculty data:\n{json.dumps(extraction_dict, indent=2)}\n\n"
            )
            if paper_selection:
                papers_dict = [p.model_dump(mode='json') for p in paper_selection.selected]
                prompt += f"Selected papers:\n{json.dumps(papers_dict, indent=2)}\n\n"

            # Include recruiting insight in prompt
            recruiting_dict = recruiting_insight.model_dump(mode='json')
            prompt += f"Recruiting status:\n{json.dumps(recruiting_dict, indent=2)}\n\n"

            # Include user's research interests
            prompt += f"User's research interests:\n{research_interests_text}\n\n"

            result = await main_agent.run(prompt, deps=deps)
            synthesis = result.output

            logger.info(
                f"[bold green]✓ Synthesis complete:[/bold green] "
                f"score={synthesis.score:.0f}"
            )
            if synthesis.red_flags:
                logger.debug(f"[bold yellow]⚠ Red flags:[/bold yellow] {synthesis.red_flags}")

            # ============================================================
            # STEP 6: Assemble & Save Report
            # ============================================================
            logger.info("\n[bold cyan]═══ Step 6: Save Report ═══[/bold cyan]\n")

            # Assemble final report from synthesis + paper reviews
            research_report = ResearchReport(
                professor=extraction,
                synthesis=synthesis,
                paper_reviews=paper_selection.selected if paper_selection else [],
                paper_failures=paper_selection.failures if paper_selection else [],
                created_at=datetime.now(),
            )

            # Format to markdown
            from src.report_formatter import format_report
            markdown_report = format_report(research_report)

            # Save to disk
            output_dir = Path("reports")
            report_path = save_report(research_report, output_dir)
            logger.info(f"[bold green]✓ Report saved:[/bold green] {report_path}\n")

            return markdown_report  # Return markdown string directly


@app.command(name="research-url")
def research_url(
    url: str = typer.Argument(..., help="Faculty profile URL to research"),
    debug_skip_reviews: bool = typer.Option(
        False,
        "--debug-skip-reviews",
        help="Skip Gemini paper reviews (use mock data for faster debugging)",
    ),
) -> None:
    """Research a professor from their faculty profile URL."""
    asyncio.run(_run_research_url(url, debug_skip_reviews))


if __name__ == "__main__":
    app()
