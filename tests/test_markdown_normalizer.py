"""Tests for markdown normalization."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.markdown_normalizer import (
    escape_table_cell,
    normalize_bullet_points,
    normalize_heading_depths,
    normalize_markdown,
)


def test_normalize_bullet_points():
    """Test bullet point normalization."""
    input_text = """• First item
• Second item with details
  • Nested item"""

    expected = """- First item
- Second item with details
  - Nested item"""

    assert normalize_bullet_points(input_text) == expected


def test_normalize_bullet_points_preserves_existing():
    """Test that existing markdown bullets are preserved."""
    input_text = """- Already a dash
* Already an asterisk
• Bullet character"""

    result = normalize_bullet_points(input_text)

    assert "- Already a dash" in result
    assert "* Already an asterisk" in result
    assert "- Bullet character" in result
    assert "•" not in result


def test_strip_errant_title_heading():
    """Test removal of paper review title headings."""
    input_text = """# Paper Review: Example Title

## 1. Paper Gist
Content here."""

    expected = """## 1. Paper Gist
Content here."""

    assert normalize_markdown(input_text) == expected


def test_normalize_heading_depths():
    """Test heading depth normalization."""
    input_text = """# Some Section
Content
### Subsection"""

    expected = """## Some Section
Content
### Subsection"""

    assert normalize_heading_depths(input_text) == expected


def test_normalize_heading_depths_preserves_lower_headings():
    """Test that H2, H3, H4 headings are preserved."""
    input_text = """## Section
### Subsection
#### Sub-subsection"""

    result = normalize_heading_depths(input_text)

    assert "## Section" in result
    assert "### Subsection" in result
    assert "#### Sub-subsection" in result


def test_escape_table_cell():
    """Test table cell escaping."""
    text_with_pipe = "Uses A|B framework for testing"
    assert escape_table_cell(text_with_pipe) == "Uses A\\|B framework for testing"


def test_escape_table_cell_multiple_pipes():
    """Test escaping multiple pipe characters."""
    text = "Choice A|B|C framework"
    assert escape_table_cell(text) == "Choice A\\|B\\|C framework"


def test_normalize_markdown_comprehensive():
    """Test full normalization pipeline."""
    input_text = """# Paper Review: Test

• Uses interesting methods
• Shows strong results


## 1. Paper Gist
Content."""

    result = normalize_markdown(input_text)

    # Should remove title, fix bullets, collapse blank lines
    assert result is not None
    assert "# Paper Review" not in result
    assert "- Uses interesting methods" in result
    assert "- Shows strong results" in result
    assert result.count('\n\n\n') == 0  # No triple newlines


def test_normalize_markdown_empty_string():
    """Test that empty string returns empty string."""
    assert normalize_markdown("") == ""
    assert normalize_markdown(None) is None


def test_normalize_markdown_strips_whitespace():
    """Test that leading/trailing whitespace is stripped."""
    input_text = """

Some content

  """
    result = normalize_markdown(input_text)
    assert result == "Some content"


def test_normalize_bullet_points_with_mixed_indentation():
    """Test bullet normalization with mixed indentation."""
    input_text = """• Top level
  • Indented once
    • Indented twice"""

    result = normalize_bullet_points(input_text)

    assert "- Top level" in result
    assert "  - Indented once" in result
    assert "    - Indented twice" in result
