import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.tools import fetch_scholar_papers  # noqa: E402


class DummyClient:
    def __init__(self, responses):
        self._responses = responses
        self._idx = 0

    async def get(self, url, params=None, follow_redirects=False):
        response = self._responses[self._idx]
        self._idx += 1
        return response


class StrictDummyClient(DummyClient):
    async def get(self, url, params=None, follow_redirects=False):
        if "googleapis.com/customsearch" in url:
            raise AssertionError("unexpected scholar search call")
        return await super().get(url, params=params, follow_redirects=follow_redirects)


class DummyResponse:
    def __init__(self, text, json_data=None):
        self.text = text
        self._json = json_data
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


def test_fetch_scholar_papers_filters_pdf_only():
    search_json = {
        "items": [{"link": "https://scholar.google.com/citations?user=abc"}],
        "searchInformation": {"totalResults": "1"},
    }
    profile_html = (
        "<tr class=\"gsc_a_tr\">"
        "<a class=\"gsc_a_at\" href=\"/citations?view_op=view_citation\">Test Paper</a>"
        "<div class=\"gs_gray\">Test Author</div>"
        "<div class=\"gs_gray\">Test Venue</div>"
        "<td class=\"gsc_a_y\"><span>2024</span></td>"
        "</tr>"
    )
    citation_html = (
        "<a href=\"https://arxiv.org/pdf/2507.00163\">"
        "<span class=\"gsc_vcd_title_ggt\">[PDF]</span></a>"
        "<div id=\"gsc_oci_descr\">Abstract text.</div>"
    )
    client = DummyClient(
        [
            DummyResponse("", json_data=search_json),
            DummyResponse(profile_html),
            DummyResponse(citation_html),
        ]
    )
    deps = SimpleNamespace(http_client=client, google_api_key="k", google_cse_id="c")
    ctx = SimpleNamespace(deps=deps)

    result = asyncio.run(fetch_scholar_papers(ctx, "Ari", "UChicago", max_papers=1, years_back=4))
    assert len(result.papers) == 1
    assert result.papers[0].pdf_url == "https://arxiv.org/pdf/2507.00163"


def test_fetch_scholar_papers_uses_profile_url_when_provided():
    profile_html = (
        "<tr class=\"gsc_a_tr\">"
        "<a class=\"gsc_a_at\" href=\"/citations?view_op=view_citation\">Test Paper</a>"
        "<div class=\"gs_gray\">Test Author</div>"
        "<div class=\"gs_gray\">Test Venue</div>"
        "<td class=\"gsc_a_y\"><span>2024</span></td>"
        "</tr>"
    )
    citation_html = (
        "<a href=\"https://arxiv.org/pdf/2507.00163\">"
        "<span class=\"gsc_vcd_title_ggt\">[PDF]</span></a>"
        "<div id=\"gsc_oci_descr\">Abstract text.</div>"
    )
    client = StrictDummyClient(
        [
            DummyResponse(profile_html),
            DummyResponse(citation_html),
        ]
    )
    deps = SimpleNamespace(http_client=client, google_api_key="k", google_cse_id="c")
    ctx = SimpleNamespace(deps=deps)

    result = asyncio.run(
        fetch_scholar_papers(
            ctx,
            "Ari",
            "UChicago",
            google_scholar_url="https://scholar.google.com/citations?user=abc",
            max_papers=1,
            years_back=4,
        )
    )
    assert result.profile_url == "https://scholar.google.com/citations?user=abc"
    assert len(result.papers) == 1
