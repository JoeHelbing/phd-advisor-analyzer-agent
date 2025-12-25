import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.scholar import parse_citation_html, parse_profile_html  # noqa: E402


def test_parse_profile_extracts_rows_and_links():
    html = Path("tests/fixtures/scholar_profile.html").read_text()
    papers = parse_profile_html(html, max_papers=5)
    assert len(papers) == 1
    assert papers[0].title == "Test Paper"
    assert papers[0].citation_url.endswith("view_op=view_citation&foo=bar")


def test_parse_citation_extracts_pdf_and_abstract():
    html = Path("tests/fixtures/scholar_citation.html").read_text()
    fields, pdf_url = parse_citation_html(html)
    assert pdf_url == "https://arxiv.org/pdf/2507.00163"
    assert fields["Description"].startswith("This paper")
