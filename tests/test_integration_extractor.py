"""Integration tests for faculty extractor agent."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.schema import ResearchDeps


@pytest.fixture
def mock_deps():
    """Create mock dependencies."""
    return ResearchDeps(
        http_client=MagicMock(),
        crawler=MagicMock(),
        google_api_key="test-key",
        google_cse_id="test-cse",
        research_interests="interests",
    )
