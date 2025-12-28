"""Tests for the research-url CLI command."""

import sys
from pathlib import Path

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src import main as cli_main

runner = CliRunner()


def test_research_url_command_invokes_async_runner(monkeypatch):
    called = {}

    async def fake_run(url: str, debug_skip_reviews: bool = False) -> None:
        called["url"] = url
        called["debug_skip_reviews"] = debug_skip_reviews

    monkeypatch.setattr(cli_main, "_run_research_url", fake_run)

    result = runner.invoke(cli_main.app, ["https://example.com"])

    assert result.exit_code == 0
    assert called["url"] == "https://example.com"
    assert called["debug_skip_reviews"] is False
