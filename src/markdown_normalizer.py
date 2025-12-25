"""Markdown normalization utilities."""

import re


def normalize_markdown(text: str | None) -> str | None:
    """
    Normalize markdown formatting in agent-generated text.

    Fixes:
    - Errant title headings (# Paper Review: ...)
    - Bullet point inconsistency (• → -)
    - Excessive blank lines
    - Heading hierarchy issues
    """
    if not text:
        return text

    # Strip errant title headings at start of text
    # Pattern: "# Paper Review:" or similar at text start
    text = re.sub(r'^#\s+Paper Review:.*?\n+', '', text, flags=re.MULTILINE)

    # Normalize bullet points to markdown list syntax
    text = normalize_bullet_points(text)

    # Normalize heading depths
    text = normalize_heading_depths(text)

    # Collapse excessive blank lines (3+ → 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def normalize_bullet_points(text: str) -> str:
    """
    Convert bullet point characters (•) to markdown list syntax (-).

    Handles:
    - • at line start → -
    - Preserves existing - or * bullets
    """
    # Replace • bullet character with markdown dash
    # Pattern: start of line (or after newline), optional whitespace, •, space
    text = re.sub(r'^(\s*)•\s+', r'\1- ', text, flags=re.MULTILINE)

    return text


def normalize_heading_depths(text: str) -> str:
    """
    Normalize heading hierarchy to consistent depths.

    Rules:
    - H1 (#) should be rare (report title only, added by formatter)
    - H2 (##) for main sections
    - H3 (###) for subsections
    - H4+ (####) for nested content

    This function demotes any H1 headings found in agent text to H2.
    """
    # Demote H1 headings to H2 (except those that look like paper titles in formatter)
    # This catches cases like "# Some Section" → "## Some Section"
    # But preserves numbered sections like "### 1. Paper Gist"

    lines = text.split('\n')
    normalized_lines = []

    for line in lines:
        # If line starts with exactly one #, demote to ##
        if re.match(r'^#\s+', line) and not re.match(r'^###', line):
            # Demote: # Title → ## Title
            normalized_lines.append('#' + line)
        else:
            normalized_lines.append(line)

    return '\n'.join(normalized_lines)


def escape_table_cell(text: str) -> str:
    """
    Escape special characters in markdown table cells.

    Escapes:
    - Pipe characters (|) that would break table structure
    - Backticks in prose (preserve inline code)
    """
    # Replace literal pipes with escaped version
    # But preserve pipes inside code blocks (backtick-wrapped)
    # For simplicity: replace all | not in backticks

    # Simple approach: replace | with \|
    # (More sophisticated version would parse code spans)
    text = text.replace('|', '\\|')

    return text
