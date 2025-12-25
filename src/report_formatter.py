"""Markdown report formatting for research results."""

from pathlib import Path

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
        "## Verdict",
        syn.verdict,
        "",
    ]

    if syn.red_flags:
        parts.extend(["## ⚠️ Red Flags", syn.red_flags, ""])

    parts.extend(["## Research Fit", syn.research_fit, ""])

    if syn.highlighted_papers:
        parts.extend(["## Highlighted Papers", syn.highlighted_papers, ""])

    parts.extend([
        "## Recruiting",
        f"**Status:** {status} (confidence: {rec.confidence:.2f})",
        f"**Source:** {rec.source_url}",
        "",
        f"> {rec.verbatim_text}",
        "",
    ])

    if syn.advising_and_lab:
        parts.extend(["## Advising & Lab", syn.advising_and_lab, ""])

    parts.extend(["## Activity", syn.activity, ""])

    if report.paper_reviews:
        parts.append("## Paper Reviews")
        for i, r in enumerate(report.paper_reviews, 1):
            # Format paper header with metadata
            parts.append(f"### {i}. {r.metadata.title}")

            # Authors
            if r.metadata.authors:
                parts.append(f"**Authors:** {r.metadata.authors}")

            # Venue and year
            venue_parts = []
            if r.metadata.venue:
                venue_parts.append(r.metadata.venue)
            if r.metadata.published_at:
                venue_parts.append(r.metadata.published_at)
            if venue_parts:
                parts.append(f"**Published:** {' • '.join(venue_parts)}")

            # URL
            if r.metadata.url:
                parts.append(f"**URL:** {r.metadata.url}")

            # Citation count
            if r.metadata.citation_count is not None:
                parts.append(f"**Citations:** {r.metadata.citation_count}")

            # Abstract
            if r.abstract:
                parts.extend(["", "**Abstract:**", r.abstract])

            # Summary
            parts.extend(["", "**Summary:**", r.summary_for_user, ""])

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
