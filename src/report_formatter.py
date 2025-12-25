"""Markdown report formatting for research results."""

from pathlib import Path

from src.markdown_normalizer import escape_table_cell, normalize_markdown
from src.schema import ResearchReport


def format_report(report: ResearchReport) -> str:
    """Format a ResearchReport as markdown."""
    syn = report.synthesis
    rec = syn.recruiting

    # Differentiate between "not recruiting" and "no information found"
    if rec.is_recruiting:
        status = "✅ Recruiting"
    elif rec.confidence <= 0.3:
        # Low confidence + not recruiting = no information found
        status = "❓ No Information Found"
    else:
        # Higher confidence + not recruiting = actively not recruiting
        status = "❌ Not Recruiting"

    parts = [
        f"# {report.professor.name}",
        f"**Institution:** {report.professor.institution}",
        f"**Score:** {syn.score:.0f}/100",
        f"**Generated:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        # Score breakdown section
        "## Score Breakdown",
        "",
        "| Component | Score | Explanation |",
        "|-----------|-------|-------------|",
        (
            f"| Research Alignment | "
            f"{syn.score_breakdown.research_alignment.score:.0f}/"
            f"{syn.score_breakdown.research_alignment.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.research_alignment.explanation)} |"
        ),
        (
            f"| Methods Overlap | "
            f"{syn.score_breakdown.methods_overlap.score:.0f}/"
            f"{syn.score_breakdown.methods_overlap.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.methods_overlap.explanation)} |"
        ),
        (
            f"| Publication Quality | "
            f"{syn.score_breakdown.publication_quality.score:.0f}/"
            f"{syn.score_breakdown.publication_quality.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.publication_quality.explanation)} |"
        ),
        (
            f"| Recent Activity | "
            f"{syn.score_breakdown.recent_activity.score:.0f}/"
            f"{syn.score_breakdown.recent_activity.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.recent_activity.explanation)} |"
        ),
        (
            f"| Funding | "
            f"{syn.score_breakdown.funding.score:.0f}/"
            f"{syn.score_breakdown.funding.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.funding.explanation)} |"
        ),
        (
            f"| Recruiting | "
            f"{syn.score_breakdown.recruiting_status.score:.0f}/"
            f"{syn.score_breakdown.recruiting_status.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.recruiting_status.explanation)} |"
        ),
        (
            f"| Advising & Lab | "
            f"{syn.score_breakdown.advising_and_lab.score:.0f}/"
            f"{syn.score_breakdown.advising_and_lab.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.advising_and_lab.explanation)} |"
        ),
        (
            f"| Program Fit | "
            f"{syn.score_breakdown.program_fit.score:.0f}/"
            f"{syn.score_breakdown.program_fit.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.program_fit.explanation)} |"
        ),
        (
            f"| Red Flags | "
            f"{syn.score_breakdown.red_flags.score:.0f}/"
            f"{syn.score_breakdown.red_flags.max_score:.0f} | "
            f"{escape_table_cell(syn.score_breakdown.red_flags.explanation)} |"
        ),
        f"| **Total** | **{syn.score:.0f}/100** | |",
        "",
        "## Verdict",
        normalize_markdown(syn.verdict),
        "",
    ]

    if syn.red_flags:
        parts.extend(["## ⚠️ Red Flags", normalize_markdown(syn.red_flags), ""])

    parts.extend(["## Research Fit", normalize_markdown(syn.research_fit), ""])

    if syn.highlighted_papers:
        parts.extend(["## Highlighted Papers", normalize_markdown(syn.highlighted_papers), ""])

    parts.extend([
        "## Recruiting",
        f"**Status:** {status} (confidence: {rec.confidence:.2f})",
        f"**Source:** {rec.source_url}",
        "",
        f"> {rec.verbatim_text}",
        "",
    ])

    if syn.advising_and_lab:
        parts.extend(["## Advising & Lab", normalize_markdown(syn.advising_and_lab), ""])

    parts.extend(["## Activity", normalize_markdown(syn.activity), ""])

    if report.paper_reviews:
        parts.append("## Paper Reviews")
        for i, r in enumerate(report.paper_reviews, 1):
            # Format paper header with metadata
            parts.append(f"### {i}. Paper Title: {r.metadata.title}")
            parts.append("")  # Blank line after title

            # Authors
            if r.metadata.authors:
                parts.append(f"- **Authors:** {r.metadata.authors}")

            # Venue and year
            venue_parts = []
            if r.metadata.venue:
                venue_parts.append(r.metadata.venue)
            if r.metadata.published_at:
                venue_parts.append(r.metadata.published_at)
            if venue_parts:
                parts.append(f"- **Published:** {' • '.join(venue_parts)}")

            # URL
            if r.metadata.url:
                parts.append(f"- **URL:** {r.metadata.url}")

            # Citation count
            if r.metadata.citation_count is not None:
                parts.append(f"- **Citations:** {r.metadata.citation_count}")

            # Summary (normalize to fix title headings, bullets, etc.)
            parts.extend(["", normalize_markdown(r.summary_for_user), ""])

            # Abstract
            if r.abstract:
                parts.extend(["", "**Abstract:**", normalize_markdown(r.abstract)])

    return "\n".join(parts)


def save_report(report: ResearchReport, output_dir: Path) -> Path:
    """Save research report to markdown file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    score = f"{report.synthesis.score:02.0f}"
    name = report.professor.name.replace(' ', '_')
    safe_name = "".join(c for c in name if c.isalnum() or c == '_')

    path = output_dir / f"{score}_{safe_name}.md"
    path.write_text(format_report(report), encoding='utf-8')
    return path
